# Page Design Spec: ระบบสแกนไฟล์ขยะในโปรเจกต์ (Desktop-first)

## Global Styles (Design Tokens)
- Layout: Desktop-first, max content width 1200px, centered; ใช้ CSS Grid สำหรับโครงหน้า + ตาราง, ใช้ Flex สำหรับแถบเครื่องมือ
- Breakpoints: Desktop ≥1200, Laptop ≥1024, Tablet ≥768, Mobile ≥375 (ย่อลงแบบ stacked)
- Spacing scale: 4/8/12/16/24/32
- Colors:
  - Background: #0B1220 (dark) หรือ #FFFFFF (light) (เลือกธีมเดียวทั้งระบบ)
  - Surface/Card: #111B2E
  - Primary: #3B82F6, Hover: #2563EB
  - Danger/Delete: #EF4444, Hover: #DC2626
  - Border: rgba(255,255,255,0.08)
  - Text: #E5E7EB / Muted: #9CA3AF
- Typography: 12/14/16/20/24 (base 14), ใช้ tabular-nums สำหรับคอลัมน์ “ขนาด/วันที่”
- Buttons:
  - Primary (Start Scan), Secondary (Settings), Danger (Delete)
  - Disabled state ชัดเจนเมื่อยังไม่เลือกไฟล์
- Tables:
  - Sticky header, row hover, selectable checkboxes, zebra subtle
- Feedback:
  - Toast สำหรับสำเร็จ/ผิดพลาด, Inline error สำหรับ path ไม่ถูกต้อง

## Shared Components
- Top App Bar: ชื่อระบบ + เมนู (Scan / Rules / Backup) + สถานะโหมด (Recycle Bin/Backup)
- Breadcrumb/Path Bar: แสดง rootPath ที่กำลังสแกน พร้อมปุ่ม “เปลี่ยนโฟลเดอร์”
- Summary Chips: จำนวนไฟล์, ขนาดรวม, หมวดหมู่ที่เปิดใช้
- Confirm Dialog (Delete): แสดง “จำนวนที่เลือก + ขนาดรวม + โหมด” และตารางสรุปตามหมวดหมู่

---

## Page 1: หน้าสแกนและรายการไฟล์ขยะ (/scan)
### Meta Information
- Title: สแกนไฟล์ขยะ | Trash Scanner
- Description: สแกนไฟล์ขยะในโปรเจกต์ แสดงขนาด/วันที่/ประเภท และลบอย่างปลอดภัย
- Open Graph: og:title, og:description, og:type=website

### Page Structure
- Two-column desktop layout (Grid 12 cols)
  - Left (4 cols): แผงตัวกรอง/สรุปหมวดหมู่
  - Right (8 cols): ตารางรายการไฟล์ + แถบ actions
- Tablet/Mobile: ซ้อนเป็น stacked (Summary ก่อน Table)

### Sections & Components
1) Header / Toolbar (sticky)
- Path selector: input read-only + “Browse”
- Mode selector: segmented control “Recycle Bin” / “Backup”
- Primary CTA: “Start Scan” และ secondary “Cancel” (แสดงเฉพาะระหว่างสแกน)
- Status indicator: กำลังสแกน/เสร็จสิ้น/ผิดพลาด

2) Left Panel: Category Summary
- Category list (cards/rows): ชื่อหมวด + count + total size
- Checkbox “เลือกทั้งหมวด” ต่อหมวดหมู่ (ส่งผลต่อ selection ในตาราง)
- Filter controls:
  - Search box (ค้นหา path/นามสกุล)
  - Toggle “ซ่อนรายการที่ถูก whitelist”

3) Right Panel: File Table
- Columns (เรียงตามความสำคัญ):
  - Checkbox, File name (relativePath), Category, Type(ext), Size, Modified date, Full path (truncate + tooltip)
- Sorting: Size, Modified date, Category
- Row badges:
  - Whitelisted badge (แสดงและปิดการเลือก/ปิดปุ่มลบสำหรับ row นั้น)

4) Selection Footer Bar (sticky bottom)
- แสดง: “เลือกแล้ว X ไฟล์ | ขนาดรวม Y”
- Actions:
  - Danger button “Delete selected”
  - Secondary “Clear selection”

5) Confirm Dialog: Delete
- Summary block: จำนวนไฟล์ที่เลือก + ขนาดรวม + โหมด (Recycle Bin/Backup)
- Category breakdown mini-table
- Warnings: “ลบ/ย้ายเฉพาะรายการที่ไม่ whitelist เท่านั้น”
- Buttons: Cancel / Confirm Delete

Interaction States
- Start Scan disabled จนกว่าจะเลือก rootPath
- Delete disabled หาก selection เป็น 0
- Loading skeleton สำหรับตารางระหว่างสแกน

---

## Page 2: หน้าตั้งค่ากฎสแกนและ Whitelist (/rules)
### Meta Information
- Title: กฎสแกนและ Whitelist | Trash Scanner
- Description: ตั้งค่าหมวดหมู่ไฟล์ขยะและรายการยกเว้น (whitelist)

### Page Structure
- Two-panel split
  - Left: รายการหมวดหมู่
  - Right: รายละเอียดหมวดหมู่ + Whitelist

### Sections & Components
1) Category Manager
- List with toggle enabled/disabled
- Buttons: Add / Edit / Save
- Category form fields:
  - Name, ID (readonly/auto), includeGlobs, excludeGlobs

2) Whitelist Manager
- Table: pattern, note, actions (delete)
- Add rule form: pattern + note + add button
- Helper text: ตัวอย่าง pattern และขอบเขตการทำงาน

Validation
- ป้องกัน pattern ว่าง
- เตือนเมื่อ includeGlobs ไม่ถูกต้อง

---

## Page 3: หน้าตั้งค่า/ปลายทาง Backup (/backup)
### Meta Information
- Title: Backup Settings | Trash Scanner
- Description: กำหนดโฟลเดอร์สำรอง และดูสรุปการทำงานล่าสุด

### Page Structure
- Single column dashboard (cards stacked)

### Sections & Components
1) Backup Destination Card
- Field: backup folder path + browse
- Naming rule preview: แสดงตัวอย่างโฟลเดอร์สำรองต่อการลบหนึ่งครั้ง (preview text)

2) Last Operation Summary Card
- Metrics: movedCount, movedTotalSizeBytes, mode used, timestamp
- Read-only, เน้นตัวเลขแบบ tabular

3) Safety Notes Card
- อธิบายสั้น ๆ ว่าโหมด Recycle Bin/Backup ทำงานต่างกันอย่างไร และผลกระทบต่อไฟล์
