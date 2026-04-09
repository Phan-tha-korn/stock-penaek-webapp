from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import orjson
from sqlalchemy import delete, select

from server.config.config_loader import load_master_config, write_master_config
from server.config.paths import app_db_path, backups_root, media_root, repo_root
from server.config.settings import refresh_runtime_settings_from_master_config
from server.db.database import SessionLocal
from server.db.models import (
    Attachment,
    AttachmentBinding,
    AttachmentMalwareStatus,
    AttachmentScanJob,
    AttachmentScanStatus,
    AttachmentStatus,
    AttachmentStorageDriver,
    AttachmentTypeClassification,
    AuditEvent,
    AuditLog,
    AuditSeverity,
    Branch,
    LoginLock,
    Product,
    RefreshSession,
    Role,
    StockAlertState,
    StockStatus,
    StockTransaction,
    Supplier,
    SupplierChangeProposal,
    SupplierContact,
    SupplierLink,
    SupplierPickupPoint,
    SupplierProductLink,
    SupplierProposalStatus,
    SupplierReliabilityBreakdown,
    SupplierReliabilityProfile,
    SupplierReliabilityScore,
    SupplierStatus,
    TxnType,
    User,
    UserBranchScope,
)


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


async def build_backup_payload() -> dict:
    cfg = load_master_config()
    async with SessionLocal() as db:
        branches = (await db.execute(select(Branch))).scalars().all()
        branch_scopes = (await db.execute(select(UserBranchScope))).scalars().all()
        users = (await db.execute(select(User))).scalars().all()
        products = (await db.execute(select(Product))).scalars().all()
        suppliers = (await db.execute(select(Supplier))).scalars().all()
        supplier_contacts = (await db.execute(select(SupplierContact))).scalars().all()
        supplier_links = (await db.execute(select(SupplierLink))).scalars().all()
        supplier_pickup_points = (await db.execute(select(SupplierPickupPoint))).scalars().all()
        supplier_product_links = (await db.execute(select(SupplierProductLink))).scalars().all()
        supplier_reliability_profiles = (await db.execute(select(SupplierReliabilityProfile))).scalars().all()
        supplier_reliability_scores = (await db.execute(select(SupplierReliabilityScore))).scalars().all()
        supplier_reliability_breakdowns = (await db.execute(select(SupplierReliabilityBreakdown))).scalars().all()
        supplier_change_proposals = (await db.execute(select(SupplierChangeProposal))).scalars().all()
        attachments = (await db.execute(select(Attachment))).scalars().all()
        attachment_bindings = (await db.execute(select(AttachmentBinding))).scalars().all()
        attachment_scan_jobs = (await db.execute(select(AttachmentScanJob))).scalars().all()
        attachment_type_classifications = (await db.execute(select(AttachmentTypeClassification))).scalars().all()
        txns = (await db.execute(select(StockTransaction))).scalars().all()
        alerts = (await db.execute(select(StockAlertState))).scalars().all()
        audit_logs = (await db.execute(select(AuditLog))).scalars().all()
        audit_events = (await db.execute(select(AuditEvent))).scalars().all()

    return {
        "meta": {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "format": "stock-penaek-backup-v2",
            "database": {
                "engine": "sqlite",
                "file_name": app_db_path().name,
            },
            "counts": {
                "users": len(users),
                "branches": len(branches),
                "branch_scopes": len(branch_scopes),
                "products": len(products),
                "suppliers": len(suppliers),
                "supplier_contacts": len(supplier_contacts),
                "supplier_links": len(supplier_links),
                "supplier_pickup_points": len(supplier_pickup_points),
                "supplier_product_links": len(supplier_product_links),
                "supplier_reliability_profiles": len(supplier_reliability_profiles),
                "supplier_reliability_scores": len(supplier_reliability_scores),
                "supplier_reliability_breakdowns": len(supplier_reliability_breakdowns),
                "supplier_change_proposals": len(supplier_change_proposals),
                "attachments": len(attachments),
                "attachment_bindings": len(attachment_bindings),
                "attachment_scan_jobs": len(attachment_scan_jobs),
                "attachment_type_classifications": len(attachment_type_classifications),
                "transactions": len(txns),
                "alert_states": len(alerts),
                "audit_logs": len(audit_logs),
                "audit_events": len(audit_events),
            },
        },
        "branches": [
            {
                "id": branch.id,
                "code": branch.code,
                "name": branch.name,
                "description": branch.description,
                "is_default": branch.is_default,
                "is_active": branch.is_active,
                "created_at": _dt(branch.created_at),
                "updated_at": _dt(branch.updated_at),
            }
            for branch in branches
        ],
        "branch_scopes": [
            {
                "id": scope.id,
                "user_id": scope.user_id,
                "branch_id": scope.branch_id,
                "can_view": scope.can_view,
                "can_edit": scope.can_edit,
                "scope_source": scope.scope_source,
                "created_at": _dt(scope.created_at),
                "updated_at": _dt(scope.updated_at),
            }
            for scope in branch_scopes
        ],
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "role": u.role.value,
                "is_active": u.is_active,
                "language": u.language,
                "password_hash": u.password_hash,
                "totp_secret": u.totp_secret,
                "created_at": _dt(u.created_at),
                "updated_at": _dt(u.updated_at),
            }
            for u in users
        ],
        "products": [
            {
                "id": p.id,
                "sku": p.sku,
                "branch_id": p.branch_id,
                "category_id": p.category_id,
                "last_category_id": p.last_category_id,
                "name_th": p.name_th,
                "name_en": p.name_en,
                "category": p.category,
                "type": p.type,
                "unit": p.unit,
                "cost_price": str(p.cost_price),
                "selling_price": str(p.selling_price) if p.selling_price is not None else None,
                "stock_qty": str(p.stock_qty),
                "min_stock": str(p.min_stock),
                "max_stock": str(p.max_stock),
                "status": p.status.value,
                "is_test": p.is_test,
                "supplier": p.supplier,
                "barcode": p.barcode,
                "image_url": p.image_url,
                "notes": p.notes,
                "archived_at": _dt(p.archived_at),
                "deleted_at": _dt(p.deleted_at),
                "delete_reason": p.delete_reason,
                "created_by": p.created_by,
                "created_at": _dt(p.created_at),
                "updated_at": _dt(p.updated_at),
            }
            for p in products
        ],
        "suppliers": [
            {
                "id": supplier.id,
                "branch_id": supplier.branch_id,
                "code": supplier.code,
                "name": supplier.name,
                "normalized_name": supplier.normalized_name,
                "phone": supplier.phone,
                "line_id": supplier.line_id,
                "facebook_url": supplier.facebook_url,
                "website_url": supplier.website_url,
                "address": supplier.address,
                "pickup_notes": supplier.pickup_notes,
                "source_details": supplier.source_details,
                "purchase_history_notes": supplier.purchase_history_notes,
                "reliability_note": supplier.reliability_note,
                "status": supplier.status.value,
                "is_verified": supplier.is_verified,
                "created_by": supplier.created_by,
                "updated_by": supplier.updated_by,
                "archived_at": _dt(supplier.archived_at),
                "deleted_at": _dt(supplier.deleted_at),
                "delete_reason": supplier.delete_reason,
                "created_at": _dt(supplier.created_at),
                "updated_at": _dt(supplier.updated_at),
            }
            for supplier in suppliers
        ],
        "supplier_contacts": [
            {
                "id": row.id,
                "supplier_id": row.supplier_id,
                "contact_type": row.contact_type,
                "label": row.label,
                "value": row.value,
                "is_primary": row.is_primary,
                "sort_order": row.sort_order,
                "created_at": _dt(row.created_at),
                "updated_at": _dt(row.updated_at),
                "archived_at": _dt(row.archived_at),
            }
            for row in supplier_contacts
        ],
        "supplier_links": [
            {
                "id": row.id,
                "supplier_id": row.supplier_id,
                "link_type": row.link_type,
                "label": row.label,
                "url": row.url,
                "is_primary": row.is_primary,
                "sort_order": row.sort_order,
                "created_at": _dt(row.created_at),
                "updated_at": _dt(row.updated_at),
                "archived_at": _dt(row.archived_at),
            }
            for row in supplier_links
        ],
        "supplier_pickup_points": [
            {
                "id": row.id,
                "supplier_id": row.supplier_id,
                "label": row.label,
                "address": row.address,
                "details": row.details,
                "is_primary": row.is_primary,
                "created_at": _dt(row.created_at),
                "updated_at": _dt(row.updated_at),
                "archived_at": _dt(row.archived_at),
            }
            for row in supplier_pickup_points
        ],
        "supplier_product_links": [
            {
                "id": row.id,
                "supplier_id": row.supplier_id,
                "product_id": row.product_id,
                "legacy_supplier_name": row.legacy_supplier_name,
                "is_primary": row.is_primary,
                "linked_by_user_id": row.linked_by_user_id,
                "created_at": _dt(row.created_at),
                "updated_at": _dt(row.updated_at),
                "archived_at": _dt(row.archived_at),
            }
            for row in supplier_product_links
        ],
        "supplier_reliability_profiles": [
            {
                "id": row.id,
                "supplier_id": row.supplier_id,
                "legacy_supplier_name": row.legacy_supplier_name,
                "legacy_supplier_key": row.legacy_supplier_key,
                "overall_score": str(row.overall_score),
                "auto_score": str(row.auto_score),
                "price_competitiveness_score": str(row.price_competitiveness_score),
                "purchase_frequency_score": str(row.purchase_frequency_score),
                "delivery_reliability_score": str(row.delivery_reliability_score),
                "data_completeness_score": str(row.data_completeness_score),
                "verification_confidence_score": str(row.verification_confidence_score),
                "dispute_reject_score": str(row.dispute_reject_score),
                "dev_override_score": str(row.dev_override_score) if row.dev_override_score is not None else None,
                "owner_override_score": str(row.owner_override_score) if row.owner_override_score is not None else None,
                "override_reason": row.override_reason,
                "overridden_by_user_id": row.overridden_by_user_id,
                "created_at": _dt(row.created_at),
                "updated_at": _dt(row.updated_at),
            }
            for row in supplier_reliability_profiles
        ],
        "supplier_reliability_scores": [
            {
                "id": row.id,
                "supplier_id": row.supplier_id,
                "overall_score": str(row.overall_score),
                "auto_score": str(row.auto_score),
                "effective_score": str(row.effective_score),
                "calculated_at": _dt(row.calculated_at),
                "updated_at": _dt(row.updated_at),
            }
            for row in supplier_reliability_scores
        ],
        "supplier_reliability_breakdowns": [
            {
                "id": row.id,
                "supplier_score_id": row.supplier_score_id,
                "metric_key": row.metric_key,
                "score_value": str(row.score_value),
                "weight": str(row.weight),
                "detail_text": row.detail_text,
                "created_at": _dt(row.created_at),
            }
            for row in supplier_reliability_breakdowns
        ],
        "supplier_change_proposals": [
            {
                "id": row.id,
                "supplier_id": row.supplier_id,
                "action": row.action,
                "status": row.status.value,
                "proposed_by_user_id": row.proposed_by_user_id,
                "reviewed_by_user_id": row.reviewed_by_user_id,
                "approved_supplier_id": row.approved_supplier_id,
                "requires_dev_review": row.requires_dev_review,
                "proposed_payload_json": row.proposed_payload_json,
                "current_payload_json": row.current_payload_json,
                "review_note": row.review_note,
                "created_at": _dt(row.created_at),
                "updated_at": _dt(row.updated_at),
                "reviewed_at": _dt(row.reviewed_at),
            }
            for row in supplier_change_proposals
        ],
        "attachments": [
            {
                "id": row.id,
                "storage_driver": row.storage_driver.value,
                "storage_bucket": row.storage_bucket,
                "storage_key": row.storage_key,
                "original_filename": row.original_filename,
                "stored_filename": row.stored_filename,
                "content_type": row.content_type,
                "size_bytes": row.size_bytes,
                "checksum_sha256": row.checksum_sha256,
                "classification": row.classification,
                "status": row.status.value,
                "malware_status": row.malware_status.value,
                "owner_user_id": row.owner_user_id,
                "created_at": _dt(row.created_at),
                "archived_at": _dt(row.archived_at),
                "deleted_at": _dt(row.deleted_at),
            }
            for row in attachments
        ],
        "attachment_bindings": [
            {
                "id": row.id,
                "attachment_id": row.attachment_id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "relation_type": row.relation_type,
                "branch_id": row.branch_id,
                "created_by": row.created_by,
                "created_at": _dt(row.created_at),
                "archived_at": _dt(row.archived_at),
            }
            for row in attachment_bindings
        ],
        "attachment_scan_jobs": [
            {
                "id": row.id,
                "attachment_id": row.attachment_id,
                "status": row.status.value,
                "scanner_name": row.scanner_name,
                "error_message": row.error_message,
                "result_detail": row.result_detail,
                "scheduled_at": _dt(row.scheduled_at),
                "started_at": _dt(row.started_at),
                "completed_at": _dt(row.completed_at),
            }
            for row in attachment_scan_jobs
        ],
        "attachment_type_classifications": [
            {
                "id": row.id,
                "entity_type": row.entity_type,
                "classification": row.classification,
                "allowed_mime_csv": row.allowed_mime_csv,
                "allowed_extensions_csv": row.allowed_extensions_csv,
                "max_size_bytes": row.max_size_bytes,
                "max_file_count": row.max_file_count,
                "is_enabled": row.is_enabled,
                "created_at": _dt(row.created_at),
                "updated_at": _dt(row.updated_at),
            }
            for row in attachment_type_classifications
        ],
        "transactions": [
            {
                "id": t.id,
                "type": t.type.value,
                "product_id": t.product_id,
                "branch_id": t.branch_id,
                "sku": t.sku,
                "qty": str(t.qty),
                "unit_cost": str(t.unit_cost) if t.unit_cost is not None else None,
                "unit_price": str(t.unit_price) if t.unit_price is not None else None,
                "reason": t.reason,
                "approval_required": t.approval_required,
                "approved_by": t.approved_by,
                "created_by": t.created_by,
                "created_at": _dt(t.created_at),
            }
            for t in txns
        ],
        "alert_states": [
            {
                "id": a.id,
                "product_id": a.product_id,
                "last_low_level_pct": a.last_low_level_pct,
                "last_high_level_pct": a.last_high_level_pct,
                "last_pct": str(a.last_pct) if a.last_pct is not None else None,
                "updated_at": _dt(a.updated_at),
            }
            for a in alerts
        ],
        "audit_logs": [
            {
                "id": a.id,
                "actor_user_id": a.actor_user_id,
                "actor_username": a.actor_username,
                "actor_role": a.actor_role.value if a.actor_role else None,
                "action": a.action,
                "entity": a.entity,
                "entity_id": a.entity_id,
                "branch_id": a.branch_id,
                "ip": a.ip,
                "user_agent": a.user_agent,
                "success": a.success,
                "before_json": a.before_json,
                "after_json": a.after_json,
                "message": a.message,
                "created_at": _dt(a.created_at),
            }
            for a in audit_logs
        ],
        "audit_events": [
            {
                "id": event.id,
                "audit_log_id": event.audit_log_id,
                "actor_user_id": event.actor_user_id,
                "actor_username": event.actor_username,
                "actor_role": event.actor_role.value if event.actor_role else None,
                "branch_id": event.branch_id,
                "action": event.action,
                "entity": event.entity,
                "entity_id": event.entity_id,
                "severity": event.severity.value,
                "reason": event.reason,
                "diff_summary": event.diff_summary,
                "metadata_json": event.metadata_json,
                "before_json": event.before_json,
                "after_json": event.after_json,
                "success": event.success,
                "created_at": _dt(event.created_at),
            }
            for event in audit_events
        ],
        "settings": cfg,
    }


async def create_backup_archive(label: str = "manual") -> dict:
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe_label = "".join(ch.lower() if ch.isalnum() else "-" for ch in label).strip("-") or "backup"
    filename = f"stock-penaek-backup-{safe_label}-{ts}.zip"
    path = backups_root() / filename
    payload = await build_backup_payload()
    payload_bytes = orjson.dumps(payload)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("backup/data.json", payload_bytes)
        zf.writestr(
            "backup/manifest.json",
            json.dumps(
                {
                    "format": "stock-penaek-backup-v2",
                    "database_file": app_db_path().name,
                    "created_at": payload["meta"]["created_at"],
                    "label": safe_label,
                    "counts": payload["meta"]["counts"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        zf.writestr("backup/config.json", json.dumps(load_master_config(), ensure_ascii=False, indent=2))

        media = media_root()
        if media.exists():
            for file_path in media.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=str(Path("backup/media") / file_path.relative_to(media)))

    return {
        "file_name": filename,
        "file_path": str(path),
        "size_bytes": path.stat().st_size,
        "counts": payload["meta"]["counts"],
    }


def _extract_backup_json(zip_bytes: bytes) -> tuple[dict, dict | None, list[tuple[str, bytes]]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = set(zf.namelist())
        data_name = "backup/data.json" if "backup/data.json" in names else "data.json"
        config_name = "backup/config.json" if "backup/config.json" in names else "config.json"
        if data_name not in names:
            raise ValueError("backup_data_missing")
        payload = orjson.loads(zf.read(data_name))
        config = None
        if config_name in names:
            config = json.loads(zf.read(config_name).decode("utf-8"))

        media_files: list[tuple[str, bytes]] = []
        for name in zf.namelist():
            if not name.startswith("backup/media/") or name.endswith("/"):
                continue
            media_files.append((name[len("backup/media/") :], zf.read(name)))
        return payload, config, media_files


def preview_backup_archive(zip_bytes: bytes) -> dict:
    payload, config, media_files = _extract_backup_json(zip_bytes)
    meta = dict(payload.get("meta") or {})
    counts = dict(meta.get("counts") or {})
    return {
        "created_at": str(meta.get("created_at") or ""),
        "counts": {
            "branches": int(counts.get("branches") or len(payload.get("branches") or [])),
            "branch_scopes": int(counts.get("branch_scopes") or len(payload.get("branch_scopes") or [])),
            "users": int(counts.get("users") or len(payload.get("users") or [])),
            "products": int(counts.get("products") or len(payload.get("products") or [])),
            "suppliers": int(counts.get("suppliers") or len(payload.get("suppliers") or [])),
            "attachments": int(counts.get("attachments") or len(payload.get("attachments") or [])),
            "transactions": int(counts.get("transactions") or len(payload.get("transactions") or [])),
            "alert_states": int(counts.get("alert_states") or len(payload.get("alert_states") or [])),
            "audit_logs": int(counts.get("audit_logs") or len(payload.get("audit_logs") or [])),
            "audit_events": int(counts.get("audit_events") or len(payload.get("audit_events") or [])),
            "media_files": int(len(media_files)),
        },
        "sheet_id": str((config or {}).get("google_sheets_id") or ((config or {}).get("google_sheets") or {}).get("sheet_id") or ""),
        "app_name": str((config or {}).get("app_name") or ""),
    }


async def restore_backup_archive(zip_bytes: bytes) -> dict:
    payload, config, media_files = _extract_backup_json(zip_bytes)
    branches = payload.get("branches") or []
    branch_scopes = payload.get("branch_scopes") or []
    users = payload.get("users") or []
    products = payload.get("products") or []
    suppliers = payload.get("suppliers") or []
    supplier_contacts = payload.get("supplier_contacts") or []
    supplier_links = payload.get("supplier_links") or []
    supplier_pickup_points = payload.get("supplier_pickup_points") or []
    supplier_product_links = payload.get("supplier_product_links") or []
    supplier_reliability_profiles = payload.get("supplier_reliability_profiles") or []
    supplier_reliability_scores = payload.get("supplier_reliability_scores") or []
    supplier_reliability_breakdowns = payload.get("supplier_reliability_breakdowns") or []
    supplier_change_proposals = payload.get("supplier_change_proposals") or []
    attachments = payload.get("attachments") or []
    attachment_bindings = payload.get("attachment_bindings") or []
    attachment_scan_jobs = payload.get("attachment_scan_jobs") or []
    attachment_type_classifications = payload.get("attachment_type_classifications") or []
    transactions = payload.get("transactions") or []
    alert_states = payload.get("alert_states") or []
    audit_logs = payload.get("audit_logs") or []
    audit_events = payload.get("audit_events") or []

    async with SessionLocal() as db:
        await db.execute(delete(LoginLock))
        await db.execute(delete(RefreshSession))
        await db.execute(delete(AttachmentScanJob))
        await db.execute(delete(AttachmentBinding))
        await db.execute(delete(Attachment))
        await db.execute(delete(AttachmentTypeClassification))
        await db.execute(delete(SupplierReliabilityBreakdown))
        await db.execute(delete(SupplierReliabilityScore))
        await db.execute(delete(SupplierChangeProposal))
        await db.execute(delete(SupplierReliabilityProfile))
        await db.execute(delete(SupplierProductLink))
        await db.execute(delete(SupplierPickupPoint))
        await db.execute(delete(SupplierLink))
        await db.execute(delete(SupplierContact))
        await db.execute(delete(UserBranchScope))
        await db.execute(delete(StockAlertState))
        await db.execute(delete(StockTransaction))
        await db.execute(delete(Product))
        await db.execute(delete(Supplier))
        await db.execute(delete(AuditEvent))
        await db.execute(delete(AuditLog))
        await db.execute(delete(User))
        await db.execute(delete(Branch))

        for raw in branches:
            db.add(
                Branch(
                    id=str(raw["id"]),
                    code=str(raw.get("code") or ""),
                    name=str(raw.get("name") or ""),
                    description=str(raw.get("description") or ""),
                    is_default=bool(raw.get("is_default", False)),
                    is_active=bool(raw.get("is_active", True)),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in users:
            db.add(
                User(
                    id=str(raw["id"]),
                    username=str(raw.get("username") or ""),
                    display_name=str(raw.get("display_name") or ""),
                    role=Role(str(raw.get("role") or Role.STOCK.value)),
                    is_active=bool(raw.get("is_active", True)),
                    language=str(raw.get("language") or "th"),
                    password_hash=str(raw.get("password_hash") or ""),
                    totp_secret=raw.get("totp_secret"),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in branch_scopes:
            db.add(
                UserBranchScope(
                    id=str(raw["id"]),
                    user_id=str(raw.get("user_id") or ""),
                    branch_id=str(raw.get("branch_id") or ""),
                    can_view=bool(raw.get("can_view", True)),
                    can_edit=bool(raw.get("can_edit", False)),
                    scope_source=str(raw.get("scope_source") or "system"),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in products:
            db.add(
                Product(
                    id=str(raw["id"]),
                    sku=str(raw.get("sku") or ""),
                    branch_id=raw.get("branch_id"),
                    category_id=raw.get("category_id"),
                    last_category_id=raw.get("last_category_id"),
                    name_th=str(raw.get("name_th") or ""),
                    name_en=str(raw.get("name_en") or ""),
                    category=str(raw.get("category") or ""),
                    type=str(raw.get("type") or ""),
                    unit=str(raw.get("unit") or ""),
                    cost_price=float(raw.get("cost_price") or 0),
                    selling_price=float(raw["selling_price"]) if raw.get("selling_price") not in (None, "") else None,
                    stock_qty=float(raw.get("stock_qty") or 0),
                    min_stock=float(raw.get("min_stock") or 0),
                    max_stock=float(raw.get("max_stock") or 0),
                    status=StockStatus(str(raw.get("status") or StockStatus.NORMAL.value)),
                    is_test=bool(raw.get("is_test", False)),
                    supplier=str(raw.get("supplier") or ""),
                    barcode=str(raw.get("barcode") or ""),
                    image_url=raw.get("image_url"),
                    notes=str(raw.get("notes") or ""),
                    archived_at=_parse_dt(raw.get("archived_at")),
                    deleted_at=_parse_dt(raw.get("deleted_at")),
                    delete_reason=raw.get("delete_reason"),
                    created_by=str(raw.get("created_by") or ""),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in suppliers:
            db.add(
                Supplier(
                    id=str(raw["id"]),
                    branch_id=raw.get("branch_id"),
                    code=str(raw.get("code") or ""),
                    name=str(raw.get("name") or ""),
                    normalized_name=str(raw.get("normalized_name") or ""),
                    phone=str(raw.get("phone") or ""),
                    line_id=str(raw.get("line_id") or ""),
                    facebook_url=str(raw.get("facebook_url") or ""),
                    website_url=str(raw.get("website_url") or ""),
                    address=str(raw.get("address") or ""),
                    pickup_notes=str(raw.get("pickup_notes") or ""),
                    source_details=str(raw.get("source_details") or ""),
                    purchase_history_notes=str(raw.get("purchase_history_notes") or ""),
                    reliability_note=str(raw.get("reliability_note") or ""),
                    status=SupplierStatus(str(raw.get("status") or SupplierStatus.ACTIVE.value)),
                    is_verified=bool(raw.get("is_verified", False)),
                    created_by=raw.get("created_by"),
                    updated_by=raw.get("updated_by"),
                    archived_at=_parse_dt(raw.get("archived_at")),
                    deleted_at=_parse_dt(raw.get("deleted_at")),
                    delete_reason=raw.get("delete_reason"),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in supplier_contacts:
            db.add(
                SupplierContact(
                    id=str(raw["id"]),
                    supplier_id=str(raw.get("supplier_id") or ""),
                    contact_type=str(raw.get("contact_type") or "other"),
                    label=str(raw.get("label") or ""),
                    value=str(raw.get("value") or ""),
                    is_primary=bool(raw.get("is_primary", False)),
                    sort_order=int(raw.get("sort_order") or 0),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                    archived_at=_parse_dt(raw.get("archived_at")),
                )
            )

        for raw in supplier_links:
            db.add(
                SupplierLink(
                    id=str(raw["id"]),
                    supplier_id=str(raw.get("supplier_id") or ""),
                    link_type=str(raw.get("link_type") or "other"),
                    label=str(raw.get("label") or ""),
                    url=str(raw.get("url") or ""),
                    is_primary=bool(raw.get("is_primary", False)),
                    sort_order=int(raw.get("sort_order") or 0),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                    archived_at=_parse_dt(raw.get("archived_at")),
                )
            )

        for raw in supplier_pickup_points:
            db.add(
                SupplierPickupPoint(
                    id=str(raw["id"]),
                    supplier_id=str(raw.get("supplier_id") or ""),
                    label=str(raw.get("label") or ""),
                    address=str(raw.get("address") or ""),
                    details=str(raw.get("details") or ""),
                    is_primary=bool(raw.get("is_primary", False)),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                    archived_at=_parse_dt(raw.get("archived_at")),
                )
            )

        for raw in supplier_product_links:
            db.add(
                SupplierProductLink(
                    id=str(raw["id"]),
                    supplier_id=str(raw.get("supplier_id") or ""),
                    product_id=str(raw.get("product_id") or ""),
                    legacy_supplier_name=str(raw.get("legacy_supplier_name") or ""),
                    is_primary=bool(raw.get("is_primary", False)),
                    linked_by_user_id=raw.get("linked_by_user_id"),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                    archived_at=_parse_dt(raw.get("archived_at")),
                )
            )

        for raw in supplier_reliability_profiles:
            db.add(
                SupplierReliabilityProfile(
                    id=str(raw["id"]),
                    supplier_id=raw.get("supplier_id"),
                    legacy_supplier_name=str(raw.get("legacy_supplier_name") or ""),
                    legacy_supplier_key=str(raw.get("legacy_supplier_key") or ""),
                    overall_score=float(raw.get("overall_score") or 0),
                    auto_score=float(raw.get("auto_score") or 0),
                    price_competitiveness_score=float(raw.get("price_competitiveness_score") or 0),
                    purchase_frequency_score=float(raw.get("purchase_frequency_score") or 0),
                    delivery_reliability_score=float(raw.get("delivery_reliability_score") or 0),
                    data_completeness_score=float(raw.get("data_completeness_score") or 0),
                    verification_confidence_score=float(raw.get("verification_confidence_score") or 0),
                    dispute_reject_score=float(raw.get("dispute_reject_score") or 0),
                    dev_override_score=float(raw["dev_override_score"]) if raw.get("dev_override_score") not in (None, "") else None,
                    owner_override_score=float(raw["owner_override_score"]) if raw.get("owner_override_score") not in (None, "") else None,
                    override_reason=str(raw.get("override_reason") or ""),
                    overridden_by_user_id=raw.get("overridden_by_user_id"),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in supplier_reliability_scores:
            db.add(
                SupplierReliabilityScore(
                    id=str(raw["id"]),
                    supplier_id=str(raw.get("supplier_id") or ""),
                    overall_score=float(raw.get("overall_score") or 0),
                    auto_score=float(raw.get("auto_score") or 0),
                    effective_score=float(raw.get("effective_score") or 0),
                    calculated_at=_parse_dt(raw.get("calculated_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in supplier_reliability_breakdowns:
            db.add(
                SupplierReliabilityBreakdown(
                    id=str(raw["id"]),
                    supplier_score_id=str(raw.get("supplier_score_id") or ""),
                    metric_key=str(raw.get("metric_key") or ""),
                    score_value=float(raw.get("score_value") or 0),
                    weight=float(raw.get("weight") or 0),
                    detail_text=str(raw.get("detail_text") or ""),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                )
            )

        for raw in supplier_change_proposals:
            db.add(
                SupplierChangeProposal(
                    id=str(raw["id"]),
                    supplier_id=raw.get("supplier_id"),
                    action=str(raw.get("action") or ""),
                    status=SupplierProposalStatus(str(raw.get("status") or SupplierProposalStatus.PENDING.value)),
                    proposed_by_user_id=raw.get("proposed_by_user_id"),
                    reviewed_by_user_id=raw.get("reviewed_by_user_id"),
                    approved_supplier_id=raw.get("approved_supplier_id"),
                    requires_dev_review=bool(raw.get("requires_dev_review", True)),
                    proposed_payload_json=raw.get("proposed_payload_json"),
                    current_payload_json=raw.get("current_payload_json"),
                    review_note=str(raw.get("review_note") or ""),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                    reviewed_at=_parse_dt(raw.get("reviewed_at")),
                )
            )

        for raw in attachments:
            db.add(
                Attachment(
                    id=str(raw["id"]),
                    storage_driver=AttachmentStorageDriver(str(raw.get("storage_driver") or AttachmentStorageDriver.LOCAL.value)),
                    storage_bucket=str(raw.get("storage_bucket") or ""),
                    storage_key=str(raw.get("storage_key") or ""),
                    original_filename=str(raw.get("original_filename") or ""),
                    stored_filename=str(raw.get("stored_filename") or ""),
                    content_type=str(raw.get("content_type") or ""),
                    size_bytes=int(raw.get("size_bytes") or 0),
                    checksum_sha256=str(raw.get("checksum_sha256") or ""),
                    classification=str(raw.get("classification") or "other"),
                    status=AttachmentStatus(str(raw.get("status") or AttachmentStatus.ACTIVE.value)),
                    malware_status=AttachmentMalwareStatus(str(raw.get("malware_status") or AttachmentMalwareStatus.PENDING.value)),
                    owner_user_id=raw.get("owner_user_id"),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    archived_at=_parse_dt(raw.get("archived_at")),
                    deleted_at=_parse_dt(raw.get("deleted_at")),
                )
            )

        for raw in attachment_bindings:
            db.add(
                AttachmentBinding(
                    id=str(raw["id"]),
                    attachment_id=str(raw.get("attachment_id") or ""),
                    entity_type=str(raw.get("entity_type") or ""),
                    entity_id=str(raw.get("entity_id") or ""),
                    relation_type=str(raw.get("relation_type") or "primary"),
                    branch_id=raw.get("branch_id"),
                    created_by=raw.get("created_by"),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    archived_at=_parse_dt(raw.get("archived_at")),
                )
            )

        for raw in attachment_scan_jobs:
            db.add(
                AttachmentScanJob(
                    id=str(raw["id"]),
                    attachment_id=str(raw.get("attachment_id") or ""),
                    status=AttachmentScanStatus(str(raw.get("status") or AttachmentScanStatus.PENDING.value)),
                    scanner_name=str(raw.get("scanner_name") or "hook"),
                    error_message=str(raw.get("error_message") or ""),
                    result_detail=str(raw.get("result_detail") or ""),
                    scheduled_at=_parse_dt(raw.get("scheduled_at")) or datetime.utcnow(),
                    started_at=_parse_dt(raw.get("started_at")),
                    completed_at=_parse_dt(raw.get("completed_at")),
                )
            )

        for raw in attachment_type_classifications:
            db.add(
                AttachmentTypeClassification(
                    id=str(raw["id"]),
                    entity_type=str(raw.get("entity_type") or ""),
                    classification=str(raw.get("classification") or ""),
                    allowed_mime_csv=str(raw.get("allowed_mime_csv") or ""),
                    allowed_extensions_csv=str(raw.get("allowed_extensions_csv") or ""),
                    max_size_bytes=int(raw.get("max_size_bytes") or 0),
                    max_file_count=int(raw.get("max_file_count") or 0),
                    is_enabled=bool(raw.get("is_enabled", True)),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in transactions:
            db.add(
                StockTransaction(
                    id=str(raw["id"]),
                    type=TxnType(str(raw.get("type") or TxnType.ADJUST.value)),
                    product_id=str(raw.get("product_id") or ""),
                    branch_id=raw.get("branch_id"),
                    sku=str(raw.get("sku") or ""),
                    qty=float(raw.get("qty") or 0),
                    unit_cost=float(raw["unit_cost"]) if raw.get("unit_cost") not in (None, "") else None,
                    unit_price=float(raw["unit_price"]) if raw.get("unit_price") not in (None, "") else None,
                    reason=str(raw.get("reason") or ""),
                    approval_required=bool(raw.get("approval_required", False)),
                    approved_by=raw.get("approved_by"),
                    created_by=str(raw.get("created_by") or ""),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                )
            )

        for raw in alert_states:
            db.add(
                StockAlertState(
                    id=str(raw["id"]),
                    product_id=str(raw.get("product_id") or ""),
                    last_low_level_pct=raw.get("last_low_level_pct"),
                    last_high_level_pct=raw.get("last_high_level_pct"),
                    last_pct=float(raw["last_pct"]) if raw.get("last_pct") not in (None, "") else None,
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in audit_logs:
            role_value = raw.get("actor_role")
            db.add(
                AuditLog(
                    id=str(raw["id"]),
                    actor_user_id=raw.get("actor_user_id"),
                    actor_username=raw.get("actor_username"),
                    actor_role=Role(str(role_value)) if role_value else None,
                    action=str(raw.get("action") or ""),
                    entity=str(raw.get("entity") or ""),
                    entity_id=raw.get("entity_id"),
                    branch_id=raw.get("branch_id"),
                    ip=raw.get("ip"),
                    user_agent=raw.get("user_agent"),
                    success=bool(raw.get("success", True)),
                    before_json=raw.get("before_json"),
                    after_json=raw.get("after_json"),
                    message=str(raw.get("message") or ""),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                )
            )

        for raw in audit_events:
            role_value = raw.get("actor_role")
            db.add(
                AuditEvent(
                    id=str(raw["id"]),
                    audit_log_id=raw.get("audit_log_id"),
                    actor_user_id=raw.get("actor_user_id"),
                    actor_username=raw.get("actor_username"),
                    actor_role=Role(str(role_value)) if role_value else None,
                    branch_id=raw.get("branch_id"),
                    action=str(raw.get("action") or ""),
                    entity=str(raw.get("entity") or ""),
                    entity_id=raw.get("entity_id"),
                    severity=AuditSeverity(str(raw.get("severity") or "info")),
                    reason=str(raw.get("reason") or ""),
                    diff_summary=str(raw.get("diff_summary") or ""),
                    metadata_json=raw.get("metadata_json"),
                    before_json=raw.get("before_json"),
                    after_json=raw.get("after_json"),
                    success=bool(raw.get("success", True)),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                )
            )

        await db.commit()

    media = media_root()
    if media.exists():
        shutil.rmtree(media, ignore_errors=True)
    media.mkdir(parents=True, exist_ok=True)
    for rel_path, data in media_files:
        target = media / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    if isinstance(config, dict):
        write_master_config(config)
        refresh_runtime_settings_from_master_config()

    return {
        "branches": len(branches),
        "branch_scopes": len(branch_scopes),
        "users": len(users),
        "products": len(products),
        "suppliers": len(suppliers),
        "supplier_contacts": len(supplier_contacts),
        "supplier_links": len(supplier_links),
        "supplier_pickup_points": len(supplier_pickup_points),
        "supplier_product_links": len(supplier_product_links),
        "supplier_reliability_profiles": len(supplier_reliability_profiles),
        "supplier_reliability_scores": len(supplier_reliability_scores),
        "supplier_reliability_breakdowns": len(supplier_reliability_breakdowns),
        "supplier_change_proposals": len(supplier_change_proposals),
        "attachments": len(attachments),
        "attachment_bindings": len(attachment_bindings),
        "attachment_scan_jobs": len(attachment_scan_jobs),
        "attachment_type_classifications": len(attachment_type_classifications),
        "transactions": len(transactions),
        "alert_states": len(alert_states),
        "audit_logs": len(audit_logs),
        "audit_events": len(audit_events),
        "media_files": len(media_files),
    }
