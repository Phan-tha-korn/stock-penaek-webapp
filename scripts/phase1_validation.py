import io
import json
import zipfile
from uuid import uuid4

import requests
from PIL import Image

BASE = "http://localhost:8000/api"


def make_token(username: str, password: str, phrase: str) -> str:
  r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": password, "secret_phrase": phrase}, timeout=20)
  r.raise_for_status()
  return r.json()["access_token"]


def make_headers(token: str) -> dict:
  return {"Authorization": f"Bearer {token}"}


def tiny_png() -> bytes:
  buf = io.BytesIO()
  Image.new("RGB", (8, 8), color=(255, 120, 0)).save(buf, format="PNG")
  return buf.getvalue()


def build_zip(zip_sku: str) -> bytes:
  csv_text = (
    "sku,name_th,category,unit,stock_qty,min_stock,max_stock,cost_price,selling_price,image_key\n"
    f"{zip_sku},น้ำปลา bulk,วัตถุดิบ,ขวด,9,2,25,12.5,16.0,001\n"
  )
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("products.csv", csv_text)
    zf.writestr("001.png", tiny_png())
  return buf.getvalue()


def main() -> None:
  cfg = requests.get(f"{BASE}/config", timeout=20).json()
  phrase = cfg.get("login_secret_phrase", "") or ""
  owner = make_token("owner", "Owner@1234", phrase)
  stock = make_token("stock", "Stock@1234", phrase)

  results = []
  run_id = uuid4().hex[:6].upper()
  sku = f"IMG-SINGLE-{run_id}"
  zip_sku = f"ZIP-ITEM-{run_id}"

  # single create with image
  files = {"image": ("single.png", tiny_png(), "image/png")}
  data = {
    "sku": sku,
    "name_th": "สินค้าทดสอบรูปเดี่ยว",
    "category": "ทดสอบ",
    "unit": "ชิ้น",
    "stock_qty": "3",
    "min_stock": "1",
    "max_stock": "10",
    "cost_price": "5.5",
    "selling_price": "8.0",
  }
  r = requests.post(f"{BASE}/products/create-with-image", headers=make_headers(owner), data=data, files=files, timeout=40)
  results.append({"feature": "create_with_image", "status": "PASS" if r.status_code == 200 else "FAIL", "code": r.status_code})

  # update with image
  r2 = requests.post(
    f"{BASE}/products/{sku}/update-with-image",
    headers=make_headers(owner),
    data={"name_th": "สินค้าทดสอบรูปเดี่ยว-อัปเดต", "cost_price": "6.0"},
    files={"image": ("update.png", tiny_png(), "image/png")},
    timeout=40,
  )
  results.append({"feature": "update_with_image", "status": "PASS" if r2.status_code == 200 else "FAIL", "code": r2.status_code})

  # bulk zip import
  zip_bytes = build_zip(zip_sku)
  r3 = requests.post(
    f"{BASE}/products/bulk-import-zip",
    headers=make_headers(owner),
    data={"overwrite_existing": "true"},
    files={"file": ("bulk.zip", zip_bytes, "application/zip")},
    timeout=60,
  )
  ok_bulk = r3.status_code == 200 and r3.json().get("ok") is True
  results.append({"feature": "bulk_import_zip", "status": "PASS" if ok_bulk else "FAIL", "code": r3.status_code})

  # stock can read imported
  r4 = requests.get(f"{BASE}/products?q={zip_sku}", headers=make_headers(stock), timeout=20)
  found_bulk = r4.status_code == 200 and any(x.get("sku") == zip_sku for x in r4.json().get("items", []))
  results.append({"feature": "stock_search_bulk_item", "status": "PASS" if found_bulk else "FAIL", "code": r4.status_code})

  # public read-only endpoint
  r5 = requests.get(f"{BASE}/products/public/products/{sku}", timeout=20)
  has_fields = r5.status_code == 200 and ("cost_price" in r5.json()) and ("stock_qty" in r5.json())
  results.append({"feature": "public_readonly_fields", "status": "PASS" if has_fields else "FAIL", "code": r5.status_code})

  # cleanup
  requests.post(f"{BASE}/products/{sku}/delete", headers=make_headers(owner), json={"reason": "phase1_validation_cleanup"}, timeout=20)
  requests.post(f"{BASE}/products/{zip_sku}/delete", headers=make_headers(owner), json={"reason": "phase1_validation_cleanup"}, timeout=20)

  print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
  main()
