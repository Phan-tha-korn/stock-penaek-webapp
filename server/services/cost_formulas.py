from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import CostFormula, CostFormulaVersion, FormulaScopeType, FormulaStatus, User
from server.services.audit import write_audit_log


ALLOWED_FORMULA_VARIABLES = {
    "base_price",
    "vat_amount",
    "shipping_cost",
    "fuel_cost",
    "labor_cost",
    "utility_cost",
    "distance_meter",
    "distance_cost",
    "quantity",
    "supplier_fee",
    "discount",
}
ALLOWED_FORMULA_PREFIXES = ("custom_input_",)
TOKEN_PATTERN = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")
RESERVED_WORDS = {"and", "or", "not", "if", "else", "min", "max", "abs", "round"}


def validate_formula_scope(scope_type: str, scope_ref_id: str | None) -> FormulaScopeType:
    try:
        scope = FormulaScopeType(str(scope_type or FormulaScopeType.GLOBAL.value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_formula_scope_type") from exc
    if scope == FormulaScopeType.GLOBAL and scope_ref_id:
        raise HTTPException(status_code=400, detail="global_formula_cannot_have_scope_ref")
    if scope != FormulaScopeType.GLOBAL and not scope_ref_id:
        raise HTTPException(status_code=400, detail="formula_scope_ref_required")
    return scope


def validate_formula_status(value: str) -> FormulaStatus:
    try:
        return FormulaStatus(str(value or FormulaStatus.DRAFT.value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_formula_status") from exc


def _is_allowed_variable(token: str) -> bool:
    if token in ALLOWED_FORMULA_VARIABLES:
        return True
    return any(token.startswith(prefix) for prefix in ALLOWED_FORMULA_PREFIXES)


def extract_formula_variables(expression_text: str) -> list[str]:
    found: list[str] = []
    for token in TOKEN_PATTERN.findall(str(expression_text or "")):
        if token in RESERVED_WORDS:
            continue
        if token.isupper():
            continue
        if token not in found:
            found.append(token)
    return found


def validate_formula_expression(expression_text: str, variables: list[str] | None = None) -> list[str]:
    expression = str(expression_text or "").strip()
    if not expression:
        raise HTTPException(status_code=400, detail="formula_expression_required")
    detected = variables or extract_formula_variables(expression)
    invalid = [token for token in detected if not _is_allowed_variable(token)]
    if invalid:
        raise HTTPException(status_code=400, detail=f"invalid_formula_variables:{','.join(invalid)}")
    return detected


def ensure_formula_version_mutable(version: CostFormulaVersion) -> None:
    if version.is_locked or version.activated_at is not None or version.is_active_version:
        raise HTTPException(status_code=409, detail="cost_formula_version_immutable")


def serialize_formula(formula: CostFormula) -> dict[str, Any]:
    return {
        "id": formula.id,
        "code": formula.code,
        "name": formula.name,
        "scope_type": formula.scope_type.value,
        "scope_ref_id": formula.scope_ref_id,
        "branch_id": formula.branch_id,
        "is_override": formula.is_override,
        "status": formula.status.value,
        "active_version_id": formula.active_version_id,
    }


def serialize_formula_version(version: CostFormulaVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "formula_id": version.formula_id,
        "version_no": version.version_no,
        "expression_text": version.expression_text,
        "variables_json": version.variables_json,
        "constants_json": version.constants_json,
        "dependency_keys_json": version.dependency_keys_json,
        "is_active_version": version.is_active_version,
        "is_locked": version.is_locked,
        "activated_at": version.activated_at.isoformat() if version.activated_at else None,
        "replaced_version_id": version.replaced_version_id,
    }


async def create_cost_formula(
    db: AsyncSession,
    *,
    actor: User,
    request: Request | None,
    payload: dict[str, Any],
) -> CostFormula:
    code = str(payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="formula_code_required")
    existing = await db.scalar(select(CostFormula).where(CostFormula.code == code, CostFormula.archived_at.is_(None)))
    if existing:
        raise HTTPException(status_code=409, detail="formula_code_exists")

    scope_type = validate_formula_scope(str(payload.get("scope_type") or FormulaScopeType.GLOBAL.value), payload.get("scope_ref_id"))
    formula = CostFormula(
        code=code,
        name=str(payload.get("name") or code).strip(),
        description=str(payload.get("description") or ""),
        scope_type=scope_type,
        scope_ref_id=payload.get("scope_ref_id"),
        branch_id=payload.get("branch_id"),
        is_override=bool(payload.get("is_override", False)),
        status=validate_formula_status(str(payload.get("status") or FormulaStatus.DRAFT.value)),
        warning_on_change=bool(payload.get("warning_on_change", True)),
        created_by=actor.id,
        updated_by=actor.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(formula)
    await db.flush()
    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="COST_FORMULA_CREATE",
        entity="cost_formula",
        entity_id=formula.id,
        success=True,
        message="cost_formula_created",
        before=None,
        after=serialize_formula(formula),
        branch_id=formula.branch_id,
        reason="cost_formula_created",
        diff_summary="cost formula create",
    )
    return formula


async def create_cost_formula_version(
    db: AsyncSession,
    *,
    formula: CostFormula,
    actor: User,
    request: Request | None,
    payload: dict[str, Any],
) -> CostFormulaVersion:
    expression_text = str(payload.get("expression_text") or "").strip()
    variables = validate_formula_expression(expression_text, payload.get("variables_json"))
    latest = await db.scalar(
        select(CostFormulaVersion)
        .where(CostFormulaVersion.formula_id == formula.id)
        .order_by(CostFormulaVersion.version_no.desc())
        .limit(1)
    )
    next_version = 1 if latest is None else int(latest.version_no) + 1
    version = CostFormulaVersion(
        formula_id=formula.id,
        version_no=next_version,
        expression_text=expression_text,
        variables_json=payload.get("variables_json") or variables,
        constants_json=payload.get("constants_json") or {},
        dependency_keys_json=payload.get("dependency_keys_json") or variables,
        notes=str(payload.get("notes") or ""),
        is_active_version=False,
        is_locked=False,
        created_by=actor.id,
        created_at=datetime.utcnow(),
    )
    db.add(version)
    await db.flush()
    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="COST_FORMULA_VERSION_CREATE",
        entity="cost_formula_version",
        entity_id=version.id,
        success=True,
        message="cost_formula_version_created",
        before=None,
        after=serialize_formula_version(version),
        branch_id=formula.branch_id,
        reason="cost_formula_version_created",
        diff_summary=f"version:{version.version_no}",
    )
    return version


async def update_cost_formula_version(
    db: AsyncSession,
    *,
    version: CostFormulaVersion,
    actor: User,
    request: Request | None,
    payload: dict[str, Any],
) -> CostFormulaVersion:
    ensure_formula_version_mutable(version)
    before = serialize_formula_version(version)
    expression_text = str(payload.get("expression_text") or version.expression_text).strip()
    variables = validate_formula_expression(expression_text, payload.get("variables_json") or version.variables_json)
    version.expression_text = expression_text
    version.variables_json = payload.get("variables_json") or variables
    version.constants_json = payload.get("constants_json") or version.constants_json
    version.dependency_keys_json = payload.get("dependency_keys_json") or variables
    version.notes = str(payload.get("notes") or version.notes)
    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="COST_FORMULA_VERSION_UPDATE",
        entity="cost_formula_version",
        entity_id=version.id,
        success=True,
        message="cost_formula_version_updated",
        before=before,
        after=serialize_formula_version(version),
        branch_id=None,
        reason="cost_formula_version_updated",
        diff_summary=f"version:{version.version_no}",
    )
    return version


async def activate_cost_formula_version(
    db: AsyncSession,
    *,
    formula: CostFormula,
    version: CostFormulaVersion,
    actor: User,
    request: Request | None,
) -> CostFormulaVersion:
    if version.formula_id != formula.id:
        raise HTTPException(status_code=400, detail="formula_version_mismatch")

    previous_active = await db.scalar(
        select(CostFormulaVersion).where(
            CostFormulaVersion.formula_id == formula.id,
            CostFormulaVersion.is_active_version.is_(True),
            CostFormulaVersion.archived_at.is_(None),
        )
    )
    if previous_active and previous_active.id != version.id:
        previous_active.is_active_version = False
        previous_active.is_locked = True
        previous_active.replaced_version_id = version.id

    version.is_active_version = True
    version.is_locked = True
    version.activated_at = datetime.utcnow()
    formula.active_version_id = version.id
    formula.status = FormulaStatus.ACTIVE
    formula.updated_by = actor.id
    formula.updated_at = datetime.utcnow()

    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="COST_FORMULA_VERSION_ACTIVATE",
        entity="cost_formula_version",
        entity_id=version.id,
        success=True,
        message="cost_formula_version_activated",
        before=None,
        after=serialize_formula_version(version),
        branch_id=formula.branch_id,
        reason="cost_formula_version_activated",
        diff_summary=f"version:{version.version_no}",
    )
    return version
