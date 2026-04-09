# Ubuntu Autorun

คำสั่งเดียวสำหรับ Ubuntu:

```bash
bash ./install.sh
```

คำสั่งนี้จะทำให้ครบดังนี้:
- ติดตั้ง Python 3.10+ และ Node.js 18+ ถ้ายังไม่มี
- ติดตั้ง dependency ของ frontend/backend
- build frontend
- initialize database และ seed ข้อมูลเริ่มต้น
- สร้าง `systemd` service ชื่อ `stock-penaek`
- เปิด service แบบ auto-start และ auto-restart

คำสั่งดูสถานะหลังติดตั้ง:

```bash
sudo systemctl status stock-penaek
sudo journalctl -u stock-penaek -f
```

ถ้าต้องการลบ autorun service:

```bash
bash ./scripts/ubuntu-service-remove.sh
```
