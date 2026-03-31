# คู่มือ Deploy (GitHub → Vercel) + รัน Backend บนเครื่อง (Windows 11)

## 0) เตรียมให้ปลอดภัยก่อน
- ห้ามเอา `.env` ขึ้น GitHub (โปรเจกต์ใส่ `.gitignore` ให้แล้ว)
- เก็บ secret ไว้ใน Vercel/เครื่องตัวเองเท่านั้น

## 1) รัน Backend บนเครื่องตัวเอง (Windows 11)

### 1.1 รันเองแบบกด
เปิด cmd/PowerShell ที่โฟลเดอร์โปรเจกต์ แล้วรัน:

```cmd
.\start-server.cmd -ApiHost 0.0.0.0 -ApiPort 8000
```

### 1.2 ให้รันอัตโนมัติตอนเปิดคอม/ล็อกอิน (Scheduled Task)
รันคำสั่งนี้ครั้งเดียว (แนะนำเปิด PowerShell แบบ Run as administrator):

```cmd
.\backend-autostart-install.cmd -ApiHost 0.0.0.0 -ApiPort 8000
```

ไฟล์ log จะอยู่ที่:
- `storage/logs/backend.log`

ถ้าต้องการเอาออก:

```cmd
.\backend-autostart-remove.cmd
```

## 2) ขึ้น GitHub

### 2.1 ติดตั้ง Git
ติดตั้ง Git for Windows แล้วเปิด PowerShell ในโฟลเดอร์โปรเจกต์

### 2.2 init repo และ push ขึ้น GitHub

```bash
git init
git add .
git commit -m "Initial commit"
```

จากนั้นไป GitHub → New repository แล้วทำตามคำสั่งที่ GitHub แสดง (ตัวอย่าง):

```bash
git remote add origin https://github.com/<your-username>/<repo>.git
git branch -M main
git push -u origin main
```

## 3) Deploy Frontend ขึ้น Vercel

### 3.1 Import repo
Vercel → Add New → Project → Import GitHub repo

### 3.2 ตั้งค่า Build
- Build Command: `npm run build`
- Output Directory: `dist`

### 3.3 ตั้งค่า Environment Variables (Frontend)
Vercel → Project Settings → Environment Variables:
- `VITE_API_URL` = `https://<โดเมน-backend>/api`
- `VITE_SOCKET_ENABLED` = `true`
- `VITE_SOCKET_URL` = `https://<โดเมน-backend>`

หมายเหตุ: ถ้าไม่ต้องการ realtime ให้ตั้ง `VITE_SOCKET_ENABLED=false`

## 4) ตั้งค่า Backend ให้เชื่อม Postgres (Neon)

ในเครื่อง backend ให้ตั้ง env (แนะนำเก็บไว้ใน `.env` ของเครื่อง ไม่เอาขึ้น Git):
- `ESP_DATABASE_URL=postgresql://...`
- `ESP_JWT_SECRET=...`
- `ESP_LOGIN_SECRET_PHRASE=...`

โปรเจกต์จะแปลง `postgresql://` เป็น `postgresql+asyncpg://` ให้อัตโนมัติ

## 5) หมายเหตุเรื่อง “ให้คนอื่นนอกบ้านเข้าได้”
ถ้า backend อยู่เครื่องคุณเอง และ frontend อยู่ Vercel ต้องมี URL สาธารณะของ backend (https) เช่น:
- Cloudflare Tunnel (แนะนำ)
- ngrok

แล้วนำ URL นั้นไปใส่ใน `VITE_API_URL` และ `VITE_SOCKET_URL` ของ Vercel

