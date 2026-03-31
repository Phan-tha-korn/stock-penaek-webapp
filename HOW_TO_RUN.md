# คู่มือการรันเซิร์ฟเวอร์ (How to Run)

โปรเจกต์นี้มีสคริปต์แบบ All-in-One เพื่อให้ง่ายต่อการใช้งานบน Windows (ผ่าน Command Prompt หรือ PowerShell) 

## สิ่งที่ต้องมีในเครื่องก่อนเริ่ม (Prerequisites)
1. **Node.js** (เวอร์ชัน 18 ขึ้นไป)
2. **Python** (เวอร์ชัน 3.10 ขึ้นไป)

---

## 🚀 วิธีรันแบบง่ายที่สุด (แนะนำ)

เปิด Command Prompt (cmd) หรือ PowerShell ในโฟลเดอร์โปรเจกต์ แล้วพิมพ์คำสั่งด้านล่าง:

### 1. รันเซิร์ฟเวอร์อย่างเดียว
ถ้าคุณเคยติดตั้งไปแล้ว และต้องการเปิดเซิร์ฟเวอร์เพื่อใช้งาน:
```cmd
.\start-server.cmd -ApiHost 0.0.0.0 -ApiPort 8000
```
- ระบบจะเปิดเซิร์ฟเวอร์ที่ `http://localhost:8000`
- สามารถเข้าใช้งานผ่าน Browser ได้ทันที

### 2. รันทดสอบระบบทั้งหมด (Test)
ถ้าระบบติดตั้งแล้ว และต้องการรันทดสอบ Automated Test ว่าทุกฟังก์ชันทำงานปกติหรือไม่:
```cmd
.\all-in-one.cmd -Action test -ApiHost 127.0.0.1 -ApiPort 8000
```
- สคริปต์จะเปิดเซิร์ฟเวอร์ให้ชั่วคราว รันเทส และปิดเซิร์ฟเวอร์ให้อัตโนมัติ
- รายงานผลจะอยู่ในโฟลเดอร์ `reports/test-results`

### 3. ติดตั้ง + รันทดสอบระบบ (Full)
ถ้าเพิ่งโหลดโปรเจกต์มาครั้งแรก และต้องการให้ระบบ **ติดตั้ง + รันเทส** ในคำสั่งเดียว:
```cmd
.\all-in-one.cmd -Action full -ApiHost 127.0.0.1 -ApiPort 8000
```

### 4. ติดตั้งอย่างเดียว (Install)
ถ้าต้องการแค่ติดตั้ง Dependency และสร้างฐานข้อมูลเริ่มต้น (ไม่รันเซิร์ฟเวอร์ ไม่รันเทส):
```cmd
.\all-in-one.cmd -Action install
```

---

## 🛠️ รหัสผ่านสำหรับ Demo Accounts
หลังจากติดตั้งเสร็จ คุณสามารถล็อกอินเข้าสู่ระบบด้วยบัญชีเหล่านี้:
- **OWNER**: `owner` / `Owner@1234`
- **ADMIN**: `admin` / `Admin@1234`
- **STOCK**: `stock` / `Stock@1234`
- **ACCOUNTANT**: `accountant` / `Acc@1234`
- **DEV**: `dev` / `Dev@1234`

---

## 📝 วิธีรันแบบแยกส่วน (Manual ขั้นสูง)
สำหรับนักพัฒนาที่ต้องการรันแยกส่วนด้วยตัวเอง:

**ติดตั้ง (Install):**
```powershell
.\scripts\install.ps1
```

**รันเซิร์ฟเวอร์ (Start Server):**
```powershell
.\scripts\start.ps1 -ApiHost 0.0.0.0 -ApiPort 8000
```

**รัน Frontend โหมด Development:**
(ต้องเปิดหน้าต่างใหม่)
```powershell
npm run dev
```

**รันเทสด้วยตัวเอง (รันไฟล์ Python ตรงๆ):**
(ต้องเปิดเซิร์ฟเวอร์ทิ้งไว้ก่อนในอีกหน้าต่าง)
```powershell
python .\scripts\full_system_test.py --base-url http://127.0.0.1:8000/api
```

---

## Deploy ขึ้น Vercel (แนะนำแบบใช้งานได้เหมือนเดิม)

เพื่อให้ระบบใช้งานได้เหมือนเดิม (รวมรูปภาพ, งาน background, และ realtime) แนะนำให้:
- Deploy **Frontend** ขึ้น Vercel
- Deploy **Backend (FastAPI)** ขึ้นบริการที่รันต่อเนื่องได้ (เช่น Render/Railway/Fly.io/VPS)
- ใช้ฐานข้อมูลภายนอก (เช่น Neon Postgres) ผ่าน `ESP_DATABASE_URL`

### 1) ตั้งค่า Frontend บน Vercel

ใน Vercel Project Settings → Environment Variables:
- `VITE_API_URL` = `https://<โดเมน-backend>/api`
- `VITE_SOCKET_ENABLED` = `true`
- `VITE_SOCKET_URL` = `https://<โดเมน-backend>`

หมายเหตุ: ถ้าไม่ต้องใช้ realtime ให้ตั้ง `VITE_SOCKET_ENABLED=false` ได้

### 2) ตั้งค่า Backend (ตัวอย่าง Env ที่ควรมี)

- `ESP_DATABASE_URL` = `postgresql://...` (ระบบจะแปลงเป็น asyncpg ให้เอง)
- `ESP_JWT_SECRET` = สุ่มค่าใหม่สำหรับ production
- `ESP_LOGIN_SECRET_PHRASE` = สุ่มค่าใหม่สำหรับ production
