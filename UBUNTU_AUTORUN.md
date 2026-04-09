# Ubuntu Autorun

ไฟล์นี้สรุปวิธีรัน backend บน Ubuntu ให้ติดเองหลังบูตเครื่องแบบไม่มีหน้าต่างหรือ terminal โผล่ เพราะระบบจะรันผ่าน `systemd` ทั้งหมด

## 1) รัน backend อย่างเดียว

คำสั่งเดียว:

```bash
bash ./install.sh
```

คำสั่งนี้จะ:
- ติดตั้ง dependency ที่จำเป็น
- build frontend
- init database
- สร้าง service `stock-penaek`
- ตั้งให้เปิดเองหลังบูตและ restart เองถ้าหลุด

หลังติดตั้ง:

```bash
sudo systemctl status stock-penaek
sudo journalctl -u stock-penaek -f
```

ลบ autorun ของ backend:

```bash
bash ./scripts/ubuntu-service-remove.sh
```

## 2) รัน backend + Cloudflare Tunnel ในรอบเดียว

ก่อนใช้คำสั่งนี้ ต้องมี 3 อย่างก่อน:
- ติดตั้ง `cloudflared` แล้ว
- login/create named tunnel เรียบร้อยแล้ว
- มีไฟล์ config เช่น `/home/<USER>/.cloudflared/config.yml`

ถ้า tunnel ที่ใช้ชื่อ `penaek-backend`:

```bash
bash ./install.sh --cloudflare-tunnel penaek-backend
```

ถ้าต้องระบุ config เอง:

```bash
bash ./install.sh --cloudflare-tunnel penaek-backend --cloudflare-config /home/<USER>/.cloudflared/config.yml
```

คำสั่งนี้จะสร้าง 2 service:
- `stock-penaek`
- `stock-penaek-cloudflared`

ทั้งสองตัวจะรันเบื้องหลังแบบเงียบ ๆ หลังเปิดเครื่อง ไม่ต้องเปิด terminal ค้างไว้

ตรวจสถานะ:

```bash
sudo systemctl status stock-penaek
sudo systemctl status stock-penaek-cloudflared
```

ดู log:

```bash
sudo journalctl -u stock-penaek -f
sudo journalctl -u stock-penaek-cloudflared -f
```

ลบ autorun ของ Cloudflare Tunnel:

```bash
bash ./ubuntu-cloudflared-service-remove.sh
```

## 3) ติดตั้ง Cloudflare Tunnel autorun แยกทีหลัง

ถ้าคุณติดตั้ง backend ไปแล้ว และอยากเพิ่ม tunnel ทีหลัง:

```bash
bash ./ubuntu-cloudflared-service-install.sh --tunnel-name penaek-backend
```

หรือระบุ config เอง:

```bash
bash ./ubuntu-cloudflared-service-install.sh --tunnel-name penaek-backend --config /home/<USER>/.cloudflared/config.yml
```

## 4) หมายเหตุสำคัญ

- service ฝั่ง Ubuntu เป็นงาน background ทั้งหมด ไม่มีหน้าต่างเด้งขึ้นมาหลัง login
- ถ้า backend ใช้โดเมนสาธารณะผ่าน Cloudflare ให้เช็กว่า `cloudflared` มองเห็นไฟล์ config/tunnel credential ของ user ที่รัน service ได้จริง
- ถ้าต้องการเปลี่ยน port backend ให้แก้ `ESP_API_PORT` ใน `.env` ก่อนรัน `install.sh`
