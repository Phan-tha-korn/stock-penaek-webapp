import json
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

BASE = "http://localhost:8000/api"


class Resp:
    def __init__(self, status: int, text: str):
        self.status = status
        self.text = text

    def json(self):
        try:
            return json.loads(self.text)
        except Exception:
            return {}


def call(method: str, path: str, token: str | None = None, body: dict | None = None) -> Resp:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{BASE}{path}", headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return Resp(r.getcode(), r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return Resp(e.code, e.read().decode("utf-8"))


def main():
    cfg = call("GET", "/config").json()
    phrase = cfg.get("login_secret_phrase", "") or ""
    owner_login = call("POST", "/auth/login", body={"username": "owner", "password": "Owner@1234", "secret_phrase": phrase})
    stock_login = call("POST", "/auth/login", body={"username": "stock", "password": "Stock@1234", "secret_phrase": phrase})
    owner = owner_login.json().get("access_token", "")
    stock = stock_login.json().get("access_token", "")
    if not owner or not stock:
        print(json.dumps({"ok": False, "error": "login failed"}, ensure_ascii=False))
        return

    before = call("GET", "/dashboard/kpis", token=owner).json().get("total_products", 0)

    sku = f"AUTO-{uuid4().hex[:8].upper()}"
    create_res = call(
        "POST",
        "/products",
        token=owner,
        body={
            "sku": sku,
            "name_th": "ทดสอบ น้ำปลา อย่างดี",
            "category": "วัตถุดิบ",
            "unit": "ขวด",
            "stock_qty": 7,
            "min_stock": 2,
            "max_stock": 20,
            "cost_price": 19.5,
            "selling_price": 25.0,
        },
    )
    if create_res.status != 200:
        print(json.dumps({"ok": False, "error": "create failed", "detail": create_res.text[:300]}, ensure_ascii=False))
        return

    # wait tiny bit for db commit visibility and async hooks
    time.sleep(0.5)
    after = call("GET", "/dashboard/kpis", token=owner).json().get("total_products", 0)

    partial = call("GET", f"/products?q={sku[-4:]}", token=stock)
    tokenized_q = urllib.parse.quote("ทดสอบ อย่างดี")
    tokenized = call("GET", f"/products?q={tokenized_q}", token=stock)

    cleanup = call("POST", f"/products/{sku}/delete", token=owner, body={"reason": "automation_cleanup"})

    out = {
        "ok": True,
        "kpi_total_before": before,
        "kpi_total_after": after,
        "kpi_incremented": after == before + 1,
        "partial_search_status": partial.status,
        "partial_search_found": any(x.get("sku") == sku for x in partial.json().get("items", [])),
        "tokenized_search_status": tokenized.status,
        "tokenized_search_found": any(x.get("sku") == sku for x in tokenized.json().get("items", [])),
        "cleanup_status": cleanup.status,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
