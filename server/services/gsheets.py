import asyncio
import csv
import io
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import gspread
import orjson
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2.service_account import Credentials
from sqlalchemy import select

from server.config.config_loader import load_master_config
from server.config.config_loader import repo_root, resolve_repo_path
from server.config.settings import settings
from server.db.database import SessionLocal
from server.db.models import AuditLog, Product, Role, User
from server.db.init_db import calc_status
from server.services.branches import ensure_default_branch
from server.services.suppliers import sync_product_supplier_links
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]

DELETED_PREFIX = "__DELETED__:"
logger = logging.getLogger(__name__)
_SYNC_LOCK = asyncio.Lock()
_IMPORT_LOCK = asyncio.Lock()
_QUOTA_COOLDOWN_UNTIL = 0.0
_QUOTA_COOLDOWN_SECONDS = 90
_PENDING_SYNC_TASK: asyncio.Task | None = None



TAB_STOCK = "สต็อกสินค้า"
TAB_OVERVIEW = "ภาพรวมระบบ"
TAB_STOCK_ALERTS = "สินค้าเฝ้าระวัง"
TAB_EDIT_LOG = "บันทึกแก้ไข"
TAB_ADD_LOG = "บันทึกรับเข้า"
TAB_SELL_LOG = "บันทึกเบิกออก"
TAB_AUDIT_LOG = "บันทึกตรวจสอบ"
TAB_ACCOUNTING = "สรุปบัญชี"
TAB_INCOME_LOG = "รายรับเพิ่มเติม"
TAB_EXPENSE_LOG = "รายจ่ายเพิ่มเติม"
TAB_USERS = "ข้อมูลบัญชีผู้ใช้"
TAB_PRODUCT_IMPORT = "Product Import"

WORKBOOK_TABS = [
    TAB_OVERVIEW,
    TAB_STOCK,
    TAB_PRODUCT_IMPORT,
    TAB_STOCK_ALERTS,
    TAB_ACCOUNTING,
    TAB_AUDIT_LOG,
    TAB_EDIT_LOG,
    TAB_ADD_LOG,
    TAB_SELL_LOG,
    TAB_INCOME_LOG,
    TAB_EXPENSE_LOG,
    TAB_USERS,
]

LEGACY_TAB_ALIASES = {
    TAB_OVERVIEW: ["Overview"],
    TAB_STOCK: ["Stock"],
    TAB_PRODUCT_IMPORT: ["ProductImport", "ImportProducts"],
    TAB_STOCK_ALERTS: ["StockAlerts"],
    TAB_ACCOUNTING: ["Accounting"],
    TAB_AUDIT_LOG: ["AuditLog"],
    TAB_EDIT_LOG: ["EditLog"],
    TAB_ADD_LOG: ["AddLog"],
    TAB_SELL_LOG: ["SellLog"],
    TAB_INCOME_LOG: ["IncomeLog"],
    TAB_EXPENSE_LOG: ["ExpenseLog"],
    TAB_USERS: ["Users", "Accounts"],
}

HEADERS = {
    TAB_OVERVIEW: ["หัวข้อ", "ค่า", "รายละเอียด"],
    TAB_STOCK: [
        "รหัสสินค้า",
        "ชื่อสินค้า",
        "หมวดหมู่",
        "หน่วยนับ",
        "จำนวนคงเหลือ",
        "จำนวนที่ควรมี",
        "ราคาต่อหน่วย",
        "มูลค่ารวม",
        "เปอร์เซ็นต์คงเหลือ",
        "สถานะสต็อก",
        "เกณฑ์แจ้งเตือน (%)",
        "ไลน์ผู้ใช้",
        "ไลน์กลุ่ม",
        "ข้อความแจ้งเตือน",
        "อัปเดตล่าสุด",
    ],
    TAB_PRODUCT_IMPORT: [
        "SKU",
        "Name",
        "Category",
        "Unit",
        "Current_Qty",
        "Max_Stock",
        "Unit_Price",
        "Threshold%",
        "Current_Status",
        "Updated_At",
        "Notes",
    ],
    TAB_STOCK_ALERTS: ["ระดับความสำคัญ", "รหัสสินค้า", "ชื่อสินค้า", "คงเหลือ", "ขั้นต่ำ", "ควรมี", "สถานะ", "อัปเดตล่าสุด", "หมายเหตุ"],
    TAB_EDIT_LOG: ["วันที่-เวลา", "ประเภทการกระทำ", "รหัสสินค้า", "ชื่อสินค้า", "รายละเอียด", "ผู้ทำรายการ"],
    TAB_ADD_LOG: [
        "วันที่-เวลา",
        "รหัสสินค้า",
        "ชื่อสินค้า",
        "จำนวนเพิ่ม",
        "หน่วยนับ",
        "จากเดิม",
        "คงเหลือหลังเพิ่ม",
        "หมายเหตุ",
        "ผู้ทำรายการ",
    ],
    TAB_SELL_LOG: [
        "วันที่-เวลา",
        "รหัสสินค้า",
        "ชื่อสินค้า",
        "จำนวนเบิก/ขาย",
        "หน่วยนับ",
        "จากเดิม",
        "คงเหลือหลังเบิก",
        "หมายเหตุ",
        "ผู้ทำรายการ",
    ],
    TAB_AUDIT_LOG: ["ระดับความสำคัญ", "วันที่-เวลา", "การกระทำ", "ประเภทข้อมูล", "รหัสสินค้า", "ชื่อสินค้า", "รายละเอียด", "ผู้ทำรายการ"],
    TAB_ACCOUNTING: ["หัวข้อ", "ค่า", "รายละเอียด"],
    TAB_INCOME_LOG: ["วันที่-เวลา", "หมวดรายรับ", "รายละเอียด", "จำนวนเงิน", "ช่องทาง", "อ้างอิง", "ผู้บันทึก"],
    TAB_EXPENSE_LOG: ["วันที่-เวลา", "หมวดรายจ่าย", "รายละเอียด", "จำนวนเงิน", "ช่องทาง", "อ้างอิง", "ผู้บันทึก"],
    TAB_USERS: ["รหัสผู้ใช้", "ชื่อผู้ใช้", "ชื่อแสดงผล", "บทบาท", "สถานะบัญชี", "ภาษา", "วันที่สร้าง", "อัปเดตล่าสุด"],
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


def _is_quota_error(exc: Exception) -> bool:
    return "quota exceeded" in str(exc).lower()


def _quota_cooldown_remaining() -> int:
    return max(0, int(_QUOTA_COOLDOWN_UNTIL - time.time()))


def _set_quota_cooldown() -> None:
    global _QUOTA_COOLDOWN_UNTIL
    _QUOTA_COOLDOWN_UNTIL = time.time() + _QUOTA_COOLDOWN_SECONDS


def _is_quota_cooling_down() -> bool:
    return _quota_cooldown_remaining() > 0


def schedule_sheet_sync(delay_seconds: float = 1.0) -> bool:
    global _PENDING_SYNC_TASK
    if _PENDING_SYNC_TASK and not _PENDING_SYNC_TASK.done():
        return False

    async def _runner() -> None:
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            await sync_all_to_sheets()
        except Exception:
            logger.exception("Scheduled Google Sheets sync failed")
        finally:
            global _PENDING_SYNC_TASK
            _PENDING_SYNC_TASK = None

    try:
        _PENDING_SYNC_TASK = asyncio.create_task(_runner())
        return True
    except RuntimeError:
        return False

def get_client() -> gspread.client.Client | None:
    oauth_token_path = resolve_repo_path(
        str(settings.google_oauth_token_path or "").strip(),
        fallback_relative="credentials/google_oauth_token.json",
    )
    if oauth_token_path.exists():
        try:
            credentials = OAuthCredentials.from_authorized_user_file(str(oauth_token_path), scopes=SCOPES)
            return gspread.authorize(credentials)
        except Exception as e:
            logger.error(f"Failed to authorize Google Sheets OAuth client: {e}")

    key_path = resolve_repo_path(
        str(settings.google_service_account_key_path or "").strip(),
        fallback_relative="credentials/google_key.json",
    )
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


def _role_th(role: Role | str | None) -> str:
    value = str(getattr(role, "value", role) or "").upper()
    return {
        "STOCK": "พนักงานสต็อก",
        "ADMIN": "ผู้ดูแลระบบ",
        "ACCOUNTANT": "ฝ่ายบัญชี",
        "OWNER": "เจ้าของระบบ",
        "DEV": "นักพัฒนา",
    }.get(value, value or "-")


def _action_th(action: str) -> str:
    value = str(action or "").strip().upper()
    mapping = {
        "LOGIN": "เข้าสู่ระบบ",
        "TOKEN_REFRESH": "ต่ออายุโทเคน",
        "CONFIG_UPDATE": "อัปเดตการตั้งค่า",
        "CONFIG_GOOGLE_SETUP": "ตั้งค่า Google Sheets",
        "USER_CREATE": "สร้างบัญชีผู้ใช้",
        "USER_UPDATE": "แก้ไขบัญชีผู้ใช้",
        "USER_RESET_PASSWORD": "รีเซ็ตรหัสผ่านผู้ใช้",
        "USER_DELETE": "ลบบัญชีผู้ใช้",
        "PRODUCT_CREATE": "สร้างสินค้า",
        "PRODUCT_UPDATE": "แก้ไขสินค้า",
        "PRODUCT_DELETE": "ลบสินค้า",
        "PRODUCT_DELETE_ALL": "ลบสินค้าทั้งหมด",
        "PRODUCT_DELETE_ALL_TEST": "ลบสินค้าทดสอบทั้งหมด",
        "PRODUCT_BULK_DELETE": "ลบสินค้าหลายรายการ",
        "PRODUCT_BULK_IMPORT_ZIP": "นำเข้าสินค้าจากไฟล์ ZIP",
        "PRODUCT_RESTORE": "กู้คืนสินค้า",
        "STOCK_STOCK_IN": "รับสินค้าเข้า",
        "STOCK_STOCK_OUT": "เบิกหรือขายสินค้าออก",
        "SHEETS_IMPORT": "นำเข้าข้อมูลจาก Google Sheets",
        "DEV_GARBAGE_DELETE": "ลบไฟล์ขยะ",
        "DEV_RESET_STOCK": "ล้างข้อมูลสต็อก",
        "BACKUP_CREATE": "สร้างไฟล์สำรองข้อมูล",
        "BACKUP_RESTORE": "กู้คืนไฟล์สำรองข้อมูล",
    }
    return mapping.get(value, "การทำงานของระบบ")


def _entity_th(entity: str) -> str:
    value = str(entity or "").strip().lower()
    mapping = {
        "config": "การตั้งค่า",
        "user": "บัญชีผู้ใช้",
        "users": "บัญชีผู้ใช้",
        "product": "สินค้า",
        "products": "สินค้า",
        "stock": "สต็อก",
        "sheet": "Google Sheets",
        "sheets": "Google Sheets",
        "backup": "ไฟล์สำรองข้อมูล",
        "auth": "การยืนยันตัวตน",
    }
    return mapping.get(value, "ข้อมูลระบบ")


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


def _mix_channel(a: float, b: float, ratio: float) -> float:
    return round(a * (1 - ratio) + b * ratio, 4)


def _rgb(red: float, green: float, blue: float) -> dict:
    return {"red": red, "green": green, "blue": blue}


def _mix_color(base: dict, target: dict, ratio: float) -> dict:
    return _rgb(
        _mix_channel(base["red"], target["red"], ratio),
        _mix_channel(base["green"], target["green"], ratio),
        _mix_channel(base["blue"], target["blue"], ratio),
    )


def _hex_to_rgb(value: str, fallback: dict) -> dict:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) != 6:
        return dict(fallback)
    try:
        return _rgb(int(raw[0:2], 16) / 255.0, int(raw[2:4], 16) / 255.0, int(raw[4:6], 16) / 255.0)
    except Exception:
        return dict(fallback)


def _theme_sheet_styles() -> dict[str, dict]:
    cfg = load_master_config()
    primary = _hex_to_rgb(str(cfg.get("primary_color") or "#FF6B00"), _rgb(1.0, 0.42, 0.0))
    secondary = _hex_to_rgb(str(cfg.get("secondary_color") or "#1E6FD9"), _rgb(0.12, 0.44, 0.85))
    white = _rgb(1.0, 1.0, 1.0)
    black = _rgb(0.0, 0.0, 0.0)
    amber = _rgb(0.96, 0.65, 0.14)
    red = _rgb(0.83, 0.2, 0.2)
    green = _rgb(0.18, 0.62, 0.32)

    accent = _mix_color(primary, secondary, 0.45)
    soft_primary = _mix_color(primary, white, 0.78)
    soft_secondary = _mix_color(secondary, white, 0.8)
    soft_accent = _mix_color(accent, white, 0.82)

    return {
        TAB_OVERVIEW: {"tab": _mix_color(secondary, black, 0.12), "header": soft_secondary},
        TAB_STOCK: {"tab": _mix_color(secondary, black, 0.12), "header": soft_secondary},
        TAB_PRODUCT_IMPORT: {"tab": _mix_color(primary, secondary, 0.18), "header": _mix_color(primary, white, 0.84)},
        TAB_STOCK_ALERTS: {"tab": amber, "header": _mix_color(amber, white, 0.76)},
        TAB_ACCOUNTING: {"tab": _mix_color(accent, black, 0.08), "header": soft_accent},
        TAB_AUDIT_LOG: {"tab": red, "header": _mix_color(red, white, 0.82)},
        TAB_EDIT_LOG: {"tab": _mix_color(primary, amber, 0.38), "header": _mix_color(primary, white, 0.84)},
        TAB_ADD_LOG: {"tab": green, "header": _mix_color(green, white, 0.82)},
        TAB_SELL_LOG: {"tab": _mix_color(primary, amber, 0.64), "header": _mix_color(amber, white, 0.8)},
        TAB_INCOME_LOG: {"tab": _mix_color(green, secondary, 0.2), "header": _mix_color(green, white, 0.86)},
        TAB_EXPENSE_LOG: {"tab": _mix_color(red, primary, 0.2), "header": _mix_color(red, white, 0.86)},
        TAB_USERS: {"tab": _mix_color(secondary, primary, 0.28), "header": _mix_color(accent, white, 0.84)},
    }


def _find_existing_tab(sheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet | None:
    for candidate in [title, *LEGACY_TAB_ALIASES.get(title, [])]:
        try:
            return sheet.worksheet(candidate)
        except Exception:
            continue
    return None


def _ensure_tab(sheet: gspread.Spreadsheet, title: str, *, write_header: bool = True) -> gspread.Worksheet:
    ws = _find_existing_tab(sheet, title)
    if ws is None:
        ws = sheet.add_worksheet(title=title, rows=2000, cols=max(20, len(HEADERS.get(title, []))))
    elif ws.title != title:
        try:
            ws.update_title(title)
        except Exception:
            pass

    header = HEADERS.get(title)
    if write_header and header:
        try:
            ws.update([header], range_name="A1")
        except Exception:
            ws.clear()
            ws.update([header], range_name="A1")
    return ws


def _style_sheet(sheet: gspread.Spreadsheet, worksheets: list[gspread.Worksheet]) -> None:
    styles = _theme_sheet_styles()
    grid_line = _rgb(0.85, 0.88, 0.92)
    header_row_height = 36
    data_row_height = 26

    col_widths: dict[str, list[int]] = {
        TAB_STOCK: [120, 260, 150, 110, 140, 140, 130, 130, 140, 140, 170, 150, 150, 320, 160],
        TAB_PRODUCT_IMPORT: [120, 260, 150, 110, 140, 140, 130, 130, 150, 170, 260],
        TAB_STOCK_ALERTS: [140, 140, 260, 110, 110, 110, 140, 170, 300],
        TAB_AUDIT_LOG: [140, 170, 180, 150, 140, 260, 360, 170],
        TAB_EDIT_LOG: [170, 200, 140, 260, 360, 170],
        TAB_ADD_LOG: [170, 140, 260, 120, 110, 120, 140, 300, 170],
        TAB_SELL_LOG: [170, 140, 260, 140, 110, 120, 140, 300, 170],
        TAB_INCOME_LOG: [170, 180, 320, 140, 140, 160, 170],
        TAB_EXPENSE_LOG: [170, 180, 320, 140, 140, 160, 170],
        TAB_USERS: [140, 170, 220, 140, 140, 120, 170, 170],
        TAB_OVERVIEW: [220, 160, 360],
        TAB_ACCOUNTING: [220, 160, 360],
    }

    def _luma(color: dict) -> float:
        return (
            0.2126 * float(color.get("red", 0.0))
            + 0.7152 * float(color.get("green", 0.0))
            + 0.0722 * float(color.get("blue", 0.0))
        )

    def _text_for(bg: dict) -> dict:
        return _rgb(0.0, 0.0, 0.0) if _luma(bg) >= 0.62 else _rgb(1.0, 1.0, 1.0)

    def _header_bg_for(title: str, style: dict) -> dict:
        base = style.get("header") or style.get("tab")
        if isinstance(base, dict):
            return base
        return _rgb(0.12, 0.44, 0.85)

    def _filter_range(ws_id: int, cols: int) -> dict:
        return {"sheetId": ws_id, "startRowIndex": 0, "endRowIndex": 2000, "startColumnIndex": 0, "endColumnIndex": max(1, cols)}

    def _border_style(color: dict) -> dict:
        return {"style": "SOLID", "width": 1, "color": color}

    requests: list[dict] = []

    cf_counts: dict[int, int] = {}
    banded_ids: dict[int, list[int]] = {}
    try:
        meta = sheet.fetch_sheet_metadata()
        for sh in meta.get("sheets", []) or []:
            props = sh.get("properties") or {}
            sid = props.get("sheetId")
            if sid is None:
                continue
            sid_int = int(sid)
            cf_counts[sid_int] = len(sh.get("conditionalFormats") or [])
            banded_ids[sid_int] = [int(x.get("bandedRangeId")) for x in (sh.get("bandedRanges") or []) if x.get("bandedRangeId") is not None]
    except Exception:
        pass

    def _repeat_number(ws_id: int, cols: int, col_idx: int, nf_type: str, nf_pattern: str, align: str) -> None:
        if col_idx < 0 or col_idx >= cols:
            return
        requests.append(
            {
                "repeatCell": {
                    "range": {"sheetId": ws_id, "startRowIndex": 1, "endRowIndex": 2000, "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1},
                    "cell": {
                        "userEnteredFormat": {
                            "horizontalAlignment": align,
                            "verticalAlignment": "MIDDLE",
                            "numberFormat": {"type": nf_type, "pattern": nf_pattern},
                        }
                    },
                    "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,numberFormat)",
                }
            }
        )

    for ws in worksheets:
        header = HEADERS.get(ws.title) or []
        if not header:
            continue
        style = styles.get(ws.title) or {}
        cols = len(header)
        header_bg = _header_bg_for(ws.title, style)
        header_text = _text_for(header_bg)

        existing_cf = cf_counts.get(int(ws.id), 0)
        for idx in range(existing_cf - 1, -1, -1):
            requests.append({"deleteConditionalFormatRule": {"sheetId": ws.id, "index": idx}})
        for bid in banded_ids.get(int(ws.id), []) or []:
            requests.append({"deleteBanding": {"bandedRangeId": bid}})

        frozen_cols = 2 if ws.title == TAB_STOCK else 0
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ws.id,
                        "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": frozen_cols, "hideGridlines": True, "rowCount": 2000, "columnCount": max(20, cols)},
                        "tabColor": style.get("tab") or header_bg,
                    },
                    "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount,gridProperties.hideGridlines,gridProperties.rowCount,gridProperties.columnCount,tabColor",
                }
            }
        )
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": ws.id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                    "properties": {"pixelSize": header_row_height},
                    "fields": "pixelSize",
                }
            }
        )
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": ws.id, "dimension": "ROWS", "startIndex": 1, "endIndex": 2000},
                    "properties": {"pixelSize": data_row_height},
                    "fields": "pixelSize",
                }
            }
        )
        requests.append(
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": cols},
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": header_bg,
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": header_text},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)",
                }
            }
        )
        requests.append(
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 2000, "startColumnIndex": 0, "endColumnIndex": cols},
                    "cell": {
                        "userEnteredFormat": {
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                            "textFormat": {"fontSize": 10},
                        }
                    },
                    "fields": "userEnteredFormat(verticalAlignment,wrapStrategy,textFormat)",
                }
            }
        )
        requests.append(
            {
                "updateBorders": {
                    "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 2000, "startColumnIndex": 0, "endColumnIndex": cols},
                    "top": _border_style(grid_line),
                    "bottom": _border_style(grid_line),
                    "left": _border_style(grid_line),
                    "right": _border_style(grid_line),
                }
            }
        )
        requests.append({"updateBorders": {"range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": cols}, "bottom": {"style": "SOLID", "width": 2, "color": grid_line}}})
        requests.append({"clearBasicFilter": {"sheetId": ws.id}})
        requests.append({"setBasicFilter": {"filter": {"range": _filter_range(ws.id, cols)}}})

        widths = col_widths.get(ws.title)
        if widths:
            for idx, px in enumerate(widths[:cols]):
                requests.append(
                    {
                        "updateDimensionProperties": {
                            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": idx, "endIndex": idx + 1},
                            "properties": {"pixelSize": int(px)},
                            "fields": "pixelSize",
                        }
                    }
                )

        requests.append(
            {
                "addBanding": {
                    "bandedRange": {
                        "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 2000, "startColumnIndex": 0, "endColumnIndex": cols},
                        "rowProperties": {
                            "headerColor": header_bg,
                            "firstBandColor": _rgb(1.0, 1.0, 1.0),
                            "secondBandColor": _rgb(0.98, 0.99, 1.0),
                        },
                    }
                }
            }
        )

        if ws.title == TAB_STOCK:
            _repeat_number(ws.id, cols, 4, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 5, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 6, "NUMBER", "฿#,##0.00", "RIGHT")
            _repeat_number(ws.id, cols, 7, "NUMBER", "฿#,##0.00", "RIGHT")
            _repeat_number(ws.id, cols, 8, "PERCENT", "0.0%", "RIGHT")
            _repeat_number(ws.id, cols, 10, "PERCENT", "0%", "RIGHT")
            _repeat_number(ws.id, cols, 14, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")
            status_col = 9
            if status_col < cols:
                def _cf(text: str, bg: dict, fg: dict) -> dict:
                    return {
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 2000, "startColumnIndex": status_col, "endColumnIndex": status_col + 1}],
                                "booleanRule": {
                                    "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": text}]},
                                    "format": {"backgroundColor": bg, "textFormat": {"foregroundColor": fg, "bold": True}},
                                },
                            },
                            "index": 0,
                        }
                    }
                requests.extend(
                    [
                        _cf("Stock หมด", _rgb(0.1, 0.1, 0.1), _text_for(_rgb(0.1, 0.1, 0.1))),
                        _cf("ควรเติม", _rgb(0.83, 0.2, 0.2), _text_for(_rgb(0.83, 0.2, 0.2))),
                        _cf("ใกล้หมด", _rgb(0.96, 0.65, 0.14), _rgb(0.0, 0.0, 0.0)),
                        _cf("Stock เต็ม", _rgb(0.18, 0.62, 0.32), _text_for(_rgb(0.18, 0.62, 0.32))),
                        _cf("ปกติ", _rgb(0.45, 0.45, 0.45), _text_for(_rgb(0.45, 0.45, 0.45))),
                    ]
                )

        if ws.title == TAB_PRODUCT_IMPORT:
            _repeat_number(ws.id, cols, 4, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 5, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 6, "NUMBER", "฿#,##0.00", "RIGHT")
            _repeat_number(ws.id, cols, 7, "PERCENT", "0%", "RIGHT")
            _repeat_number(ws.id, cols, 9, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")

        if ws.title == TAB_STOCK_ALERTS:
            _repeat_number(ws.id, cols, 3, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 4, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 5, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 7, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")

        if ws.title == TAB_EDIT_LOG:
            _repeat_number(ws.id, cols, 0, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")

        if ws.title == TAB_ADD_LOG:
            _repeat_number(ws.id, cols, 0, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")
            _repeat_number(ws.id, cols, 3, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 5, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 6, "NUMBER", "#,##0.##", "RIGHT")

        if ws.title == TAB_SELL_LOG:
            _repeat_number(ws.id, cols, 0, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")
            _repeat_number(ws.id, cols, 3, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 5, "NUMBER", "#,##0.##", "RIGHT")
            _repeat_number(ws.id, cols, 6, "NUMBER", "#,##0.##", "RIGHT")

        if ws.title == TAB_AUDIT_LOG:
            _repeat_number(ws.id, cols, 1, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")

        if ws.title == TAB_INCOME_LOG:
            _repeat_number(ws.id, cols, 0, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")
            _repeat_number(ws.id, cols, 3, "NUMBER", "฿#,##0.00", "RIGHT")

        if ws.title == TAB_EXPENSE_LOG:
            _repeat_number(ws.id, cols, 0, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")
            _repeat_number(ws.id, cols, 3, "NUMBER", "฿#,##0.00", "RIGHT")

        if ws.title == TAB_USERS:
            _repeat_number(ws.id, cols, 6, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")
            _repeat_number(ws.id, cols, 7, "DATE_TIME", "yyyy-mm-dd hh:mm:ss", "CENTER")

        if ws.title in (TAB_STOCK_ALERTS, TAB_AUDIT_LOG):
            sev_col = 0
            if sev_col < cols:
                def _sev(text: str, bg: dict, fg: dict) -> dict:
                    return {
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 2000, "startColumnIndex": sev_col, "endColumnIndex": sev_col + 1}],
                                "booleanRule": {
                                    "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": text}]},
                                    "format": {"backgroundColor": bg, "textFormat": {"foregroundColor": fg, "bold": True}},
                                },
                            },
                            "index": 0,
                        }
                    }
                requests.extend(
                    [
                        _sev("🟥", _rgb(0.83, 0.2, 0.2), _text_for(_rgb(0.83, 0.2, 0.2))),
                        _sev("🟨", _rgb(0.96, 0.65, 0.14), _rgb(0.0, 0.0, 0.0)),
                        _sev("🟩", _rgb(0.18, 0.62, 0.32), _text_for(_rgb(0.18, 0.62, 0.32))),
                    ]
                )

    if requests:
        sheet.batch_update({"requests": requests})


def ensure_workbook_template(sheet: gspread.Spreadsheet, *, write_headers: bool = True) -> list[gspread.Worksheet]:
    tabs = [_ensure_tab(sheet, title, write_header=write_headers) for title in WORKBOOK_TABS]
    _style_sheet(sheet, tabs)
    return tabs


def create_stock_workbook(client: gspread.client.Client, title: str) -> gspread.Spreadsheet:
    sheet = client.create(title)
    ensure_workbook_template(sheet)
    return sheet


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


def _format_sheet_number(value: float | int | None) -> str:
    number = float(value or 0)
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _build_import_template_rows(products: list[dict]) -> list[list[str]]:
    rows = [HEADERS[TAB_PRODUCT_IMPORT][:]]
    for product in sorted(products, key=lambda item: str(item.get("sku") or "")):
        sku = str(product.get("sku") or "").strip()
        if not sku:
            continue
        qty = float(product.get("stock_qty") or 0)
        max_qty = float(product.get("max_stock") or 0)
        min_qty = float(product.get("min_stock") or 0)
        price = product.get("selling_price")
        if price is None:
            price = product.get("cost_price") or 0
        threshold = (min_qty / max_qty * 100.0) if max_qty > 0 and min_qty > 0 else 60.0
        rows.append(
            [
                sku,
                str(product.get("name_th") or ""),
                str(product.get("category") or ""),
                str(product.get("unit") or ""),
                _format_sheet_number(qty),
                _format_sheet_number(max_qty) if max_qty > 0 else "",
                _format_sheet_number(float(price or 0)) if float(price or 0) > 0 else "",
                _format_sheet_number(threshold),
                str(product.get("status") or ""),
                str(product.get("updated_at") or ""),
                "",
            ]
        )
    return rows


def _resolve_import_source_tab(source: str | None) -> str:
    normalized = str(source or "stock").strip().lower().replace("-", "_")
    if normalized in ("stock", "stock_sheet", "default"):
        return TAB_STOCK
    if normalized in ("import", "import_tab", "import_template", "product_import"):
        return TAB_PRODUCT_IMPORT
    raise ValueError("invalid_import_source")


def _severity_label(action: str, success: bool, status: str = "") -> str:
    if not success:
        return "🟥 สำคัญ"
    if status in ("OUT", "CRITICAL"):
        return "🟥 สำคัญ"
    if status == "LOW":
        return "🟨 เฝ้าระวัง"
    if action.startswith("DEV_"):
        return "🟨 ตรวจสอบ"
    return "🟩 ปกติ"


def _write_rows(ws: gspread.Worksheet, rows: list[list]) -> None:
    ws.clear()
    ws.update(rows)


def _sync_stock_sheet(ws: gspread.Worksheet, products: list[dict]) -> None:
    values = ws.get_all_values()
    if not values:
        values = [HEADERS[TAB_STOCK]]

    header = values[0]
    if not header:
        header = HEADERS[TAB_STOCK]
        values = [header]

    id_idx = _get_col_idx(header, ["รหัสสินค้า", "ID", "Sku", "SKU"])
    if id_idx is None:
        header = HEADERS[TAB_STOCK]
        values = [header]
        id_idx = 0

    name_idx = _get_col_idx(header, ["ชื่อสินค้า", "Name"])
    type_idx = _get_col_idx(header, ["หมวดหมู่", "ประเภท", "Category"])
    unit_idx = _get_col_idx(header, ["หน่วยนับ", "หน่วย", "Unit"])
    qty_idx = _get_col_idx(header, ["จำนวนคงเหลือ", "จำนวนปัจจุบัน", "Current_Qty"])
    max_idx = _get_col_idx(header, ["จำนวนที่ควรมี", "Max_Stock"])
    price_idx = _get_col_idx(header, ["ราคาต่อหน่วย", "Unit_Price"])
    total_idx = _get_col_idx(header, ["มูลค่ารวม", "Total_Value"])
    pct_idx = _get_col_idx(header, ["เปอร์เซ็นต์คงเหลือ", "% คงเหลือ", "%", "Pct"])
    status_idx = _get_col_idx(header, ["สถานะสต็อก", "สถานะ", "Status"])
    threshold_idx = _get_col_idx(header, ["เกณฑ์แจ้งเตือน (%)", "เกณฑ์แจ้งเตือน%", "Threshold%"])
    msg_idx = _get_col_idx(header, ["ข้อความแจ้งเตือน", "Message"])
    updated_idx = _get_col_idx(header, ["อัปเดตล่าสุด", "Last_Updated"])

    row_by_id: dict[str, list[str]] = {}
    for i in range(1, len(values)):
        row = values[i]
        if id_idx < len(row):
            key = (row[id_idx] or "").strip()
            if key:
                row_by_id[key] = row

    now = datetime.utcnow().isoformat(timespec="seconds")

    def ensure_len(r: list[str]) -> list[str]:
        if len(r) < len(header):
            return r + [""] * (len(header) - len(r))
        return r[: len(header)]

    next_values = [ensure_len(header)]

    for p in sorted(products, key=lambda item: str(item.get("sku") or "")):
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

        existing_row = row_by_id.get(pid)
        row = ensure_len(existing_row if existing_row is not None else [""] * len(header))
        row[id_idx] = pid

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

        next_values.append(row)

    col_count = len(header)
    end_col = gspread.utils.rowcol_to_a1(1, col_count).split("1")[0]
    ws.clear()
    ws.update(f"A1:{end_col}{len(next_values)}", next_values)


async def _collect_products_for_sheet_rows() -> list[dict]:
    products_data: list[dict] = []
    async with SessionLocal() as db:
        res = await db.execute(select(Product))
        products = [p for p in res.scalars().all() if not _is_deleted_product(p)]
        for p in products:
            updated = p.updated_at.isoformat(timespec="seconds") if p.updated_at else datetime.utcnow().isoformat(timespec="seconds")
            products_data.append(
                {
                    "id": p.id,
                    "sku": p.sku,
                    "name_th": p.name_th,
                    "category": p.category,
                    "unit": p.unit,
                    "stock_qty": float(p.stock_qty or 0),
                    "min_stock": float(p.min_stock or 0),
                    "max_stock": float(p.max_stock or 0),
                    "cost_price": float(p.cost_price or 0),
                    "selling_price": float(p.selling_price) if p.selling_price is not None else None,
                    "status": p.status.value,
                    "updated_at": updated,
                }
            )
    return products_data


def _normalize_import_values(values: list[list[object]] | None) -> list[list[str]]:
    normalized: list[list[str]] = []
    for row in values or []:
        if not isinstance(row, list):
            continue
        normalized.append(["" if cell is None else str(cell).strip() for cell in row])
    return normalized


def _read_import_csv_values(csv_bytes: bytes) -> list[list[str]]:
    text = (csv_bytes or b"").decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return _normalize_import_values([list(row) for row in reader])


async def _import_stock_from_values(
    values: list[list[object]] | None,
    *,
    actor_id: str | None = None,
    overwrite_stock_qty: bool = False,
    overwrite_prices: bool = False,
) -> dict:
    values = _normalize_import_values(values)
    if not values:
        return {"ok": False, "error": "import_data_empty"}
    if len(values) < 2:
        return {"ok": True, "created": 0, "updated": 0, "skipped": 0}

    header = values[0]
    id_idx = _get_col_idx(header, ["รหัสสินค้า", "ID", "SKU", "Sku"])
    name_idx = _get_col_idx(header, ["ชื่อสินค้า", "Name"])
    type_idx = _get_col_idx(header, ["หมวดหมู่", "ประเภท", "Category"])
    unit_idx = _get_col_idx(header, ["หน่วยนับ", "หน่วย", "Unit"])
    qty_idx = _get_col_idx(header, ["จำนวนคงเหลือ", "จำนวนปัจจุบัน", "Current_Qty"])
    max_idx = _get_col_idx(header, ["จำนวนที่ควรมี", "Max_Stock"])
    price_idx = _get_col_idx(header, ["ราคาต่อหน่วย", "Unit_Price"])
    threshold_idx = _get_col_idx(header, ["เกณฑ์แจ้งเตือน (%)", "เกณฑ์แจ้งเตือน%", "Threshold%"])

    if id_idx is None or name_idx is None:
        return {"ok": False, "error": "missing_required_columns"}

    created = 0
    updated = 0
    skipped = 0

    async with SessionLocal() as db:
        actor = None
        default_branch = await ensure_default_branch(db)
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
                    branch_id=default_branch.id,
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
                if not p.branch_id:
                    p.branch_id = default_branch.id
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
            await db.flush()
            await sync_product_supplier_links(db, product=p, actor_id=actor_id_resolved)

        await db.commit()

    return {"ok": True, "created": created, "updated": updated, "skipped": skipped}


async def sync_product_import_template_to_sheet(*, fail_if_busy: bool = False) -> bool:
    if _is_quota_cooling_down():
        remaining = _quota_cooldown_remaining()
        if fail_if_busy:
            raise RuntimeError(f"google_sheets_quota_cooldown:{remaining}")
        logger.warning("Skipping Google Sheets import template sync during quota cooldown (%ss remaining)", remaining)
        return False

    if _SYNC_LOCK.locked():
        if fail_if_busy:
            raise RuntimeError("google_sheets_sync_in_progress")
        logger.info("Skipping overlapping Google Sheets import template sync request")
        return False

    products_data = await _collect_products_for_sheet_rows()
    import_rows = _build_import_template_rows(products_data)

    def _sync_blocking() -> None:
        client = get_client()
        if not client:
            raise RuntimeError("gsheets_not_configured")
        sheet = client.open_by_key(settings.google_sheets_id)
        workbook_tabs = {ws.title: ws for ws in ensure_workbook_template(sheet, write_headers=False)}
        ws_import = workbook_tabs[TAB_PRODUCT_IMPORT]
        _write_rows(ws_import, import_rows)

    async with _SYNC_LOCK:
        try:
            await _with_retries(lambda: asyncio.to_thread(_sync_blocking), retries=3, delay_sec=1.5)
            return True
        except Exception as e:
            if _is_quota_error(e):
                _set_quota_cooldown()
            if fail_if_busy:
                raise
            logger.error(f"Google Sheets import template sync failed: {e}")
            return False


async def import_stock_from_sheet(
    *,
    actor_id: str | None = None,
    source: str = "stock",
    overwrite_stock_qty: bool = False,
    overwrite_prices: bool = False,
    fail_if_busy: bool = False,
) -> dict:
    try:
        tab_title = _resolve_import_source_tab(source)
    except ValueError:
        if fail_if_busy:
            raise RuntimeError("invalid_import_source")
        return {"ok": False, "error": "invalid_import_source"}

    if _is_quota_cooling_down():
        remaining = _quota_cooldown_remaining()
        if fail_if_busy:
            raise RuntimeError(f"google_sheets_quota_cooldown:{remaining}")
        logger.warning("Skipping Google Sheets import during quota cooldown (%ss remaining)", remaining)
        return {"ok": False, "error": "google_sheets_quota_cooldown"}

    if _IMPORT_LOCK.locked():
        if fail_if_busy:
            raise RuntimeError("google_sheets_import_in_progress")
        logger.info("Skipping overlapping Google Sheets import request")
        return {"ok": False, "error": "google_sheets_import_in_progress"}

    def _read_values_blocking():
        client = get_client()
        if not client:
            return None
        sheet = client.open_by_key(settings.google_sheets_id)
        ws = _ensure_tab(sheet, tab_title, write_header=(tab_title == TAB_PRODUCT_IMPORT))
        return ws.get_all_values()

    async with _IMPORT_LOCK:
        try:
            values = await _with_retries(lambda: asyncio.to_thread(_read_values_blocking), retries=3, delay_sec=1.5)
        except Exception as e:
            if _is_quota_error(e):
                _set_quota_cooldown()
            if fail_if_busy:
                raise
            logger.error(f"Google Sheets import failed: {e}")
            return {"ok": False, "error": str(e)}
    if not values:
        return {"ok": False, "error": "sheets_not_configured"}
    return await _import_stock_from_values(
        values,
        actor_id=actor_id,
        overwrite_stock_qty=overwrite_stock_qty,
        overwrite_prices=overwrite_prices,
    )


async def import_stock_from_csv_bytes(
    csv_bytes: bytes,
    *,
    actor_id: str | None = None,
    overwrite_stock_qty: bool = False,
    overwrite_prices: bool = False,
    fail_if_busy: bool = False,
) -> dict:
    if _IMPORT_LOCK.locked():
        if fail_if_busy:
            raise RuntimeError("google_sheets_import_in_progress")
        logger.info("Skipping overlapping CSV import request")
        return {"ok": False, "error": "google_sheets_import_in_progress"}

    async with _IMPORT_LOCK:
        try:
            values = _read_import_csv_values(csv_bytes)
        except Exception as e:
            if fail_if_busy:
                raise
            logger.error(f"CSV import parse failed: {e}")
            return {"ok": False, "error": "invalid_import_file"}

    return await _import_stock_from_values(
        values,
        actor_id=actor_id,
        overwrite_stock_qty=overwrite_stock_qty,
        overwrite_prices=overwrite_prices,
    )


async def sync_all_to_sheets(*, fail_if_busy: bool = False, include_import_tab: bool = False) -> bool:
    if _is_quota_cooling_down():
        remaining = _quota_cooldown_remaining()
        if fail_if_busy:
            raise RuntimeError(f"google_sheets_quota_cooldown:{remaining}")
        logger.warning("Skipping Google Sheets sync during quota cooldown (%ss remaining)", remaining)
        return False

    if _SYNC_LOCK.locked():
        if fail_if_busy:
            raise RuntimeError("google_sheets_sync_in_progress")
        logger.info("Skipping overlapping Google Sheets sync request")
        return False

    cfg = load_master_config()
    products_data: list[dict] = []
    product_by_id: dict[str, dict] = {}
    status_counts = {"FULL": 0, "NORMAL": 0, "LOW": 0, "CRITICAL": 0, "OUT": 0}
    alert_rows = [HEADERS[TAB_STOCK_ALERTS]]
    overview_rows = [HEADERS[TAB_OVERVIEW]]
    accounting_rows = [HEADERS[TAB_ACCOUNTING]]
    audit_rows = [HEADERS[TAB_AUDIT_LOG]]
    add_rows = [HEADERS[TAB_ADD_LOG]]
    sell_rows = [HEADERS[TAB_SELL_LOG]]
    income_rows = [HEADERS[TAB_INCOME_LOG]]
    expense_rows = [HEADERS[TAB_EXPENSE_LOG]]
    edit_rows = [HEADERS[TAB_EDIT_LOG]]
    user_rows = [HEADERS[TAB_USERS]]
    total_stock_value = 0.0
    total_sell_qty = 0.0
    total_income_value = 0.0
    total_expense_value = 0.0

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
                "min_stock": float(p.min_stock or 0),
                "max_stock": float(p.max_stock or 0),
                "cost_price": float(p.cost_price or 0),
                "selling_price": float(p.selling_price) if p.selling_price is not None else None,
                "status": p.status.value,
                "updated_at": updated,
            }
            products_data.append(pd)
            product_by_id[p.id] = {"sku": p.sku, "name_th": p.name_th, "unit": p.unit}
            total_stock_value += float(p.stock_qty or 0) * float(p.cost_price or 0)
            status_counts[p.status.value] = status_counts.get(p.status.value, 0) + 1
            if p.status.value in ("LOW", "CRITICAL", "OUT"):
                note = "ยังพอขายได้" if p.status.value == "LOW" else "ควรเติมด่วน" if p.status.value == "CRITICAL" else "สินค้าหมด"
                alert_rows.append(
                    [
                        _severity_label("", True, p.status.value),
                        p.sku,
                        p.name_th,
                        float(p.stock_qty or 0),
                        float(p.min_stock or 0),
                        float(p.max_stock or 0),
                        _status_th(p.status.value),
                        updated,
                        note,
                    ]
                )

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
                    total_expense_value += delta
                add_rows.append([ts, sku, name_th, delta, unit, qty_before or "", qty_after or "", msg, actor])
                continue

            if x.action == "STOCK_STOCK_OUT":
                delta = ""
                if isinstance(qty_before, (int, float)) and isinstance(qty_after, (int, float)):
                    delta = max(0.0, float(qty_before) - float(qty_after))
                    total_sell_qty += float(delta or 0)
                sell_rows.append([ts, sku, name_th, delta, unit, qty_before or "", qty_after or "", msg, actor])
                continue

            if x.action.startswith("STOCK_") or x.action.startswith("PRODUCT_"):
                edit_rows.append([ts, _action_th(x.action), sku, name_th, msg, actor])

            audit_rows.append([
                _severity_label(x.action, bool(x.success)),
                ts,
                _action_th(x.action),
                _entity_th(x.entity),
                sku,
                name_th,
                msg,
                actor,
            ])

        res = await db.execute(select(User).order_by(User.role.asc(), User.username.asc()))
        users = res.scalars().all()
        for user in users:
            user_rows.append(
                [
                    user.id,
                    user.username,
                    user.display_name or "",
                    _role_th(user.role),
                    "ใช้งาน" if user.is_active else "ปิดใช้งาน",
                    user.language or "th",
                    user.created_at.isoformat(sep=" ", timespec="seconds") if user.created_at else "",
                    user.updated_at.isoformat(sep=" ", timespec="seconds") if user.updated_at else "",
                ]
            )

    total_income_value = 0.0
    for row in sell_rows[1:]:
        try:
            qty = float(row[3] or 0)
        except Exception:
            qty = 0.0
        total_income_value += qty

    overview_rows.extend(
        [
            ["โหมดการใช้งาน", "ดูข้อมูลและสรุปผล", "ชีตนี้เน้นใช้ติดตามและสรุปผลเป็นหลัก"],
            ["ระบบ Stock ทำงาน", datetime.utcnow().isoformat(timespec="seconds"), "เวลาที่ sync ขึ้นชีตล่าสุด"],
            ["ชื่อระบบ", str(cfg.get("app_name") or "ระบบจัดการสต็อกองค์กร"), "ชื่อเว็บไซต์ที่เชื่อมต่ออยู่"],
            ["บัญชี Google ที่เชื่อมต่อ", str(cfg.get("google_workspace_email") or "-"), "บัญชีที่ใช้สร้างหรือดูแลไฟล์ Google Sheets นี้"],
            ["สินค้าทั้งหมด", len(products_data), "จำนวนสินค้าที่ใช้งานอยู่ในระบบ"],
            ["บัญชีผู้ใช้งานทั้งหมด", max(0, len(user_rows) - 1), f"ดูรายละเอียดต่อในแท็บ {TAB_USERS}"],
            ["สต็อกเต็ม", status_counts.get("FULL", 0), "สีเขียว = เต็ม"],
            ["สต็อกปกติ", status_counts.get("NORMAL", 0), "สีฟ้า = ปกติ"],
            ["สินค้าใกล้หมด", status_counts.get("LOW", 0), "สีเหลือง = เฝ้าระวัง"],
            ["สินค้าควรเติม", status_counts.get("CRITICAL", 0), "สีส้ม/แดง = ควรเติมด่วน"],
            ["สินค้าหมด", status_counts.get("OUT", 0), "สีแดง = หมดสต็อก"],
            ["มูลค่าสต็อกโดยประมาณ", f"{total_stock_value:.2f}", "อิงจากต้นทุนสินค้า"],
            ["จำนวนรายการแจ้งเตือน", max(0, len(alert_rows) - 1), f"ดูรายละเอียดต่อในแท็บ {TAB_STOCK_ALERTS}"],
        ]
    )
    accounting_rows.extend(
        [
            ["รายการรับเข้า", max(0, len(add_rows) - 1), "มาจากรายการรับสินค้าเข้า"],
            ["รายการขาย/เบิกออก", max(0, len(sell_rows) - 1), "มาจากรายการเบิกหรือขายสินค้าออก"],
            ["จำนวนรับเข้ารวม", f"{total_expense_value:.2f}", f"หน่วยรวมจากแท็บ {TAB_ADD_LOG}"],
            ["จำนวนขาย/เบิกรวม", f"{total_sell_qty:.2f}", f"หน่วยรวมจากแท็บ {TAB_SELL_LOG}"],
            ["มูลค่าสต็อกปัจจุบัน", f"{total_stock_value:.2f}", "อิงจากต้นทุนสินค้าในคลัง"],
            ["แท็บรายรับ", TAB_INCOME_LOG, "ใช้เก็บรายรับเพิ่มเติมได้"],
            ["แท็บรายจ่าย", TAB_EXPENSE_LOG, "ใช้เก็บรายจ่ายเพิ่มเติมได้"],
            ["แท็บบัญชีผู้ใช้งาน", TAB_USERS, "รวมข้อมูลบัญชีของผู้ใช้งานในระบบนี้"],
        ]
    )
    import_rows = _build_import_template_rows(products_data) if include_import_tab else None

    def _sync_blocking() -> None:
        client = get_client()
        if not client:
            return
        sheet = client.open_by_key(settings.google_sheets_id)
        workbook_tabs = {ws.title: ws for ws in ensure_workbook_template(sheet, write_headers=False)}
        ws_overview = workbook_tabs[TAB_OVERVIEW]
        ws_stock = workbook_tabs[TAB_STOCK]
        ws_import = workbook_tabs[TAB_PRODUCT_IMPORT]
        ws_alerts = workbook_tabs[TAB_STOCK_ALERTS]
        ws_accounting = workbook_tabs[TAB_ACCOUNTING]
        ws_audit = workbook_tabs[TAB_AUDIT_LOG]
        ws_edit = workbook_tabs[TAB_EDIT_LOG]
        ws_add = workbook_tabs[TAB_ADD_LOG]
        ws_sell = workbook_tabs[TAB_SELL_LOG]
        ws_income = workbook_tabs[TAB_INCOME_LOG]
        ws_expense = workbook_tabs[TAB_EXPENSE_LOG]
        ws_users = workbook_tabs[TAB_USERS]

        _write_rows(ws_overview, overview_rows)
        _sync_stock_sheet(ws_stock, products_data)
        if include_import_tab and import_rows is not None:
            _write_rows(ws_import, import_rows)
        _write_rows(ws_alerts, alert_rows)
        _write_rows(ws_accounting, accounting_rows)
        _write_rows(ws_audit, audit_rows)
        _write_rows(ws_add, add_rows)
        _write_rows(ws_sell, sell_rows)
        _write_rows(ws_income, income_rows)
        _write_rows(ws_expense, expense_rows)
        _write_rows(ws_edit, edit_rows)
        _write_rows(ws_users, user_rows)
        _style_sheet(sheet, [ws_overview, ws_stock, ws_import, ws_alerts, ws_accounting, ws_audit, ws_add, ws_sell, ws_edit, ws_income, ws_expense, ws_users])

    async with _SYNC_LOCK:
        try:
            await _with_retries(lambda: asyncio.to_thread(_sync_blocking), retries=3, delay_sec=2.0)
            logger.info("Google Sheets sync completed")
            return True
        except Exception as e:
            if _is_quota_error(e):
                _set_quota_cooldown()
            logger.error(f"Google Sheets sync failed: {e}")
            if fail_if_busy:
                raise
            return False

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
