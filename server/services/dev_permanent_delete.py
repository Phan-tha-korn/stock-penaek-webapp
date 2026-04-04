from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.config.paths import backups_root, repo_root, storage_root
from server.db.models import (
    Attachment,
    AttachmentBinding,
    AttachmentScanJob,
    AttachmentStorageDriver,
    AttachmentTypeClassification,
    AuditEvent,
    AuditLog,
    Branch,
    CanonicalGroupMember,
    CanonicalProductGroup,
    CatalogSearchDocument,
    CostFormula,
    CostFormulaVersion,
    EntityArchive,
    ExchangeRateSnapshot,
    LoginLock,
    MatchingDependencyCheck,
    MatchingOperation,
    MatchingOperationGroupState,
    MatchingOperationMembershipState,
    NotificationDelivery,
    NotificationEvent,
    NotificationFailure,
    NotificationOutbox,
    NotificationPreference,
    NotificationTemplate,
    PriceRecord,
    PriceSearchProjection,
    Product,
    ProductAlias,
    ProductCategory,
    ProductSpec,
    ProductTagLink,
    RefreshSession,
    ReportSnapshot,
    ReportSnapshotItem,
    ReportSnapshotLink,
    StockAlertState,
    StockTransaction,
    Supplier,
    SupplierChangeProposal,
    SupplierContact,
    SupplierLink,
    SupplierPickupPoint,
    SupplierProductLink,
    SupplierReliabilityBreakdown,
    SupplierReliabilityProfile,
    SupplierReliabilityScore,
    Tag,
    User,
    UserBranchScope,
    VerificationAction,
    VerificationAssignment,
    VerificationDependencyWarning,
    VerificationEscalation,
    VerificationQueueProjection,
    VerificationRequest,
    VerificationRequestItem,
)
from server.services.attachments import ATTACHMENT_ROOT, LOCAL_ATTACHMENT_ROOT, OBJECT_ATTACHMENT_ROOT
from server.services.media_store import MEDIA_ROOT


SAFE_SCOPES = (
    "products",
    "suppliers",
    "pricing",
    "matching",
    "verification",
    "notifications",
    "attachments",
    "reports",
    "logs",
    "system_access",
    "backups",
)
DANGEROUS_SCOPES = ("users", "branches")
ALL_SCOPES = SAFE_SCOPES + DANGEROUS_SCOPES
ENTITY_BINDING_TYPES_BY_REF = {
    "product": ["product"],
    "supplier": ["supplier"],
    "price_record": ["price_record"],
    "verification_request": ["verify_request", "verification_request"],
}


def normalize_tokens(values: Sequence[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        token = str(raw or "").strip()
        if not token:
            continue
        folded = token.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        out.append(token)
    return out


def _inc(counter: dict[str, int], key: str, amount: int) -> None:
    if amount <= 0:
        return
    counter[key] = int(counter.get(key, 0)) + int(amount)


def _folded(values: Sequence[str]) -> set[str]:
    return {value.casefold() for value in values if value}


async def _collect_string_rows(db: AsyncSession, stmt) -> list[tuple[str, ...]]:
    return [tuple(str(v or "") for v in row) for row in (await db.execute(stmt)).all()]


async def _resolve_products(db: AsyncSession, refs: Sequence[str]) -> tuple[list[str], list[str]]:
    tokens = normalize_tokens(refs)
    if not tokens:
        return [], []
    folded = _folded(tokens)
    rows = await _collect_string_rows(
        db,
        select(Product.id, Product.sku).where(
            or_(
                func.lower(Product.id).in_(folded),
                func.lower(Product.sku).in_(folded),
            )
        ),
    )
    ids: list[str] = []
    matched: set[str] = set()
    for product_id, sku in rows:
        ids.append(product_id)
        matched.add(product_id.casefold())
        matched.add(sku.casefold())
    return ids, [token for token in tokens if token.casefold() not in matched]


async def _resolve_suppliers(db: AsyncSession, refs: Sequence[str]) -> tuple[list[str], list[str]]:
    tokens = normalize_tokens(refs)
    if not tokens:
        return [], []
    folded = _folded(tokens)
    rows = await _collect_string_rows(
        db,
        select(Supplier.id, Supplier.code, Supplier.name, Supplier.normalized_name).where(
            or_(
                func.lower(Supplier.id).in_(folded),
                func.lower(Supplier.code).in_(folded),
                func.lower(Supplier.name).in_(folded),
                func.lower(Supplier.normalized_name).in_(folded),
            )
        ),
    )
    ids: list[str] = []
    matched: set[str] = set()
    for supplier_id, code, name, normalized_name in rows:
        ids.append(supplier_id)
        matched.update({supplier_id.casefold(), code.casefold(), name.casefold(), normalized_name.casefold()})
    return ids, [token for token in tokens if token.casefold() not in matched]


async def _resolve_categories(db: AsyncSession, refs: Sequence[str]) -> tuple[list[str], list[str]]:
    tokens = normalize_tokens(refs)
    if not tokens:
        return [], []
    folded = _folded(tokens)
    rows = await _collect_string_rows(
        db,
        select(ProductCategory.id, ProductCategory.name).where(
            or_(
                func.lower(ProductCategory.id).in_(folded),
                func.lower(ProductCategory.name).in_(folded),
            )
        ),
    )
    ids: list[str] = []
    matched: set[str] = set()
    for category_id, name in rows:
        ids.append(category_id)
        matched.update({category_id.casefold(), name.casefold()})
    return ids, [token for token in tokens if token.casefold() not in matched]


async def _resolve_price_records(db: AsyncSession, refs: Sequence[str]) -> tuple[list[str], list[str]]:
    tokens = normalize_tokens(refs)
    if not tokens:
        return [], []
    folded = _folded(tokens)
    rows = await _collect_string_rows(
        db,
        select(PriceRecord.id).where(func.lower(PriceRecord.id).in_(folded)),
    )
    ids = [row[0] for row in rows]
    matched = {value.casefold() for value in ids}
    return ids, [token for token in tokens if token.casefold() not in matched]


async def _resolve_verification_requests(db: AsyncSession, refs: Sequence[str]) -> tuple[list[str], list[str]]:
    tokens = normalize_tokens(refs)
    if not tokens:
        return [], []
    folded = _folded(tokens)
    rows = await _collect_string_rows(
        db,
        select(VerificationRequest.id, VerificationRequest.request_code).where(
            or_(
                func.lower(VerificationRequest.id).in_(folded),
                func.lower(VerificationRequest.request_code).in_(folded),
            )
        ),
    )
    ids: list[str] = []
    matched: set[str] = set()
    for request_id, request_code in rows:
        ids.append(request_id)
        matched.update({request_id.casefold(), request_code.casefold()})
    return ids, [token for token in tokens if token.casefold() not in matched]


async def _resolve_attachments(db: AsyncSession, refs: Sequence[str]) -> tuple[list[str], list[str]]:
    tokens = normalize_tokens(refs)
    if not tokens:
        return [], []
    folded = _folded(tokens)
    rows = await _collect_string_rows(
        db,
        select(Attachment.id, Attachment.storage_key).where(
            or_(
                func.lower(Attachment.id).in_(folded),
                func.lower(Attachment.storage_key).in_(folded),
            )
        ),
    )
    ids: list[str] = []
    matched: set[str] = set()
    for attachment_id, storage_key in rows:
        ids.append(attachment_id)
        matched.update({attachment_id.casefold(), storage_key.casefold()})
    return ids, [token for token in tokens if token.casefold() not in matched]


async def _delete_stmt(db: AsyncSession, stmt, counts: dict[str, int], key: str) -> int:
    result = await db.execute(stmt)
    deleted = int(result.rowcount or 0)
    _inc(counts, key, deleted)
    return deleted


async def _update_stmt(db: AsyncSession, stmt, counts: dict[str, int], key: str) -> int:
    result = await db.execute(stmt)
    updated = int(result.rowcount or 0)
    _inc(counts, key, updated)
    return updated


def _safe_unlink(path: Path) -> bool:
    try:
        if path.exists() and path.is_file():
            path.unlink()
            return True
    except Exception:
        return False
    return False


def _count_tree(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.rglob("*"))


def _reset_directory(path: Path) -> int:
    count = _count_tree(path)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return count


async def _delete_attachment_files(rows: Sequence[tuple[str, str]]) -> int:
    deleted = 0
    for driver, storage_key in rows:
        if not storage_key:
            continue
        base = LOCAL_ATTACHMENT_ROOT if driver == AttachmentStorageDriver.LOCAL.value else OBJECT_ATTACHMENT_ROOT
        target = base / storage_key.replace("/", "\\")
        if _safe_unlink(target):
            deleted += 1
    return deleted


def _product_media_path(image_url: str | None) -> Path | None:
    if not image_url:
        return None
    value = str(image_url).strip()
    if not value.startswith("/media/"):
        return None
    return repo_root() / value.lstrip("/").replace("/", "\\")


async def _delete_product_media(rows: Sequence[tuple[str, str]]) -> int:
    deleted = 0
    for _, image_url in rows:
        target = _product_media_path(image_url)
        if target and _safe_unlink(target):
            deleted += 1
    return deleted


async def _delete_orphan_attachments(db: AsyncSession, candidate_ids: Sequence[str], counts: dict[str, int], filesystem: dict[str, int]) -> int:
    tokens = normalize_tokens(candidate_ids)
    if not tokens:
        return 0
    rows = await _collect_string_rows(
        db,
        select(Attachment.id, Attachment.storage_driver, Attachment.storage_key)
        .outerjoin(AttachmentBinding, AttachmentBinding.attachment_id == Attachment.id)
        .where(Attachment.id.in_(tokens))
        .group_by(Attachment.id, Attachment.storage_driver, Attachment.storage_key)
        .having(func.count(AttachmentBinding.id) == 0),
    )
    if not rows:
        return 0
    attachment_ids = [row[0] for row in rows]
    await _delete_stmt(db, delete(AttachmentScanJob).where(AttachmentScanJob.attachment_id.in_(attachment_ids)), counts, "attachment_scan_jobs")
    await _delete_stmt(db, delete(Attachment).where(Attachment.id.in_(attachment_ids)), counts, "attachments")
    deleted_files = await _delete_attachment_files([(row[1], row[2]) for row in rows])
    _inc(filesystem, "attachment_files", deleted_files)
    return len(attachment_ids)


async def _delete_attachment_bindings_for_entities(
    db: AsyncSession,
    *,
    entity_types: Sequence[str],
    entity_ids: Sequence[str],
    counts: dict[str, int],
    filesystem: dict[str, int],
) -> None:
    ids = normalize_tokens(entity_ids)
    types = normalize_tokens(entity_types)
    if not ids or not types:
        return
    attachment_ids = [
        row[0]
        for row in await _collect_string_rows(
            db,
            select(AttachmentBinding.attachment_id).where(
                AttachmentBinding.entity_type.in_(types),
                AttachmentBinding.entity_id.in_(ids),
            ),
        )
    ]
    await _delete_stmt(
        db,
        delete(AttachmentBinding).where(
            AttachmentBinding.entity_type.in_(types),
            AttachmentBinding.entity_id.in_(ids),
        ),
        counts,
        "attachment_bindings",
    )
    await _delete_orphan_attachments(db, attachment_ids, counts, filesystem)


async def _delete_price_records_by_ids(
    db: AsyncSession,
    price_record_ids: Sequence[str],
    counts: dict[str, int],
    filesystem: dict[str, int],
) -> list[str]:
    ids = normalize_tokens(price_record_ids)
    if not ids:
        return []
    await _update_stmt(
        db,
        update(CatalogSearchDocument)
        .where(
            or_(
                CatalogSearchDocument.latest_price_record_id.in_(ids),
                CatalogSearchDocument.cheapest_active_price_record_id.in_(ids),
            )
        )
        .values(
            latest_price_record_id=None,
            latest_effective_at=None,
            latest_normalized_amount_thb=None,
            latest_final_total_cost_thb=None,
            cheapest_active_price_record_id=None,
            cheapest_active_normalized_amount_thb=None,
            cheapest_active_final_total_cost_thb=None,
            active_price_count=0,
        ),
        counts,
        "catalog_search_documents_cleared",
    )
    await _delete_stmt(db, delete(PriceSearchProjection).where(PriceSearchProjection.price_record_id.in_(ids)), counts, "price_search_projections")
    await _update_stmt(
        db,
        update(PriceRecord).where(PriceRecord.replaced_by_price_record_id.in_(ids)).values(replaced_by_price_record_id=None),
        counts,
        "price_records_detached",
    )
    await _delete_attachment_bindings_for_entities(
        db,
        entity_types=ENTITY_BINDING_TYPES_BY_REF["price_record"],
        entity_ids=ids,
        counts=counts,
        filesystem=filesystem,
    )
    await _delete_stmt(db, delete(PriceRecord).where(PriceRecord.id.in_(ids)), counts, "price_records")
    return ids


async def _delete_matching_for_products(db: AsyncSession, product_ids: Sequence[str], counts: dict[str, int]) -> None:
    ids = normalize_tokens(product_ids)
    if not ids:
        return
    await _delete_stmt(
        db,
        delete(MatchingOperationMembershipState).where(MatchingOperationMembershipState.product_id.in_(ids)),
        counts,
        "matching_operation_membership_states",
    )
    await _delete_stmt(db, delete(CanonicalGroupMember).where(CanonicalGroupMember.product_id.in_(ids)), counts, "canonical_group_members")


async def _prune_orphan_tags(db: AsyncSession, counts: dict[str, int]) -> None:
    await _delete_stmt(
        db,
        delete(Tag).where(
            ~Tag.id.in_(select(ProductTagLink.tag_id))
        ),
        counts,
        "tags",
    )


async def _delete_products_by_ids(
    db: AsyncSession,
    product_ids: Sequence[str],
    counts: dict[str, int],
    filesystem: dict[str, int],
) -> list[str]:
    ids = normalize_tokens(product_ids)
    if not ids:
        return []
    media_rows = await _collect_string_rows(db, select(Product.id, Product.image_url).where(Product.id.in_(ids)))
    price_ids = [
        row[0]
        for row in await _collect_string_rows(db, select(PriceRecord.id).where(PriceRecord.product_id.in_(ids)))
    ]
    if price_ids:
        await _delete_price_records_by_ids(db, price_ids, counts, filesystem)
    await _delete_attachment_bindings_for_entities(
        db,
        entity_types=ENTITY_BINDING_TYPES_BY_REF["product"],
        entity_ids=ids,
        counts=counts,
        filesystem=filesystem,
    )
    await _delete_stmt(db, delete(StockAlertState).where(StockAlertState.product_id.in_(ids)), counts, "stock_alert_states")
    await _delete_stmt(db, delete(StockTransaction).where(StockTransaction.product_id.in_(ids)), counts, "stock_transactions")
    await _delete_stmt(db, delete(ProductTagLink).where(ProductTagLink.product_id.in_(ids)), counts, "product_tag_links")
    await _delete_stmt(db, delete(ProductAlias).where(ProductAlias.product_id.in_(ids)), counts, "product_aliases")
    await _delete_stmt(db, delete(ProductSpec).where(ProductSpec.product_id.in_(ids)), counts, "product_specs")
    await _delete_stmt(db, delete(SupplierProductLink).where(SupplierProductLink.product_id.in_(ids)), counts, "supplier_product_links")
    await _delete_matching_for_products(db, ids, counts)
    await _delete_stmt(db, delete(CatalogSearchDocument).where(CatalogSearchDocument.product_id.in_(ids)), counts, "catalog_search_documents")
    await _delete_stmt(db, delete(PriceSearchProjection).where(PriceSearchProjection.product_id.in_(ids)), counts, "price_search_projections")
    await _delete_stmt(db, delete(Product).where(Product.id.in_(ids)), counts, "products")
    await _prune_orphan_tags(db, counts)
    _inc(filesystem, "product_media_files", await _delete_product_media(media_rows))
    return ids


async def _delete_suppliers_by_ids(
    db: AsyncSession,
    supplier_ids: Sequence[str],
    counts: dict[str, int],
    filesystem: dict[str, int],
) -> list[str]:
    ids = normalize_tokens(supplier_ids)
    if not ids:
        return []
    price_ids = [
        row[0]
        for row in await _collect_string_rows(db, select(PriceRecord.id).where(PriceRecord.supplier_id.in_(ids)))
    ]
    if price_ids:
        await _delete_price_records_by_ids(db, price_ids, counts, filesystem)
    await _delete_attachment_bindings_for_entities(
        db,
        entity_types=ENTITY_BINDING_TYPES_BY_REF["supplier"],
        entity_ids=ids,
        counts=counts,
        filesystem=filesystem,
    )
    await _delete_stmt(
        db,
        delete(SupplierReliabilityBreakdown).where(
            SupplierReliabilityBreakdown.supplier_score_id.in_(
                select(SupplierReliabilityScore.id).where(SupplierReliabilityScore.supplier_id.in_(ids))
            )
        ),
        counts,
        "supplier_reliability_breakdowns",
    )
    await _delete_stmt(db, delete(SupplierReliabilityScore).where(SupplierReliabilityScore.supplier_id.in_(ids)), counts, "supplier_reliability_scores")
    await _delete_stmt(
        db,
        delete(SupplierChangeProposal).where(
            or_(
                SupplierChangeProposal.supplier_id.in_(ids),
                SupplierChangeProposal.approved_supplier_id.in_(ids),
            )
        ),
        counts,
        "supplier_change_proposals",
    )
    await _delete_stmt(db, delete(SupplierReliabilityProfile).where(SupplierReliabilityProfile.supplier_id.in_(ids)), counts, "supplier_reliability_profiles")
    await _delete_stmt(db, delete(SupplierProductLink).where(SupplierProductLink.supplier_id.in_(ids)), counts, "supplier_product_links")
    await _delete_stmt(db, delete(SupplierPickupPoint).where(SupplierPickupPoint.supplier_id.in_(ids)), counts, "supplier_pickup_points")
    await _delete_stmt(db, delete(SupplierLink).where(SupplierLink.supplier_id.in_(ids)), counts, "supplier_links")
    await _delete_stmt(db, delete(SupplierContact).where(SupplierContact.supplier_id.in_(ids)), counts, "supplier_contacts")
    await _delete_stmt(db, delete(PriceSearchProjection).where(PriceSearchProjection.supplier_id.in_(ids)), counts, "price_search_projections")
    await _delete_stmt(db, delete(Supplier).where(Supplier.id.in_(ids)), counts, "suppliers")
    return ids


async def _delete_categories_by_ids(db: AsyncSession, category_ids: Sequence[str], counts: dict[str, int]) -> list[str]:
    ids = normalize_tokens(category_ids)
    if not ids:
        return []
    await _update_stmt(
        db,
        update(Product)
        .where(or_(Product.category_id.in_(ids), Product.last_category_id.in_(ids)))
        .values(category_id=None, last_category_id=None, category=""),
        counts,
        "products_reassigned_category",
    )
    await _delete_stmt(db, delete(ProductCategory).where(ProductCategory.id.in_(ids)), counts, "product_categories")
    return ids


async def _delete_verification_requests_by_ids(
    db: AsyncSession,
    request_ids: Sequence[str],
    counts: dict[str, int],
    filesystem: dict[str, int],
) -> list[str]:
    ids = normalize_tokens(request_ids)
    if not ids:
        return []
    await _delete_attachment_bindings_for_entities(
        db,
        entity_types=ENTITY_BINDING_TYPES_BY_REF["verification_request"],
        entity_ids=ids,
        counts=counts,
        filesystem=filesystem,
    )
    await _update_stmt(
        db,
        update(NotificationEvent).where(NotificationEvent.related_request_id.in_(ids)).values(related_request_id=None),
        counts,
        "notification_events_detached_request",
    )
    await _delete_stmt(db, delete(VerificationQueueProjection).where(VerificationQueueProjection.request_id.in_(ids)), counts, "verification_queue_projections")
    await _delete_stmt(db, delete(VerificationDependencyWarning).where(VerificationDependencyWarning.request_id.in_(ids)), counts, "verification_dependency_warnings")
    await _delete_stmt(db, delete(VerificationEscalation).where(VerificationEscalation.request_id.in_(ids)), counts, "verification_escalations")
    await _delete_stmt(db, delete(VerificationAssignment).where(VerificationAssignment.request_id.in_(ids)), counts, "verification_assignments")
    await _delete_stmt(db, delete(VerificationAction).where(VerificationAction.request_id.in_(ids)), counts, "verification_actions")
    await _delete_stmt(db, delete(VerificationRequestItem).where(VerificationRequestItem.request_id.in_(ids)), counts, "verification_request_items")
    await _update_stmt(
        db,
        update(VerificationRequest).where(VerificationRequest.supersedes_request_id.in_(ids)).values(supersedes_request_id=None),
        counts,
        "verification_requests_detached",
    )
    await _delete_stmt(db, delete(VerificationRequest).where(VerificationRequest.id.in_(ids)), counts, "verification_requests")
    return ids


async def _delete_attachments_by_ids(db: AsyncSession, attachment_ids: Sequence[str], counts: dict[str, int], filesystem: dict[str, int]) -> list[str]:
    ids = normalize_tokens(attachment_ids)
    if not ids:
        return []
    rows = await _collect_string_rows(db, select(Attachment.id, Attachment.storage_driver, Attachment.storage_key).where(Attachment.id.in_(ids)))
    await _delete_stmt(db, delete(AttachmentScanJob).where(AttachmentScanJob.attachment_id.in_(ids)), counts, "attachment_scan_jobs")
    await _delete_stmt(db, delete(AttachmentBinding).where(AttachmentBinding.attachment_id.in_(ids)), counts, "attachment_bindings")
    await _delete_stmt(db, delete(Attachment).where(Attachment.id.in_(ids)), counts, "attachments")
    _inc(filesystem, "attachment_files", await _delete_attachment_files([(row[1], row[2]) for row in rows]))
    return ids


async def _delete_notifications_all(db: AsyncSession, counts: dict[str, int]) -> None:
    await _delete_stmt(db, delete(NotificationDelivery), counts, "notification_deliveries")
    await _delete_stmt(db, delete(NotificationFailure), counts, "notification_failures")
    await _delete_stmt(db, delete(NotificationOutbox), counts, "notification_outbox")
    await _delete_stmt(db, delete(NotificationPreference), counts, "notification_preferences")
    await _delete_stmt(db, delete(NotificationTemplate), counts, "notification_templates")
    await _delete_stmt(db, delete(NotificationEvent), counts, "notification_events")


async def _delete_verification_all(db: AsyncSession, counts: dict[str, int], filesystem: dict[str, int]) -> None:
    request_ids = [row[0] for row in await _collect_string_rows(db, select(VerificationRequest.id))]
    await _delete_verification_requests_by_ids(db, request_ids, counts, filesystem)


async def _delete_matching_all(db: AsyncSession, counts: dict[str, int]) -> None:
    await _update_stmt(
        db,
        update(CatalogSearchDocument).values(canonical_group_id=None, canonical_group_name=""),
        counts,
        "catalog_search_documents_detached_matching",
    )
    await _update_stmt(
        db,
        update(PriceSearchProjection).values(canonical_group_id=None, canonical_group_name=""),
        counts,
        "price_search_projections_detached_matching",
    )
    await _update_stmt(db, update(CanonicalProductGroup).values(merged_into_group_id=None, last_operation_id=None), counts, "canonical_groups_detached")
    await _update_stmt(db, update(MatchingOperation).values(reversal_of_operation_id=None), counts, "matching_operations_detached")
    await _delete_stmt(db, delete(MatchingDependencyCheck), counts, "matching_dependency_checks")
    await _delete_stmt(db, delete(MatchingOperationMembershipState), counts, "matching_operation_membership_states")
    await _delete_stmt(db, delete(MatchingOperationGroupState), counts, "matching_operation_group_states")
    await _delete_stmt(db, delete(CanonicalGroupMember), counts, "canonical_group_members")
    await _delete_stmt(db, delete(MatchingOperation), counts, "matching_operations")
    await _delete_stmt(db, delete(CanonicalProductGroup), counts, "canonical_product_groups")


async def _delete_pricing_all(db: AsyncSession, counts: dict[str, int], filesystem: dict[str, int]) -> None:
    price_ids = [row[0] for row in await _collect_string_rows(db, select(PriceRecord.id))]
    if price_ids:
        await _delete_price_records_by_ids(db, price_ids, counts, filesystem)
    await _update_stmt(db, update(CostFormula).values(active_version_id=None), counts, "cost_formulas_detached")
    await _update_stmt(db, update(CostFormulaVersion).values(replaced_version_id=None), counts, "cost_formula_versions_detached")
    await _delete_stmt(db, delete(CostFormulaVersion), counts, "cost_formula_versions")
    await _delete_stmt(db, delete(CostFormula), counts, "cost_formulas")
    await _delete_stmt(db, delete(ExchangeRateSnapshot), counts, "exchange_rate_snapshots")


async def _delete_products_all(db: AsyncSession, counts: dict[str, int], filesystem: dict[str, int]) -> None:
    product_ids = [row[0] for row in await _collect_string_rows(db, select(Product.id))]
    if product_ids:
        await _delete_products_by_ids(db, product_ids, counts, filesystem)
    await _delete_stmt(db, delete(ProductCategory), counts, "product_categories")
    await _delete_stmt(db, delete(Tag), counts, "tags")
    await _delete_stmt(db, delete(CatalogSearchDocument), counts, "catalog_search_documents")
    await _delete_stmt(db, delete(PriceSearchProjection), counts, "price_search_projections")
    _inc(filesystem, "product_media_files", _reset_directory(MEDIA_ROOT))


async def _delete_suppliers_all(db: AsyncSession, counts: dict[str, int], filesystem: dict[str, int]) -> None:
    supplier_ids = [row[0] for row in await _collect_string_rows(db, select(Supplier.id))]
    if supplier_ids:
        await _delete_suppliers_by_ids(db, supplier_ids, counts, filesystem)


async def _delete_attachments_all(db: AsyncSession, counts: dict[str, int], filesystem: dict[str, int]) -> None:
    await _delete_stmt(db, delete(AttachmentScanJob), counts, "attachment_scan_jobs")
    await _delete_stmt(db, delete(AttachmentBinding), counts, "attachment_bindings")
    await _delete_stmt(db, delete(Attachment), counts, "attachments")
    await _delete_stmt(db, delete(AttachmentTypeClassification), counts, "attachment_type_classifications")
    _inc(filesystem, "attachment_files", _reset_directory(LOCAL_ATTACHMENT_ROOT))
    _inc(filesystem, "attachment_files", _reset_directory(OBJECT_ATTACHMENT_ROOT))
    ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)


async def _delete_reports_all(db: AsyncSession, counts: dict[str, int]) -> None:
    await _delete_stmt(db, delete(ReportSnapshotLink), counts, "report_snapshot_links")
    await _delete_stmt(db, delete(ReportSnapshotItem), counts, "report_snapshot_items")
    await _delete_stmt(db, delete(ReportSnapshot), counts, "report_snapshots")


async def _delete_logs_all(db: AsyncSession, counts: dict[str, int], filesystem: dict[str, int]) -> None:
    await _delete_stmt(db, delete(AuditEvent), counts, "audit_events")
    await _delete_stmt(db, delete(AuditLog), counts, "audit_logs")
    await _delete_stmt(db, delete(EntityArchive), counts, "entity_archives")
    _inc(filesystem, "log_files", _reset_directory(storage_root() / "logs"))


async def _delete_system_access_all(db: AsyncSession, counts: dict[str, int]) -> None:
    await _delete_stmt(db, delete(LoginLock), counts, "login_locks")
    await _delete_stmt(db, delete(RefreshSession), counts, "refresh_sessions")
    await _delete_stmt(db, delete(UserBranchScope), counts, "user_branch_scopes")


async def _delete_users_and_branches_all(db: AsyncSession, counts: dict[str, int]) -> None:
    await _delete_system_access_all(db, counts)
    await _delete_stmt(db, delete(User), counts, "users")
    await _delete_stmt(db, delete(Branch), counts, "branches")


def _clear_backups(filesystem: dict[str, int]) -> None:
    _inc(filesystem, "backup_files", _reset_directory(backups_root()))


async def execute_permanent_delete(
    db: AsyncSession,
    *,
    scopes: Sequence[str],
    delete_all: bool,
    product_refs: Sequence[str],
    supplier_refs: Sequence[str],
    category_refs: Sequence[str],
    price_record_refs: Sequence[str],
    verification_refs: Sequence[str],
    attachment_refs: Sequence[str],
) -> dict[str, object]:
    requested_scopes = normalize_tokens(scopes)
    invalid_scopes = [scope for scope in requested_scopes if scope not in ALL_SCOPES]
    if invalid_scopes:
        raise ValueError(f"invalid_scopes:{','.join(invalid_scopes)}")
    if any(scope in DANGEROUS_SCOPES for scope in requested_scopes) and not delete_all:
        raise ValueError("dangerous_scopes_require_delete_all")

    counts: dict[str, int] = {}
    filesystem: dict[str, int] = {}
    warnings: list[str] = []
    unmatched: dict[str, list[str]] = {}
    executed_scopes = list(ALL_SCOPES) if delete_all else requested_scopes[:]

    product_ids, unmatched_products = await _resolve_products(db, product_refs)
    supplier_ids, unmatched_suppliers = await _resolve_suppliers(db, supplier_refs)
    category_ids, unmatched_categories = await _resolve_categories(db, category_refs)
    price_record_ids, unmatched_prices = await _resolve_price_records(db, price_record_refs)
    verification_ids, unmatched_verification = await _resolve_verification_requests(db, verification_refs)
    attachment_ids, unmatched_attachments = await _resolve_attachments(db, attachment_refs)

    if unmatched_products:
        unmatched["product_refs"] = unmatched_products
    if unmatched_suppliers:
        unmatched["supplier_refs"] = unmatched_suppliers
    if unmatched_categories:
        unmatched["category_refs"] = unmatched_categories
    if unmatched_prices:
        unmatched["price_record_refs"] = unmatched_prices
    if unmatched_verification:
        unmatched["verification_refs"] = unmatched_verification
    if unmatched_attachments:
        unmatched["attachment_refs"] = unmatched_attachments

    if product_ids:
        await _delete_products_by_ids(db, product_ids, counts, filesystem)
    if supplier_ids:
        await _delete_suppliers_by_ids(db, supplier_ids, counts, filesystem)
    if category_ids:
        await _delete_categories_by_ids(db, category_ids, counts)
    if price_record_ids:
        await _delete_price_records_by_ids(db, price_record_ids, counts, filesystem)
    if verification_ids:
        await _delete_verification_requests_by_ids(db, verification_ids, counts, filesystem)
    if attachment_ids:
        await _delete_attachments_by_ids(db, attachment_ids, counts, filesystem)

    if delete_all or "pricing" in requested_scopes:
        await _delete_pricing_all(db, counts, filesystem)
    if delete_all or "matching" in requested_scopes:
        await _delete_matching_all(db, counts)
    if delete_all or "verification" in requested_scopes:
        await _delete_verification_all(db, counts, filesystem)
    if delete_all or "notifications" in requested_scopes:
        await _delete_notifications_all(db, counts)
    if delete_all or "products" in requested_scopes:
        await _delete_products_all(db, counts, filesystem)
    if delete_all or "suppliers" in requested_scopes:
        await _delete_suppliers_all(db, counts, filesystem)
    if delete_all or "attachments" in requested_scopes:
        await _delete_attachments_all(db, counts, filesystem)
    if delete_all or "reports" in requested_scopes:
        await _delete_reports_all(db, counts)
    if delete_all or "logs" in requested_scopes:
        await _delete_logs_all(db, counts, filesystem)
    if delete_all or "system_access" in requested_scopes:
        await _delete_system_access_all(db, counts)
    if delete_all:
        await _delete_users_and_branches_all(db, counts)

    await db.commit()

    if delete_all or "backups" in requested_scopes:
        _clear_backups(filesystem)

    if delete_all:
        _inc(filesystem, "product_media_files", _reset_directory(MEDIA_ROOT))
        _inc(filesystem, "attachment_files", _reset_directory(LOCAL_ATTACHMENT_ROOT))
        _inc(filesystem, "attachment_files", _reset_directory(OBJECT_ATTACHMENT_ROOT))

    if any(values for values in unmatched.values()):
        warnings.append("some_refs_not_found")

    return {
        "executed_scopes": executed_scopes,
        "deleted_counts": counts,
        "filesystem_deleted": filesystem,
        "unmatched_refs": unmatched,
        "warnings": warnings,
        "session_invalidated": bool(delete_all),
    }