import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class TestCaseResult:
    section: str
    name: str
    role: str
    expected: str
    actual: str
    status: str
    start_time: str
    end_time: str
    duration_ms: int
    error: str = ""


@dataclass
class SectionResult:
    name: str
    start_time: str
    end_time: str
    duration_ms: int
    total: int
    passed: int
    failed: int
    items: list[TestCaseResult] = field(default_factory=list)


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, str]:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}{path}", headers=headers, data=data, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=25) as res:
                return res.getcode(), res.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")
        except Exception as e:
            return 0, str(e)


class TestRunner:
    def __init__(self, base_url: str, output_dir: Path):
        self.client = ApiClient(base_url)
        self.output_dir = output_dir
        self.tokens: dict[str, str] = {}
        self.login_phrase: str = ""
        self.users = {
            "OWNER": ("owner", "Owner@1234"),
            "ADMIN": ("admin", "Admin@1234"),
            "STOCK": ("stock", "Stock@1234"),
            "ACCOUNTANT": ("accountant", "Acc@1234"),
            "DEV": ("dev", "Dev@1234"),
        }
        self.sections: list[SectionResult] = []
        self.started_at = datetime.now()
        self.current_section_name = ""

    def now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _as_json(self, text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _record_case(self, items: list[TestCaseResult], name: str, role: str, expected: str, status_ok: bool, actual: str, error: str = "") -> None:
        st = datetime.now()
        et = datetime.now()
        items.append(
            TestCaseResult(
                section=self.current_section_name,
                name=name,
                role=role,
                expected=expected,
                actual=actual,
                status="PASS" if status_ok else "FAIL",
                start_time=st.isoformat(timespec="seconds"),
                end_time=et.isoformat(timespec="seconds"),
                duration_ms=0,
                error=error,
            )
        )

    def relogin_role(self, role: str) -> bool:
        creds = self.users.get(role)
        if not creds:
            return False
        username, password = creds
        s, body = self.client.request(
            "POST",
            "/auth/login",
            body={"username": username, "password": password, "secret_phrase": self.login_phrase},
        )
        if s == 200:
            token = self._as_json(body).get("access_token", "")
            if token:
                self.tokens[role] = token
                return True
        return False

    def authed_request(self, role: str, method: str, path: str, body: dict | None = None) -> tuple[int, str]:
        token = self.tokens.get(role, "")
        s, resp_body = self.client.request(method, path, token=token, body=body)
        if s == 401 and "invalid_token" in (resp_body or ""):
            ok = self.relogin_role(role)
            if ok:
                s, resp_body = self.client.request(method, path, token=self.tokens.get(role, ""), body=body)
        return s, resp_body

    def _finalize_section(self, name: str, start_ts: float, start_iso: str, items: list[TestCaseResult]) -> None:
        end_iso = self.now_iso()
        total = len(items)
        passed = len([x for x in items if x.status == "PASS"])
        failed = total - passed
        self.sections.append(
            SectionResult(
                name=name,
                start_time=start_iso,
                end_time=end_iso,
                duration_ms=int((time.time() - start_ts) * 1000),
                total=total,
                passed=passed,
                failed=failed,
                items=items,
            )
        )

    def run_section_public_and_login(self) -> None:
        name = "public_and_login"
        self.current_section_name = name
        start_ts = time.time()
        start_iso = self.now_iso()
        items: list[TestCaseResult] = []

        s, body = self.client.request("GET", "/config")
        ok = s == 200
        self._record_case(items, "GET /config", "PUBLIC", "HTTP 200", ok, f"HTTP {s}", body[:300] if not ok else "")
        if not ok:
            self._finalize_section(name, start_ts, start_iso, items)
            return
        self.login_phrase = self._as_json(body).get("login_secret_phrase", "") or ""

        s, body = self.client.request("GET", "/health")
        self._record_case(items, "GET /health", "PUBLIC", "HTTP 200", s == 200, f"HTTP {s}", body[:300] if s != 200 else "")

        for role, (username, password) in self.users.items():
            st = time.time()
            st_iso = self.now_iso()
            s, body = self.client.request(
                "POST",
                "/auth/login",
                body={"username": username, "password": password, "secret_phrase": self.login_phrase},
            )
            token = self._as_json(body).get("access_token", "")
            if s == 200 and token:
                self.tokens[role] = token
                ok = True
                err = ""
            else:
                ok = False
                err = body[:400]
            items.append(
                TestCaseResult(
                    section=name,
                    name=f"POST /auth/login ({username})",
                    role=role,
                    expected="HTTP 200 + access_token",
                    actual=f"HTTP {s}",
                    status="PASS" if ok else "FAIL",
                    start_time=st_iso,
                    end_time=self.now_iso(),
                    duration_ms=int((time.time() - st) * 1000),
                    error=err,
                )
            )

        self._finalize_section(name, start_ts, start_iso, items)

    def run_section_role_matrix(self) -> None:
        name = "role_matrix"
        self.current_section_name = name
        start_ts = time.time()
        start_iso = self.now_iso()
        items: list[TestCaseResult] = []

        cases = [
            ("GET", "/auth/me", {"OWNER", "ADMIN", "STOCK", "ACCOUNTANT", "DEV"}),
            ("GET", "/dashboard/kpis", {"OWNER", "ADMIN", "STOCK", "ACCOUNTANT", "DEV"}),
            ("GET", "/dashboard/activity", {"OWNER", "ADMIN", "STOCK", "ACCOUNTANT", "DEV"}),
            ("GET", "/dashboard/transactions?limit=5", {"OWNER", "ADMIN", "STOCK", "ACCOUNTANT", "DEV"}),
            ("GET", "/products?limit=5", {"OWNER", "ADMIN", "STOCK", "DEV"}),
            ("GET", "/users?limit=5", {"OWNER", "DEV"}),
        ]

        for role, token in self.tokens.items():
            for method, path, allowed in cases:
                st = time.time()
                st_iso = self.now_iso()
                s, body = self.authed_request(role, method, path)
                if role in allowed:
                    ok = s not in (401, 403)
                    expected = "ไม่ใช่ HTTP 401/403"
                else:
                    ok = s == 403
                    expected = "HTTP 403"
                items.append(
                    TestCaseResult(
                        section=name,
                        name=f"{method} {path}",
                        role=role,
                        expected=expected,
                        actual=f"HTTP {s}",
                        status="PASS" if ok else "FAIL",
                        start_time=st_iso,
                        end_time=self.now_iso(),
                        duration_ms=int((time.time() - st) * 1000),
                        error=(body[:400] if not ok else ""),
                    )
                )

        self._finalize_section(name, start_ts, start_iso, items)

    def run_section_product_flow(self) -> None:
        name = "product_flow"
        self.current_section_name = name
        start_ts = time.time()
        start_iso = self.now_iso()
        items: list[TestCaseResult] = []

        dev = self.tokens.get("DEV", "")
        stock = self.tokens.get("STOCK", "")
        if not dev or not stock:
            self._record_case(items, "prepare tokens", "SYSTEM", "มี token ของ DEV และ STOCK", False, "missing token", "ไม่สามารถทดสอบ product flow ได้")
            self._finalize_section(name, start_ts, start_iso, items)
            return

        sku = f"AUTO-{uuid4().hex[:8].upper()}"
        payload = {
            "sku": sku,
            "name_th": "ทดสอบระบบอัตโนมัติ",
            "name_en": "automation",
            "category": "TEST",
            "type": "RAW",
            "unit": "ชิ้น",
            "cost_price": 10.0,
            "selling_price": 15.0,
            "stock_qty": 10.0,
            "min_stock": 2.0,
            "max_stock": 50.0,
            "is_test": True,
            "supplier": "AUTO",
            "barcode": sku,
            "notes": "automation",
        }

        st = time.time()
        st_iso = self.now_iso()
        s, body = self.authed_request("DEV", "POST", "/products", body=payload)
        items.append(
            TestCaseResult(
                section=name,
                name="POST /products",
                role="DEV",
                expected="HTTP 200",
                actual=f"HTTP {s}",
                status="PASS" if s == 200 else "FAIL",
                start_time=st_iso,
                end_time=self.now_iso(),
                duration_ms=int((time.time() - st) * 1000),
                error=(body[:400] if s != 200 else ""),
            )
        )

        st = time.time()
        st_iso = self.now_iso()
        s, body = self.authed_request("STOCK", "GET", f"/products?q={sku[-5:]}")
        data = self._as_json(body)
        found = any((x.get("sku") == sku) for x in data.get("items", []))
        ok = s == 200 and found
        items.append(
            TestCaseResult(
                section=name,
                name="GET /products search",
                role="STOCK",
                expected="HTTP 200 และพบ SKU ที่สร้าง",
                actual=f"HTTP {s}, found={found}",
                status="PASS" if ok else "FAIL",
                start_time=st_iso,
                end_time=self.now_iso(),
                duration_ms=int((time.time() - st) * 1000),
                error=(body[:400] if not ok else ""),
            )
        )

        st = time.time()
        st_iso = self.now_iso()
        s, body = self.authed_request("ADMIN", "POST", f"/products/{sku}/adjust", body={"qty": 2, "type": "STOCK_IN", "reason": "test_in"})
        items.append(
            TestCaseResult(
                section=name,
                name="POST /products/{sku}/adjust",
                role="ADMIN",
                expected="HTTP 200",
                actual=f"HTTP {s}",
                status="PASS" if s == 200 else "FAIL",
                start_time=st_iso,
                end_time=self.now_iso(),
                duration_ms=int((time.time() - st) * 1000),
                error=(body[:400] if s != 200 else ""),
            )
        )

        st = time.time()
        st_iso = self.now_iso()
        s, body = self.authed_request("DEV", "POST", f"/products/{sku}/delete", body={"reason": "automation_cleanup"})
        items.append(
            TestCaseResult(
                section=name,
                name="POST /products/{sku}/delete",
                role="DEV",
                expected="HTTP 200",
                actual=f"HTTP {s}",
                status="PASS" if s == 200 else "FAIL",
                start_time=st_iso,
                end_time=self.now_iso(),
                duration_ms=int((time.time() - st) * 1000),
                error=(body[:400] if s != 200 else ""),
            )
        )

        self._finalize_section(name, start_ts, start_iso, items)

    def run_section_user_and_dev_tools_flow(self) -> None:
        name = "user_and_dev_flow"
        self.current_section_name = name
        start_ts = time.time()
        start_iso = self.now_iso()
        items: list[TestCaseResult] = []

        dev = self.tokens.get("DEV", "")
        if not dev:
            self._record_case(items, "prepare token", "SYSTEM", "มี token ของ DEV", False, "missing token", "ไม่สามารถทดสอบ user/dev flow ได้")
            self._finalize_section(name, start_ts, start_iso, items)
            return

        username = f"u_{uuid4().hex[:8]}"
        password = "Abcdef@123"
        user_id = ""

        st = time.time()
        st_iso = self.now_iso()
        s, body = self.authed_request(
            "DEV",
            "POST",
            "/users",
            body={"username": username, "display_name": "Auto User", "role": "STOCK", "password": password, "language": "th"},
        )
        data = self._as_json(body)
        user_id = data.get("id", "")
        ok = s == 200 and bool(user_id)
        items.append(
            TestCaseResult(
                section=name,
                name="POST /users",
                role="DEV",
                expected="HTTP 200 และได้ user id",
                actual=f"HTTP {s}",
                status="PASS" if ok else "FAIL",
                start_time=st_iso,
                end_time=self.now_iso(),
                duration_ms=int((time.time() - st) * 1000),
                error=(body[:400] if not ok else ""),
            )
        )

        if user_id:
            st = time.time()
            st_iso = self.now_iso()
            s, body = self.authed_request("DEV", "PATCH", f"/users/{user_id}", body={"display_name": "Auto User Updated"})
            items.append(
                TestCaseResult(
                    section=name,
                    name="PATCH /users/{id}",
                    role="DEV",
                    expected="HTTP 200",
                    actual=f"HTTP {s}",
                    status="PASS" if s == 200 else "FAIL",
                    start_time=st_iso,
                    end_time=self.now_iso(),
                    duration_ms=int((time.time() - st) * 1000),
                    error=(body[:400] if s != 200 else ""),
                )
            )

            st = time.time()
            st_iso = self.now_iso()
            s, body = self.authed_request("DEV", "POST", f"/users/{user_id}/reset-password", body={"password": "Newpass@123"})
            items.append(
                TestCaseResult(
                    section=name,
                    name="POST /users/{id}/reset-password",
                    role="DEV",
                    expected="HTTP 200",
                    actual=f"HTTP {s}",
                    status="PASS" if s == 200 else "FAIL",
                    start_time=st_iso,
                    end_time=self.now_iso(),
                    duration_ms=int((time.time() - st) * 1000),
                    error=(body[:400] if s != 200 else ""),
                )
            )

        temp_dir = Path(__file__).resolve().parents[1] / ".auto-garbage"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f"auto_{uuid4().hex[:6]}.tmp"
        temp_file.write_text("automation", encoding="utf-8")

        st = time.time()
        st_iso = self.now_iso()
        s, body = self.authed_request("DEV", "GET", "/dev/garbage/scan?include_whitelisted=true")
        data = self._as_json(body)
        rel_temp = str(temp_file.resolve()).replace("\\", "/")
        found = False
        for item in data.get("items", []):
            p = str(item.get("absolute_path", "")).replace("\\", "/")
            if p == rel_temp:
                found = True
                break
        ok = s == 200 and found
        items.append(
            TestCaseResult(
                section=name,
                name="GET /dev/garbage/scan",
                role="DEV",
                expected="HTTP 200 และพบไฟล์ temp ที่สร้าง",
                actual=f"HTTP {s}, found={found}",
                status="PASS" if ok else "FAIL",
                start_time=st_iso,
                end_time=self.now_iso(),
                duration_ms=int((time.time() - st) * 1000),
                error=(body[:400] if not ok else ""),
            )
        )

        st = time.time()
        st_iso = self.now_iso()
        rel_path = str(temp_file.relative_to(Path(__file__).resolve().parents[1])).replace("\\", "/")
        s, body = self.authed_request("DEV", "POST", "/dev/garbage/delete", body={"paths": [rel_path], "mode": "backup", "confirm": True})
        ok = s == 200 and self._as_json(body).get("deleted_count", 0) >= 1
        items.append(
            TestCaseResult(
                section=name,
                name="POST /dev/garbage/delete",
                role="DEV",
                expected="HTTP 200 และ deleted_count >= 1",
                actual=f"HTTP {s}",
                status="PASS" if ok else "FAIL",
                start_time=st_iso,
                end_time=self.now_iso(),
                duration_ms=int((time.time() - st) * 1000),
                error=(body[:400] if not ok else ""),
            )
        )

        if user_id:
            st = time.time()
            st_iso = self.now_iso()
            s, body = self.authed_request("DEV", "DELETE", f"/users/{user_id}")
            items.append(
                TestCaseResult(
                    section=name,
                    name="DELETE /users/{id}",
                    role="DEV",
                    expected="HTTP 200",
                    actual=f"HTTP {s}",
                    status="PASS" if s == 200 else "FAIL",
                    start_time=st_iso,
                    end_time=self.now_iso(),
                    duration_ms=int((time.time() - st) * 1000),
                    error=(body[:400] if s != 200 else ""),
                )
            )

        if temp_dir.exists():
            try:
                temp_dir.rmdir()
            except Exception:
                pass

        self._finalize_section(name, start_ts, start_iso, items)

    def run(self) -> dict[str, Any]:
        self.run_section_public_and_login()
        if len(self.tokens) == 5:
            self.run_section_role_matrix()
            self.run_section_product_flow()
            self.run_section_user_and_dev_tools_flow()

        ended_at = datetime.now()
        flat_items = [it for sec in self.sections for it in sec.items]
        passed = len([x for x in flat_items if x.status == "PASS"])
        failed = len(flat_items) - passed
        result = {
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "ended_at": ended_at.isoformat(timespec="seconds"),
            "duration_ms": int((ended_at.timestamp() - self.started_at.timestamp()) * 1000),
            "total": len(flat_items),
            "passed": passed,
            "failed": failed,
            "ok": failed == 0,
            "sections": [asdict(sec) for sec in self.sections],
        }
        self.write_reports(result)
        return result

    def write_reports(self, report: dict[str, Any]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = self.output_dir / f"full-test-report-{stamp}.json"
        md_path = self.output_dir / f"full-test-report-{stamp}.md"
        fail_path = self.output_dir / f"full-test-failures-{stamp}.log"

        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        lines: list[str] = []
        lines.append("# Full System Test Report")
        lines.append("")
        lines.append(f"- Started: {report['started_at']}")
        lines.append(f"- Ended: {report['ended_at']}")
        lines.append(f"- Duration(ms): {report['duration_ms']}")
        lines.append(f"- Total: {report['total']}")
        lines.append(f"- Passed: {report['passed']}")
        lines.append(f"- Failed: {report['failed']}")
        lines.append("")
        for sec in report["sections"]:
            lines.append(f"## Section: {sec['name']}")
            lines.append(f"- Start: {sec['start_time']}")
            lines.append(f"- End: {sec['end_time']}")
            lines.append(f"- Duration(ms): {sec['duration_ms']}")
            lines.append(f"- Passed/Total: {sec['passed']}/{sec['total']}")
            lines.append("")
            lines.append("| Test | Role | Expected | Actual | Status | Error |")
            lines.append("|---|---|---|---|---|---|")
            for item in sec["items"]:
                err = str(item.get("error", "")).replace("\n", " ").replace("|", " ")
                lines.append(
                    f"| {item['name']} | {item['role']} | {item['expected']} | {item['actual']} | {item['status']} | {err} |"
                )
            lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8")

        fail_lines: list[str] = []
        for sec in report["sections"]:
            for item in sec["items"]:
                if item["status"] == "FAIL":
                    fail_lines.append(
                        f"[{sec['name']}] {item['name']} ({item['role']}) expected={item['expected']} actual={item['actual']} error={item.get('error','')}"
                    )
        fail_path.write_text("\n".join(fail_lines), encoding="utf-8")

        print(json.dumps({"ok": report["ok"], "json_report": str(json_path), "markdown_report": str(md_path), "failure_log": str(fail_path)}, ensure_ascii=False))


def wait_for_health(base_url: str, timeout_sec: int = 90) -> bool:
    client = ApiClient(base_url)
    started = time.time()
    while time.time() - started < timeout_sec:
        s, _ = client.request("GET", "/health")
        if s == 200:
            return True
        time.sleep(1)
    return False


def find_python_executable(project_root: Path) -> str:
    candidates = [
        project_root / ".venv" / "Scripts" / "python.exe",
        project_root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def start_server_process(project_root: Path, host: str, port: int) -> subprocess.Popen[Any]:
    python_cmd = find_python_executable(project_root)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    cmd = [python_cmd, "-m", "uvicorn", "server.main:app", "--host", host, "--port", str(port)]
    return subprocess.Popen(cmd, cwd=str(project_root), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--output-dir", default="reports/test-results")
    parser.add_argument("--auto-start-server", action="store_true")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / args.output_dir
    proc = None

    try:
        if args.auto_start_server:
            parsed = urllib.parse.urlparse(args.base_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 8000
            proc = start_server_process(project_root, host, port)
            if not wait_for_health(args.base_url, timeout_sec=120):
                print(json.dumps({"ok": False, "error": "server_start_timeout"}, ensure_ascii=False))
                if proc:
                    proc.terminate()
                sys.exit(1)

        runner = TestRunner(args.base_url, output_dir)
        report = runner.run()
        if not report.get("ok", False):
            sys.exit(1)
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
