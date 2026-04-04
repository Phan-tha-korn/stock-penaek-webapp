from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import (
    Attachment,
    AttachmentBinding,
    AttachmentMalwareStatus,
    AttachmentScanJob,
    AttachmentScanStatus,
    AttachmentStatus,
    AttachmentStorageDriver,
    AttachmentTypeClassification,
    User,
)
from server.services.attachment_policy import (
    DEFAULT_ENTITY_ATTACHMENT_LIMITS,
    SAFE_ATTACHMENT_TYPES,
    validate_attachment_payload,
)


ATTACHMENT_ROOT = Path(__file__).resolve().parents[2] / "storage" / "attachments"
LOCAL_ATTACHMENT_ROOT = ATTACHMENT_ROOT / "local"
OBJECT_ATTACHMENT_ROOT = ATTACHMENT_ROOT / "object"


CLASSIFICATION_RULES: dict[str, dict[str, dict[str, tuple[str, ...] | int]]] = {
    "product": {
        "image": {"mime": ("image/png", "image/jpeg", "image/webp", "image/gif"), "ext": (".png", ".jpg", ".jpeg", ".webp", ".gif")},
        "product_reference": {"mime": ("application/pdf", "text/plain"), "ext": (".pdf", ".txt", ".doc", ".docx")},
        "zip_archive": {"mime": ("application/zip", "application/x-zip-compressed"), "ext": (".zip",)},
        "other": {"mime": tuple(), "ext": tuple()},
    },
    "supplier": {
        "supplier_profile": {"mime": ("application/pdf", "text/plain"), "ext": (".pdf", ".txt", ".doc", ".docx")},
        "quote_document": {"mime": ("application/pdf",), "ext": (".pdf", ".doc", ".docx")},
        "invoice": {"mime": ("application/pdf", "image/png", "image/jpeg"), "ext": (".pdf", ".png", ".jpg", ".jpeg")},
        "chat_proof": {"mime": ("image/png", "image/jpeg", "image/webp"), "ext": (".png", ".jpg", ".jpeg", ".webp")},
        "zip_archive": {"mime": ("application/zip", "application/x-zip-compressed"), "ext": (".zip",)},
        "other": {"mime": tuple(), "ext": tuple()},
    },
    "price_record": {
        "quote_document": {"mime": ("application/pdf",), "ext": (".pdf", ".doc", ".docx")},
        "invoice": {"mime": ("application/pdf", "image/png", "image/jpeg"), "ext": (".pdf", ".png", ".jpg", ".jpeg")},
        "chat_proof": {"mime": ("image/png", "image/jpeg", "image/webp"), "ext": (".png", ".jpg", ".jpeg", ".webp")},
        "zip_archive": {"mime": ("application/zip", "application/x-zip-compressed"), "ext": (".zip",)},
        "other": {"mime": tuple(), "ext": tuple()},
    },
    "verify_request": {
        "quote_document": {"mime": ("application/pdf",), "ext": (".pdf", ".doc", ".docx")},
        "chat_proof": {"mime": ("image/png", "image/jpeg", "image/webp"), "ext": (".png", ".jpg", ".jpeg", ".webp")},
        "zip_archive": {"mime": ("application/zip", "application/x-zip-compressed"), "ext": (".zip",)},
        "other": {"mime": tuple(), "ext": tuple()},
    },
}


@dataclass
class StoredAttachment:
    storage_driver: AttachmentStorageDriver
    storage_bucket: str
    storage_key: str
    stored_filename: str


class AttachmentStorageAdapter(Protocol):
    driver: AttachmentStorageDriver

    def save(self, *, entity_type: str, entity_id: str, file_name: str, content: bytes) -> StoredAttachment:
        ...


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip("-.") or "file"


class LocalAttachmentStorageAdapter:
    driver = AttachmentStorageDriver.LOCAL

    def save(self, *, entity_type: str, entity_id: str, file_name: str, content: bytes) -> StoredAttachment:
        stored_name = f"{uuid.uuid4().hex}-{_slug(file_name)}"
        relative = Path(entity_type) / entity_id / stored_name
        target = LOCAL_ATTACHMENT_ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredAttachment(
            storage_driver=self.driver,
            storage_bucket="local-attachments",
            storage_key=str(relative).replace("\\", "/"),
            stored_filename=stored_name,
        )


class ObjectAttachmentStorageAdapter:
    driver = AttachmentStorageDriver.OBJECT

    def save(self, *, entity_type: str, entity_id: str, file_name: str, content: bytes) -> StoredAttachment:
        stored_name = f"{uuid.uuid4().hex}-{_slug(file_name)}"
        relative = Path(entity_type) / entity_id / stored_name
        target = OBJECT_ATTACHMENT_ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredAttachment(
            storage_driver=self.driver,
            storage_bucket="object-attachments",
            storage_key=str(relative).replace("\\", "/"),
            stored_filename=stored_name,
        )


def get_attachment_storage_adapter(driver: AttachmentStorageDriver | None = None) -> AttachmentStorageAdapter:
    configured = driver or AttachmentStorageDriver(str(os.getenv("ESP_ATTACHMENT_STORAGE_DRIVER", AttachmentStorageDriver.LOCAL.value)).upper())
    if configured == AttachmentStorageDriver.OBJECT:
        return ObjectAttachmentStorageAdapter()
    return LocalAttachmentStorageAdapter()


def infer_attachment_classification(file_name: str, content_type: str | None, fallback: str = "other") -> str:
    lower_name = (file_name or "").lower()
    mime = (content_type or "").lower()
    if lower_name.endswith(".zip") or "zip" in mime:
        return "zip_archive"
    if mime.startswith("image/"):
        return "image" if fallback == "other" else fallback
    return fallback


async def ensure_attachment_type_classifications(db: AsyncSession) -> int:
    created = 0
    for entity_type, rules in CLASSIFICATION_RULES.items():
        limit = DEFAULT_ENTITY_ATTACHMENT_LIMITS.get(entity_type, {"max_files": 10, "max_size_bytes": 20 * 1024 * 1024})
        for classification, config in rules.items():
            existing = await db.scalar(
                select(AttachmentTypeClassification).where(
                    AttachmentTypeClassification.entity_type == entity_type,
                    AttachmentTypeClassification.classification == classification,
                )
            )
            if existing:
                continue
            db.add(
                AttachmentTypeClassification(
                    entity_type=entity_type,
                    classification=classification,
                    allowed_mime_csv=",".join(config.get("mime", ())),
                    allowed_extensions_csv=",".join(config.get("ext", ())),
                    max_size_bytes=int(limit["max_size_bytes"]),
                    max_file_count=int(limit["max_files"]),
                    is_enabled=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
            created += 1
    await db.flush()
    return created


async def _get_current_entity_attachment_count(db: AsyncSession, *, entity_type: str, entity_id: str) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(AttachmentBinding)
        .join(Attachment, Attachment.id == AttachmentBinding.attachment_id)
        .where(
            AttachmentBinding.entity_type == entity_type,
            AttachmentBinding.entity_id == entity_id,
            AttachmentBinding.archived_at.is_(None),
            Attachment.deleted_at.is_(None),
            Attachment.status == AttachmentStatus.ACTIVE,
        )
    )
    return int(count or 0)


async def _validate_classification(db: AsyncSession, *, entity_type: str, classification: str, content_type: str, file_name: str) -> None:
    if classification not in SAFE_ATTACHMENT_TYPES:
        raise HTTPException(status_code=400, detail="invalid_attachment_classification")

    rule = await db.scalar(
        select(AttachmentTypeClassification).where(
            AttachmentTypeClassification.entity_type == entity_type,
            AttachmentTypeClassification.classification == classification,
            AttachmentTypeClassification.is_enabled.is_(True),
        )
    )
    if not rule:
        return

    mime_set = {value.strip().lower() for value in str(rule.allowed_mime_csv or "").split(",") if value.strip()}
    ext_set = {value.strip().lower() for value in str(rule.allowed_extensions_csv or "").split(",") if value.strip()}
    current_mime = (content_type or "").lower()
    current_ext = Path(file_name or "").suffix.lower()
    if mime_set and current_mime not in mime_set:
        raise HTTPException(status_code=400, detail="attachment_mime_not_allowed")
    if ext_set and current_ext not in ext_set:
        raise HTTPException(status_code=400, detail="attachment_extension_not_allowed")


async def create_attachment_for_entity(
    db: AsyncSession,
    *,
    actor: User,
    entity_type: str,
    entity_id: str,
    branch_id: str | None,
    upload: UploadFile,
    classification: str,
    relation_type: str = "primary",
    storage_driver: AttachmentStorageDriver | None = None,
) -> Attachment:
    file_name = str(upload.filename or "").strip()
    if not file_name:
        raise HTTPException(status_code=400, detail="attachment_filename_required")

    content = await upload.read()
    content_type = str(upload.content_type or "application/octet-stream").strip().lower()
    classification_value = infer_attachment_classification(file_name, content_type, classification or "other")
    current_count = await _get_current_entity_attachment_count(db, entity_type=entity_type, entity_id=entity_id)

    try:
        validate_attachment_payload(
            entity_type=entity_type,
            current_count=current_count,
            incoming_files=1,
            file_name=file_name,
            content_type=content_type,
            size_bytes=len(content),
            classification=classification_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await _validate_classification(
        db,
        entity_type=entity_type,
        classification=classification_value,
        content_type=content_type,
        file_name=file_name,
    )

    adapter = get_attachment_storage_adapter(storage_driver)
    stored = adapter.save(entity_type=entity_type, entity_id=entity_id, file_name=file_name, content=content)
    checksum = hashlib.sha256(content).hexdigest()
    attachment = Attachment(
        storage_driver=stored.storage_driver,
        storage_bucket=stored.storage_bucket,
        storage_key=stored.storage_key,
        original_filename=file_name,
        stored_filename=stored.stored_filename,
        content_type=content_type,
        size_bytes=len(content),
        checksum_sha256=checksum,
        classification=classification_value,
        status=AttachmentStatus.ACTIVE,
        malware_status=AttachmentMalwareStatus.PENDING,
        owner_user_id=actor.id,
        created_at=datetime.utcnow(),
    )
    db.add(attachment)
    await db.flush()

    db.add(
        AttachmentBinding(
            attachment_id=attachment.id,
            entity_type=entity_type,
            entity_id=entity_id,
            relation_type=relation_type,
            branch_id=branch_id,
            created_by=actor.id,
            created_at=datetime.utcnow(),
        )
    )
    db.add(
        AttachmentScanJob(
            attachment_id=attachment.id,
            status=AttachmentScanStatus.PENDING,
            scanner_name="hook",
            scheduled_at=datetime.utcnow(),
        )
    )
    await db.flush()
    return attachment


async def list_entity_attachments(db: AsyncSession, *, entity_type: str, entity_id: str) -> list[Attachment]:
    return (
        await db.execute(
            select(Attachment)
            .join(AttachmentBinding, AttachmentBinding.attachment_id == Attachment.id)
            .where(
                AttachmentBinding.entity_type == entity_type,
                AttachmentBinding.entity_id == entity_id,
                AttachmentBinding.archived_at.is_(None),
                Attachment.deleted_at.is_(None),
            )
            .order_by(Attachment.created_at.desc())
        )
    ).scalars().all()


async def archive_entity_attachment(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    attachment_id: str,
) -> Attachment | None:
    binding = await db.scalar(
        select(AttachmentBinding).where(
            AttachmentBinding.attachment_id == attachment_id,
            AttachmentBinding.entity_type == entity_type,
            AttachmentBinding.entity_id == entity_id,
            AttachmentBinding.archived_at.is_(None),
        )
    )
    if not binding:
        return None
    attachment = await db.scalar(select(Attachment).where(Attachment.id == attachment_id, Attachment.deleted_at.is_(None)))
    if not attachment:
        return None

    now = datetime.utcnow()
    binding.archived_at = now

    active_bindings = int(
        await db.scalar(
            select(func.count()).select_from(AttachmentBinding).where(
                AttachmentBinding.attachment_id == attachment_id,
                AttachmentBinding.archived_at.is_(None),
            )
        )
        or 0
    )
    if active_bindings <= 1:
        attachment.status = AttachmentStatus.ARCHIVED
        attachment.archived_at = now
    await db.flush()
    return attachment
