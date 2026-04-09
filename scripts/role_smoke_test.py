import json
from dataclasses import dataclass
from typing import Any

import urllib.request
import urllib.error

BASE = "http://localhost:8000/api"


@dataclass
class CaseResult:
    role: str
    feature: str
    expected: str
    actual: str
    status: str
    detail: str = ""


class SimpleResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        try:
            return json.loads(self.text)
        except Exception:
            return {}


def call(method: str, path: str, token: str | None = None, **kwargs: Any) -> SimpleResponse:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = kwargs.get("json")
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8")
            return SimpleResponse(resp.getcode(), text)
    except urllib.error.HTTPError as e:
        return SimpleResponse(e.code, e.read().decode("utf-8"))


def expect_status(results: list[CaseResult], role: str, feature: str, response: SimpleResponse, ok_statuses: set[int]) -> None:
    passed = response.status_code in ok_statuses
    results.append(
        CaseResult(
            role=role,
            feature=feature,
            expected=f"HTTP in {sorted(ok_statuses)}",
            actual=f"HTTP {response.status_code}",
            status="PASS" if passed else "FAIL",
            detail=(response.text[:300] if not passed else ""),
        )
    )


def main() -> None:
    cfg = call("GET", "/config")
    if cfg.status_code != 200:
        raise RuntimeError(f"/config failed: {cfg.status_code} {cfg.text}")
    login_phrase = (cfg.json() or {}).get("login_secret_phrase", "") or ""

    users = {
        "OWNER": ("owner", "Owner@1234"),
        "ADMIN": ("admin", "Admin@1234"),
        "STOCK": ("stock", "Stock@1234"),
        "ACCOUNTANT": ("accountant", "Acc@1234"),
        "DEV": ("dev", "Dev@1234"),
    }

    tokens: dict[str, str] = {}
    results: list[CaseResult] = []

    for role, (username, password) in users.items():
        r = call(
            "POST",
            "/auth/login",
            json={"username": username, "password": password, "secret_phrase": login_phrase},
        )
        if r.status_code == 200 and r.json().get("access_token"):
            tokens[role] = r.json()["access_token"]
            results.append(CaseResult(role, "Login", "HTTP 200", "HTTP 200", "PASS"))
        else:
            results.append(CaseResult(role, "Login", "HTTP 200", f"HTTP {r.status_code}", "FAIL", r.text[:300]))

    if len(tokens) < 5:
        print(json.dumps({"ok": False, "error": "login_failed", "results": [x.__dict__ for x in results]}, ensure_ascii=False, indent=2))
        return

    # Core endpoints everyone should access
    for role in users:
        t = tokens[role]
        expect_status(results, role, "GET /dashboard/kpis", call("GET", "/dashboard/kpis", token=t), {200})
        expect_status(results, role, "GET /dashboard/activity", call("GET", "/dashboard/activity", token=t), {200})
        expect_status(results, role, "GET /dashboard/transactions", call("GET", "/dashboard/transactions?limit=10", token=t), {200})
        expect_status(results, role, "GET /config", call("GET", "/config", token=t), {200})

    # Products permissions
    product_allowed = {"OWNER", "ADMIN", "STOCK", "DEV"}
    for role in users:
        t = tokens[role]
        expected = {200} if role in product_allowed else {403}
        expect_status(results, role, "GET /products", call("GET", "/products?limit=5", token=t), expected)

    # Users permissions
    user_allowed = {"OWNER", "DEV"}
    for role in users:
        t = tokens[role]
        expected = {200} if role in user_allowed else {403}
        expect_status(results, role, "GET /users", call("GET", "/users?limit=5", token=t), expected)

    # Sheets sync/import permissions
    for role in users:
        t = tokens[role]
        expected = {200} if role in user_allowed else {403}
        expect_status(results, role, "POST /products/sync-to-sheets", call("POST", "/products/sync-to-sheets", token=t, json={}), expected)
        expect_status(
            results,
            role,
            "POST /products/import-from-sheets",
            call(
                "POST",
                "/products/import-from-sheets",
                token=t,
                json={"overwrite_stock_qty": False, "overwrite_prices": False},
            ),
            expected,
        )

    # Config update permissions
    for role in users:
        t = tokens[role]
        cfg_r = call("GET", "/config", token=t)
        if cfg_r.status_code != 200:
            results.append(CaseResult(role, "PUT /config", "HTTP 200 or 403", f"HTTP {cfg_r.status_code}", "FAIL", "Cannot read config first"))
            continue
        payload = cfg_r.json()
        expected = {200} if role in user_allowed else {403}
        expect_status(results, role, "PUT /config", call("PUT", "/config", token=t, json=payload), expected)

    print(json.dumps({"ok": True, "results": [x.__dict__ for x in results]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
