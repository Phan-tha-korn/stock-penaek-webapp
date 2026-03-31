# Enterprise Stock Management Platform (Self-Hosted)

สแตก:
- Frontend: React 18 + TypeScript + Vite + Tailwind
- Backend: FastAPI + Socket.IO (python-socketio)
- DB: SQLite (ค่าเริ่มต้น) หรือ PostgreSQL (กำหนดด้วยตัวแปรแวดล้อม)

## Quick Start (Windows / PowerShell)

1) ติดตั้ง Node 18+ และ Python 3.10+

2) ติดตั้งระบบ + seed demo data

```powershell
.\scripts\install.ps1
```

3) รันระบบ (โหมด production: build frontend + serve ผ่าน FastAPI)

```powershell
.\scripts\start.ps1
```

เปิด: http://localhost:8000/

## All-in-One CLI (Windows)

คำสั่งเดียวสำหรับติดตั้ง/เริ่มระบบ/ทดสอบอัตโนมัติ:

```powershell
.\all-in-one.cmd -Action full -ApiHost 127.0.0.1 -ApiPort 8000
```

โหมดที่รองรับ:

```powershell
.\all-in-one.cmd -Action install
.\all-in-one.cmd -Action start -ApiHost 0.0.0.0 -ApiPort 8000
.\all-in-one.cmd -Action test -BaseUrl http://127.0.0.1:8000/api
.\all-in-one.cmd -Action full
```

สคริปต์เริ่มเซิร์ฟเวอร์แบบง่าย:

```powershell
.\start-server.cmd -ApiHost 0.0.0.0 -ApiPort 8000
```

## Quick Start (Bash / Linux / WSL / Git-Bash)

```bash
bash ./install.sh
```

หรือแยกขั้น:

```bash
bash ./scripts/install.sh
bash ./scripts/start.sh
```

## Demo Accounts

- owner / Owner@1234
- admin / Admin@1234
- stock / Stock@1234
- accountant / Acc@1234
- dev / Dev@1234

หมายเหตุ: ฟิลด์ hidden `secret_phrase` ถูกบังคับตรวจสอบกับค่า `login_secret_phrase` ใน `config.json` (จะถูกสร้างอัตโนมัติในสคริปต์ติดตั้ง)

## Configuration

ไฟล์หลัก: `config.json`
- สีธีม, ภาษาเริ่มต้น, ลิมิต session, interval backup
- คีย์ลับ: `jwt_secret`, `login_secret_phrase` (สคริปต์ติดตั้งจะสุ่มให้)

## API

- Health: `GET /api/health`
- Public config: `GET /api/config`
- Auth: `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me`
- Products: `GET /api/products`
- Dashboard: `GET /api/dashboard/kpis`, `GET /api/dashboard/activity`

## Automated Full Test + Report

รันชุดทดสอบอัตโนมัติแบบละเอียด (รวม role matrix, product flow, users/dev flow):

```powershell
python .\scripts\full_system_test.py --base-url http://127.0.0.1:8000/api
```

ให้สคริปต์เปิดเซิร์ฟเวอร์อัตโนมัติเอง:

```powershell
python .\scripts\full_system_test.py --base-url http://127.0.0.1:8000/api --auto-start-server
```

รายงานจะถูกสร้างใน `reports/test-results`:
- JSON สรุปผลทุกเคส
- Markdown รายงานแบบอ่านง่าย
- Failure log พร้อมข้อความ error ชัดเจน
