from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_ENTITY_ATTACHMENT_LIMITS = {
    "product": {"max_files": 5, "max_size_bytes": 10 * 1024 * 1024},
    "supplier": {"max_files": 5, "max_size_bytes": 10 * 1024 * 1024},
    "price_record": {"max_files": 5, "max_size_bytes": 10 * 1024 * 1024},
    "verify_request": {"max_files": 5, "max_size_bytes": 10 * 1024 * 1024},
}
FUTURE_ENTITY_DEFAULT_LIMIT = {"max_files": 10, "max_size_bytes": 20 * 1024 * 1024}
MAX_ZIP_SIZE_BYTES = 50 * 1024 * 1024
SAFE_ATTACHMENT_TYPES = {
    "image",
    "quote_document",
    "invoice",
    "chat_proof",
    "supplier_profile",
    "product_reference",
    "zip_archive",
    "other",
}


@dataclass(frozen=True)
class AttachmentValidationResult:
    entity_type: str
    classification: str
    size_bytes: int
    is_zip: bool


def get_entity_attachment_limits(entity_type: str) -> dict[str, int]:
    key = (entity_type or "").strip().lower()
    return DEFAULT_ENTITY_ATTACHMENT_LIMITS.get(key, FUTURE_ENTITY_DEFAULT_LIMIT)


def validate_attachment_payload(
    *,
    entity_type: str,
    current_count: int,
    incoming_files: int,
    file_name: str,
    content_type: str,
    size_bytes: int,
    classification: str,
) -> AttachmentValidationResult:
    limits = get_entity_attachment_limits(entity_type)
    if current_count + incoming_files > limits["max_files"]:
        raise ValueError("attachment_limit_exceeded")
    if size_bytes < 0:
        raise ValueError("invalid_attachment_size")

    suffix = Path(file_name or "").suffix.lower()
    is_zip = suffix == ".zip" or content_type == "application/zip"
    max_size = MAX_ZIP_SIZE_BYTES if is_zip else limits["max_size_bytes"]
    if size_bytes > max_size:
        raise ValueError("attachment_too_large")
    if classification not in SAFE_ATTACHMENT_TYPES:
        raise ValueError("invalid_attachment_classification")

    return AttachmentValidationResult(
        entity_type=(entity_type or "").strip().lower(),
        classification=classification,
        size_bytes=size_bytes,
        is_zip=is_zip,
    )
