from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


MEDIA_ROOT = Path(__file__).resolve().parents[2] / "storage" / "media" / "products"
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
MAX_ZIP_SIZE_BYTES = 50 * 1024 * 1024
MAX_ZIP_ITEMS = 1000
MAX_DIM = 1280
WEBP_QUALITY = 82


def ensure_media_root() -> Path:
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    return MEDIA_ROOT


def _slug(v: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", (v or "").strip())
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    return s or "item"


def product_image_relpath(sku: str) -> str:
    safe = _slug(sku).upper()
    return f"/media/products/{safe}.webp"


def _save_webp(raw: bytes, target_path: Path) -> None:
    if len(raw) > MAX_IMAGE_SIZE_BYTES:
        raise ValueError("image_too_large")
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            img.thumbnail((MAX_DIM, MAX_DIM))
            target_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(target_path, format="WEBP", quality=WEBP_QUALITY, method=6)
    except Exception as e:
        raise ValueError("invalid_image_file") from e


def save_product_image_bytes(sku: str, raw: bytes) -> str:
    ensure_media_root()
    rel = product_image_relpath(sku)
    fs_path = Path(__file__).resolve().parents[2] / rel.lstrip("/").replace("/", os.sep)
    _save_webp(raw, fs_path)
    return rel


@dataclass
class BulkRow:
    index: int
    sku: str
    name_th: str
    category: str
    unit: str
    stock_qty: float
    min_stock: float
    max_stock: float
    cost_price: float
    selling_price: float | None
    image_key: str


def _f(v: str | None, default: float = 0.0) -> float:
    try:
        return float((v or "").strip() or default)
    except Exception:
        return default


def parse_products_csv(data: bytes) -> list[BulkRow]:
    txt = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(txt))
    out: list[BulkRow] = []
    for i, r in enumerate(reader, start=2):
        sku = (r.get("sku") or "").strip()
        name_th = (r.get("name_th") or "").strip()
        if not sku or not name_th:
            continue
        selling_raw = (r.get("selling_price") or "").strip()
        out.append(
            BulkRow(
                index=i,
                sku=sku,
                name_th=name_th,
                category=(r.get("category") or "").strip(),
                unit=(r.get("unit") or "").strip(),
                stock_qty=_f(r.get("stock_qty"), 0.0),
                min_stock=_f(r.get("min_stock"), 0.0),
                max_stock=_f(r.get("max_stock"), 0.0),
                cost_price=_f(r.get("cost_price"), 0.0),
                selling_price=_f(selling_raw, 0.0) if selling_raw else None,
                image_key=(r.get("image_key") or "").strip(),
            )
        )
    return out


def read_zip_payload(zip_bytes: bytes) -> tuple[list[BulkRow], dict[str, bytes]]:
    if len(zip_bytes) > MAX_ZIP_SIZE_BYTES:
        raise ValueError("zip_too_large")
    csv_data: bytes | None = None
    images: dict[str, bytes] = {}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ITEMS:
            raise ValueError("zip_too_many_files")
        for info in infos:
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if ".." in name:
                raise ValueError("unsafe_zip_path")
            base = Path(name).name
            lower = base.lower()
            if lower == "products.csv":
                csv_data = zf.read(info)
                continue
            ext = Path(base).suffix.lower()
            if ext in ALLOWED_IMAGE_EXT:
                key = Path(base).stem.strip()
                if key:
                    images[key] = zf.read(info)
    if not csv_data:
        raise ValueError("products_csv_not_found")
    return parse_products_csv(csv_data), images


def choose_image_for_row(row: BulkRow, images: dict[str, bytes]) -> bytes | None:
    if row.image_key and row.image_key in images:
        return images[row.image_key]
    if row.sku in images:
        return images[row.sku]
    return None


def media_public_root() -> Path:
    return (Path(__file__).resolve().parents[2] / "storage" / "media").resolve()


def is_media_path_unused(path: str, referenced_paths: set[str]) -> bool:
    if not path or not path.startswith("/media/products/"):
        return False
    return path not in referenced_paths
