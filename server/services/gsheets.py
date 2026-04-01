import asyncio
import logging
from datetime import datetime
from pathlib import Path

import gspread
import orjson
from google.oauth2.service_account import Credentials
from sqlalchemy import select

from server.config.settings import settings
from server.db.database import SessionLocal
from server.db.models import AuditLog, Product, User
from server.db.init_db import calc_status
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]

DELETED_PREFIX = "__DELETED__:"
logger = logging.getLogger(__name__)



TAB_STOCK = "Stock"
TAB_EDIT_LOG = "EditLog"
TAB_ADD_LOG = "AddLog"
TAB_SELL_LOG = "SellLog"
TAB_INCOME_LOG = "IncomeLog"
TAB_EXPENSE_LOG = "ExpenseLog"

HEADERS = {
    TAB_STOCK: [
        "ID",
        "ชื่อสินค้า",
        "ประเภท",
        "หน่วย",
        "จำนวนปัจจุบัน",
        "จำนวนที่ควรมี",
        "ราคาต่อหน่วย",
        "มูลค่ารวม",
        "% คงเหลือ",
        "สถานะ",
        "เกณฑ์แจ้งเตือน%",
        "LINE_USER_ID",
        "LINE_GROUP_ID",
        "ข้อความแจ้งเตือน",
        "อัปเดตล่าสุด",
    ],
    TAB_EDIT_LOG: ["วันที่-เวลา", "ประเภทการกระทำ", "ID สินค้า", "ชื่อสินค้า", "รายละเอียด", "ผู้ทำรายการ"],
    TAB_ADD_LOG: [
        "วันที่-เวลา",
        "ID สินค้า",
        "ชื่อสินค้า",
        "จำนวนเพิ่ม",
        "หน่วย",
        "จากเดิม",
        "คงเหลือหลังเพิ่ม",
        "หมายเหตุ",
        "ผู้ทำรายการ",
    ],
    TAB_SELL_LOG: [
        "วันที่-เวลา",
        "ID สินค้า",
        "ชื่อสินค้า",
        "จำนวนเบิก/ขาย",
        "หน่วย",
        "จากเดิม",
        "คงเหลือหลังเบิก",
        "หมายเหตุ",
        "ผู้ทำรายการ",
    ],
    TAB_INCOME_LOG: ["วันที่-เวลา", "หมวดรายรับ", "รายละเอียด", "จำนวนเงิน", "ช่องทาง", "อ้างอิง", "ผู้บันทึก"],
    TAB_EXPENSE_LOG: ["วันที่-เวลา", "หมวดรายจ่าย", "รายละเอียด", "จำนวนเงิน", "ช่องทาง", "อ้างอิง", "ผู้บันทึก"],
}


async def _with_retries(coro_factory, retries: int = 3, delay_sec: float = 2.0):
    last_err = None
    for i in range(retries):
        try:
            return await coro_factory()
        except Exception as e:
            last_err = e
            if i < retries - 1:
                await asyncio.sleep(delay_sec * (i + 1))
    if last_err:
        raise last_err

def get_client() -> gspread.client.Client | None:
    if not settings.google_sheets_id:
        return None
    
    key_path = Path(settings.google_service_account_key_path)
    if not key_path.exists():
        logger.warning(f"Google Sheets service account key not found at {key_path}")
        return None

    try:
        credentials = Credentials.from_service_account_file(
            str(key_path), scopes=SCOPES
        )
        return gspread.authorize(credentials)
    except Exception as e:
        logger.error(f"Failed to authorize Google Sheets client: {e}")
        return None


def _is_deleted_product(p: Product) -> bool:
    return bool((p.notes or "").startswith(DELETED_PREFIX))


def _status_th(s: str) -> str:
    if s == "FULL":
        return "🟩 Stock เต็ม"
    if s == "OUT":
        return "⬛ Stock หมด"
    if s == "CRITICAL":
        return "🟥 ควรเติม"
    if s == "LOW":
        return "🟧 ใกล้หมด"
    if s == "TEST":
        return "🟦 ทดสอบ"
    return "⬜ ปกติ"


def _pct_str(v: float) -> str:
    return f"{max(0.0, min(100.0, v)):.0f}%"


def _parse_json(s: str | None) -> dict:
    if not s:
        return {}
    try:
        v = orjson.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _ensure_tab(sheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    try:
        ws = sheet.worksheet(title)
    except Exception:
        ws = sheet.add_worksheet(title=title, rows=2000, cols=max(20, len(HEADERS.get(title, []))))

    header = HEADERS.get(title)
    if header:
        try:
            ws.update([header], range_name="A1")
        except Exception:
            ws.clear()
            ws.update([header], range_name="A1")
    return ws


def _get_col_idx(header: list[str], keys: list[str]) -> int | None:
    norm = {str(x).strip(): i for i, x in enumerate(header)}
    for k in keys:
        if k in norm:
            return norm[k]
    return None


def _parse_float(v: str) -> float:
    s = (v or "").strip()
    if not s:
        return 0.0
    s = s.replace(",", "")
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except Exception:
        return 0.0


def _sync_stock_sheet(ws: gspread.Worksheet, products: list[dict]) -> None:
    values = ws.get_all_values()
    if not values:
        values = [HEADERS[TAB_STOCK]]

    header = values[0]
    if not header:
        header = HEADERS[TAB_STOCK]
        values = [header]

    id_idx = _get_col_idx(header, ["ID", "Sku", "SKU"])
    if id_idx is None:
        header = HEADERS[TAB_STOCK]
        values = [header]
        id_idx = 0

    name_idx = _get_col_idx(header, ["ชื่อสินค้า", "Name"])
    type_idx = _get_col_idx(header, ["ประเภท", "หมวดหมู่", "Category"])
    unit_idx = _get_col_idx(header, ["หน่วย", "Unit"])
    qty_idx = _get_col_idx(header, ["จำนวนปัจจุบัน", "Current_Qty"])
    max_idx = _get_col_idx(header, ["จำนวนที่ควรมี", "Max_Stock"])
    price_idx = _get_col_idx(header, ["ราคาต่อหน่วย", "Unit_Price"])
    total_idx = _get_col_idx(header, ["มูลค่ารวม", "Total_Value"])
    pct_idx = _get_col_idx(header, ["% คงเหลือ", "%", "Pct"])
    status_idx = _get_col_idx(header, ["สถานะ", "Status"])
    threshold_idx = _get_col_idx(header, ["เกณฑ์แจ้งเตือน%", "Threshold%"])
    msg_idx = _get_col_idx(header, ["ข้อความแจ้งเตือน", "Message"])
    updated_idx = _get_col_idx(header, ["อัปเดตล่าสุด", "Last_Updated"])

    row_by_id: dict[str, int] = {}
    for i in range(1, len(values)):
        row = values[i]
        if id_idx < len(row):
            key = (row[id_idx] or "").strip()
            if key:
                row_by_id[key] = i

    now = datetime.utcnow().isoformat(timespec="seconds")

    def ensure_len(r: list[str]) -> list[str]:
        if len(r) < len(header):
            return r + [""] * (len(header) - len(r))
        return r[: len(header)]

    for p in products:
        pid = str(p.get("sku") or "").strip()
        if not pid:
            continue
        qty = float(p.get("stock_qty") or 0)
        max_qty = float(p.get("max_stock") or 0)
        selling_price = p.get("selling_price")
        cost_price = p.get("cost_price")
        unit_price = float(selling_price) if selling_price is not None else float(cost_price or 0)
        total_value = qty * unit_price
        pct = (qty / max_qty * 100.0) if max_qty > 0 else 0.0

        existing_row_idx = row_by_id.get(pid)
        if existing_row_idx is None:
            row = ensure_len([""] * len(header))
            row[id_idx] = pid
            values.append(row)
            existing_row_idx = len(values) - 1
        else:
            row = ensure_len(values[existing_row_idx])

        if name_idx is not None:
            row[name_idx] = str(p.get("name_th") or "")
        if type_idx is not None:
            row[type_idx] = str(p.get("category") or "")
        if unit_idx is not None:
            row[unit_idx] = str(p.get("unit") or "")
        if qty_idx is not None:
            row[qty_idx] = str(qty)
        if max_idx is not None:
            row[max_idx] = str(max_qty) if max_qty > 0 else ""
        if price_idx is not None:
            row[price_idx] = str(unit_price)
        if total_idx is not None:
            row[total_idx] = str(total_value)
        if pct_idx is not None:
            row[pct_idx] = _pct_str(pct)
        if status_idx is not None:
            row[status_idx] = _status_th(str(p.get("status") or "NORMAL"))
        if updated_idx is not None:
            updated_at = p.get("updated_at")
            row[updated_idx] = str(updated_at or now)

        threshold = None
        if threshold_idx is not None and threshold_idx < len(row):
            threshold = _parse_float(row[threshold_idx])
            if threshold <= 0:
                threshold = 60.0
                row[threshold_idx] = str(int(threshold))

        if msg_idx is not None:
            warn = row[msg_idx] if msg_idx < len(row) else ""
            if threshold is not None and max_qty > 0 and pct <= threshold:
                warn = f"{p.get('name_th') or ''} เหลือ {_pct_str(pct)} ควรเติม"
            if str(p.get("status") or "") == "OUT":
                warn = f"{p.get('name_th') or ''} หมดสต็อก"
            row[msg_idx] = warn

        values[existing_row_idx] = row

    col_count = len(header)
    end_col = gspread.utils.rowcol_to_a1(1, col_count).split("1")[0]
    ws.update(f"A1:{end_col}{len(values)}", values)


async def import_stock_from_sheet(
    *,
    actor_id: str | None = None,
    overwrite_stock_qty: bool = False,
    overwrite_prices: bool = False,
) -> dict:
    def _read_values_blocking():
        client = get_client()
        if not client:
            return None
        sheet = client.open_by_key(settings.google_sheets_id)
        ws = _ensure_tab(sheet, TAB_STOCK)
        return ws.get_all_values()

    values = await _with_retries(lambda: asyncio.to_thread(_read_values_blocking), retries=3, delay_sec=1.5)
    if not values:
        return {"ok": False, "error": "sheets_not_configured"}
    if not values or len(values) < 2:
        return {"ok": True, "created": 0, "updated": 0, "skipped": 0}

    header = values[0]
    id_idx = _get_col_idx(header, ["ID", "SKU", "Sku"])
    name_idx = _get_col_idx(header, ["ชื่อสินค้า", "Name"])
    type_idx = _get_col_idx(header, ["ประเภท", "หมวดหมู่", "Category"])
    unit_idx = _get_col_idx(header, ["หน่วย", "Unit"])
    qty_idx = _get_col_idx(header, ["จำนวนปัจจุบัน", "Current_Qty"])
    max_idx = _get_col_idx(header, ["จำนวนที่ควรมี", "Max_Stock"])
    price_idx = _get_col_idx(header, ["ราคาต่อหน่วย", "Unit_Price"])
    threshold_idx = _get_col_idx(header, ["เกณฑ์แจ้งเตือน%", "Threshold%"])

    if id_idx is None or name_idx is None:
        return {"ok": False, "error": "missing_required_columns"}

    created = 0
    updated = 0
    skipped = 0

    async with SessionLocal() as db:
        actor = None
        if actor_id:
            actor = await db.scalar(select(User).where(User.id == actor_id))
        if not actor:
            actor = await db.scalar(select(User).order_by(User.created_at.asc()).limit(1))
        actor_id_resolved = actor.id if actor else ""

        for row in values[1:]:
            if id_idx >= len(row):
                continue
            sku = (row[id_idx] or "").strip()
            if not sku:
                continue
            name_th = (row[name_idx] or "").strip() if name_idx < len(row) else ""
            if not name_th:
                continue
            category = (row[type_idx] or "").strip() if type_idx is not None and type_idx < len(row) else ""
            unit = (row[unit_idx] or "").strip() if unit_idx is not None and unit_idx < len(row) else ""
            qty = _parse_float(row[qty_idx]) if qty_idx is not None and qty_idx < len(row) else 0.0
            max_qty = _parse_float(row[max_idx]) if max_idx is not None and max_idx < len(row) else 0.0
            unit_price = _parse_float(row[price_idx]) if price_idx is not None and price_idx < len(row) else 0.0
            threshold = _parse_float(row[threshold_idx]) if threshold_idx is not None and threshold_idx < len(row) else 60.0

            p = await db.scalar(select(Product).where(Product.sku == sku))
            if p and _is_deleted_product(p):
                skipped += 1
                continue

            min_qty = max_qty * (threshold / 100.0) if max_qty > 0 and threshold > 0 else 0.0

            if not p:
                p = Product(
                    sku=sku,
                    name_th=name_th,
                    name_en="",
                    category=category,
                    type="",
                    unit=unit or "ชิ้น",
                    cost_price=unit_price if unit_price > 0 else 0,
                    selling_price=unit_price if unit_price > 0 else None,
                    stock_qty=qty if overwrite_stock_qty else 0,
                    min_stock=min_qty,
                    max_stock=max_qty,
                    status=calc_status(qty if overwrite_stock_qty else 0, min_qty, max_qty, False),
                    is_test=False,
                    supplier="",
                    barcode="",
                    image_url=None,
                    notes="",
                    created_by=actor_id_resolved,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(p)
                created += 1
            else:
                p.name_th = name_th
                if category:
                    p.category = category
                if unit:
                    p.unit = unit
                if max_qty > 0:
                    p.max_stock = max_qty
                p.min_stock = min_qty
                if overwrite_stock_qty:
                    p.stock_qty = qty
                if overwrite_prices and unit_price > 0:
                    p.selling_price = unit_price
                p.status = calc_status(float(p.stock_qty), float(p.min_stock), float(p.max_stock), bool(p.is_test))
                p.updated_at = datetime.utcnow()
                updated += 1

        await db.commit()

    return {"ok": True, "created": created, "updated": updated, "skipped": skipped}


async def sync_all_to_sheets() -> None:
    products_data: list[dict] = []
    product_by_id: dict[str, dict] = {}
    add_rows = [HEADERS[TAB_ADD_LOG]]
    sell_rows = [HEADERS[TAB_SELL_LOG]]
    edit_rows = [HEADERS[TAB_EDIT_LOG]]

    async with SessionLocal() as db:
        res = await db.execute(select(Product))
        products = res.scalars().all()
        products = [p for p in products if not _is_deleted_product(p)]
        for p in products:
            updated = p.updated_at.isoformat(timespec="seconds") if p.updated_at else datetime.utcnow().isoformat(timespec="seconds")
            pd = {
                "id": p.id,
                "sku": p.sku,
                "name_th": p.name_th,
                "category": p.category,
                "unit": p.unit,
                "stock_qty": float(p.stock_qty or 0),
                "max_stock": float(p.max_stock or 0),
                "cost_price": float(p.cost_price or 0),
                "selling_price": float(p.selling_price) if p.selling_price is not None else None,
                "status": p.status.value,
                "updated_at": updated,
            }
            products_data.append(pd)
            product_by_id[p.id] = {"sku": p.sku, "name_th": p.name_th, "unit": p.unit}

        res = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(2000))
        logs = list(reversed(res.scalars().all()))

        for x in logs:
            if not x.success:
                continue
            before = _parse_json(x.before_json)
            after = _parse_json(x.after_json)
            qty_before = before.get("qty")
            qty_after = after.get("qty")

            info = product_by_id.get(str(x.entity_id or ""), {})
            sku = info.get("sku", "")
            name_th = info.get("name_th", "")
            unit = info.get("unit", "")
            actor = x.actor_username or ""
            ts = x.created_at.isoformat(sep=" ", timespec="seconds") if x.created_at else ""
            msg = x.message or ""

            if x.action == "STOCK_STOCK_IN":
                delta = ""
                if isinstance(qty_before, (int, float)) and isinstance(qty_after, (int, float)):
                    delta = max(0.0, float(qty_after) - float(qty_before))
                add_rows.append([ts, sku, name_th, delta, unit, qty_before or "", qty_after or "", msg, actor])
                continue

            if x.action == "STOCK_STOCK_OUT":
                delta = ""
                if isinstance(qty_before, (int, float)) and isinstance(qty_after, (int, float)):
                    delta = max(0.0, float(qty_before) - float(qty_after))
                sell_rows.append([ts, sku, name_th, delta, unit, qty_before or "", qty_after or "", msg, actor])
                continue

            if x.action.startswith("STOCK_") or x.action.startswith("PRODUCT_"):
                edit_rows.append([ts, x.action, sku, name_th, msg, actor])

    def _write_rows(ws: gspread.Worksheet, rows: list[list]) -> None:
        ws.clear()
        ws.update(rows)

    def _sync_blocking() -> None:
        client = get_client()
        if not client:
            return
        sheet = client.open_by_key(settings.google_sheets_id)
        ws_stock = _ensure_tab(sheet, TAB_STOCK)
        ws_edit = _ensure_tab(sheet, TAB_EDIT_LOG)
        ws_add = _ensure_tab(sheet, TAB_ADD_LOG)
        ws_sell = _ensure_tab(sheet, TAB_SELL_LOG)
        _ensure_tab(sheet, TAB_INCOME_LOG)
        _ensure_tab(sheet, TAB_EXPENSE_LOG)

        _sync_stock_sheet(ws_stock, products_data)
        _write_rows(ws_add, add_rows)
        _write_rows(ws_sell, sell_rows)
        _write_rows(ws_edit, edit_rows)

    try:
        await _with_retries(lambda: asyncio.to_thread(_sync_blocking), retries=3, delay_sec=2.0)
        logger.info("Google Sheets sync completed")
    except Exception as e:
        logger.error(f"Google Sheets sync failed: {e}")
        raise

async def init_sheets() -> None:
    try:
        await sync_all_to_sheets()
    except Exception as e:
        logger.error(f"Failed to initialize Google Sheets: {e}")


async def start_sync_loop() -> None:
    interval = int(getattr(settings, "google_sheets_sync_interval_seconds", 30) or 30)
    if interval < 10:
        interval = 10
    while True:
        try:
            await sync_all_to_sheets()
        except Exception as e:
            logger.error(f"Google Sheets sync loop failed: {e}")
        await asyncio.sleep(interval)


async def start_import_loop() -> None:
    interval = int(getattr(settings, "google_sheets_sync_interval_seconds", 30) or 30)
    if interval < 10:
        interval = 10
    while True:
        try:
            await import_stock_from_sheet(actor_id=None, overwrite_stock_qty=False, overwrite_prices=False)
        except Exception as e:
            logger.error(f"Google Sheets import loop failed: {e}")
        await asyncio.sleep(interval)
