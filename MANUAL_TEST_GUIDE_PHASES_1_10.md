# Manual Test Guide For Added Systems

เอกสารนี้เป็นคู่มือเทสมือแบบไฟล์เดียวสำหรับระบบที่เพิ่มมาทั้งหมดในรอบพัฒนา PHASE 1-10 ของ Stock Penaek Webapp

เป้าหมาย:
- ใช้เป็น checklist ก่อน go-live
- บอกว่าแต่ละส่วนเกี่ยวกับอะไร
- บอกว่าแต่ละส่วนควรใช้ user role ไหนเทส
- บอกลำดับการเทสที่ถูกต้องตาม dependency ของระบบ

หลักการสำคัญ:
- เทสตามลำดับที่กำหนด เพราะหลายระบบพึ่งข้อมูลจากระบบก่อนหน้า
- ถ้าเทสข้ามลำดับ อาจทำให้สรุปผลผิด เช่น compare ยังไม่ขึ้นเพราะ price/matching ยังไม่พร้อม
- ทุก flow ที่เป็น critical action ควรเช็ก 4 อย่างเสมอ:
  - action สำเร็จ
  - สิทธิ์ถูกต้อง
  - audit/notification/snapshot ถูกสร้างตามที่ควร
  - ข้อมูลปลายทางอื่นไม่พัง

## 1. User Roles ที่ต้องเตรียม

ควรมีอย่างน้อย 5 บัญชี:

1. `OWNER`
- ใช้เทส global visibility
- ใช้เทส owner-only summary
- ใช้เทส verify/matching/pricing critical paths แบบสิทธิ์สูงสุด

2. `DEV`
- ใช้เทส verification workflow
- ใช้เทส matching structural operations
- ใช้เทส dev zone และ notification/queue paths

3. `ADMIN`
- ใช้เทส supplier operations
- ใช้เทส monitoring/read access
- ใช้ยืนยันว่า admin ดูได้แต่ verify ไม่ได้

4. `STOCK`
- ใช้เทส read-only search/compare/history
- ใช้ยืนยันว่าทำ protected actions ไม่ได้

5. `DEV_OTHER_BRANCH` หรือ `STOCK_OTHER_BRANCH`
- ใช้เทส branch scope
- ใช้ยืนยันว่า non-owner ไม่เห็นข้อมูลข้าม branch

## 2. ลำดับการเทสที่แนะนำ

เทสตามลำดับนี้:

1. Authentication + role basics
2. Foundation / branch / soft delete
3. Supplier + attachment
4. Pricing + cost + formula
5. Matching / canonical group
6. Verification workflow
7. Search / comparison / history
8. Notifications
9. UI zones / deep-links / dashboards
10. Snapshot / historical report safety
11. Final end-to-end regression

เหตุผล:
- Supplier เป็นฐานให้ pricing
- Pricing และ matching เป็นฐานให้ compare
- Verification, notification, snapshot จะ meaningful เมื่อมี pricing/supplier/matching data จริงแล้ว

## 3. Test Data ที่ควรมี

ควรเตรียมอย่างน้อย:

- 2 branches
  - `MAIN`
  - `OTHER`
- 3 products
  - สินค้า A และ B อยู่ branch เดียวกันและสามารถอยู่ใน canonical group เดียวกันได้
  - สินค้า C อยู่คนละ branch
- 2 suppliers
  - Supplier Alpha
  - Supplier Beta
- price tiers อย่างน้อย:
  - `1-9`
  - `10-49`
  - `50+`
- verification request อย่างน้อย 2 แบบ
  - warning
  - blocked/high risk
- notification events อย่างน้อย
  - verification
  - pricing
  - supplier

## 4. Phase 1: Foundation / Branch / Audit / Soft Delete

เกี่ยวกับอะไร:
- โครงฐานข้อมูลใหม่
- branch visibility
- audit v2
- soft delete / archive base
- migration safety

Role ที่ใช้เทส:
- `OWNER`
- `DEV`

สิ่งที่ต้องเทส:

1. Login ได้ครบตาม role
2. Product เดิมยัง list/create/edit ได้
3. ลบ product แล้วต้องเป็น soft delete ไม่ใช่หายถาวร
4. Restore product ได้
5. audit ถูกเขียนเมื่อเกิด critical action
6. branch default/backfill ทำงาน

ผลที่ต้องได้:
- legacy flow เดิมไม่พัง
- delete/restore ทำงานจริง
- audit มี before/after/reason ตาม action สำคัญ

## 5. Phase 2: Supplier + Attachment

เกี่ยวกับอะไร:
- supplier entity จริง
- attachment system
- supplier proposal flow
- admin edit ต้องผ่าน verify path

Role ที่ใช้เทส:
- `OWNER`
- `ADMIN`
- `DEV`
- `STOCK`

ลำดับ:
1. `OWNER`
2. `ADMIN`
3. `DEV`
4. `STOCK`

สิ่งที่ต้องเทส:

1. OWNER สร้าง supplier ได้
2. OWNER แก้/archive supplier ได้
3. ADMIN แก้ supplier แล้วต้องกลายเป็น pending proposal
4. DEV approve/reject proposal ได้
5. upload attachment ได้
6. invalid file type / oversized / too many files ถูก block
7. STOCK อ่านได้เฉพาะที่ควรอ่าน

ผลที่ต้องได้:
- supplier ไม่เป็นแค่ string แล้ว
- critical supplier edit ไม่ bypass dev confirmation
- attachment rules ทำงานจริง

## 6. Phase 3: Pricing / Cost / Formula

เกี่ยวกับอะไร:
- price records
- quantity tiers
- THB/USD normalization
- VAT + cost breakdown
- formula versioning
- price lifecycle
- conflict blocking

Role ที่ใช้เทส:
- `OWNER`
- `DEV`
- `ADMIN` เฉพาะ read/monitor

ลำดับ:
1. `OWNER` สร้าง/แก้ price
2. `DEV` ตรวจ verify-related behavior
3. `ADMIN` ดูว่าถึงจุด protected แล้วทำตรง ๆ ไม่ได้

สิ่งที่ต้องเทส:

1. สร้าง tier `1-9`, `10-49`, `50+`
2. overlap แบบไม่ถูกต้องต้อง fail
3. THB ทำ rate = 1
4. USD ต้อง normalize เป็น THB
5. VAT และ cost breakdown ถูกต้อง
6. final compare field ใช้ `final_total_cost`
7. replace flow:
  - row เดิม -> `replaced`
  - row ใหม่ -> `active`
8. archive flow:
  - row -> `archived`
9. formula version activate ได้
10. formula version ที่ activate แล้วแก้ไม่ได้

ผลที่ต้องได้:
- pricing lifecycle ถูก
- conflict ถูก block จริง
- compare data พร้อมใช้งาน

## 7. Phase 4: Matching / Canonical Product Group

เกี่ยวกับอะไร:
- canonical product groups
- temporal membership
- move / merge / split
- lock states
- history + dependency checks

Role ที่ใช้เทส:
- `DEV`
- `OWNER`
- `ADMIN` อ่านได้บางส่วน
- `STOCK` อ่านได้เท่าที่ระบบเปิด

ลำดับ:
1. `DEV`
2. `OWNER`
3. `ADMIN`

สิ่งที่ต้องเทส:

1. สร้าง group
2. add product เข้า group
3. remove product ต้องปิด membership ไม่ใช่ลบ row
4. move product ระหว่าง group
5. merge groups
6. split group
7. `review_locked` block structural action
8. `owner_locked` เปลี่ยนได้โดย owner เท่านั้น
9. product active membership มีได้แค่กลุ่มเดียว
10. active primary ต่อ group มีได้แค่ 1
11. version_no:
  - add/remove/move/merge/split bump
  - lock change ไม่ bump
  - split-created target group = version 1

ผลที่ต้องได้:
- matching ย้อนประวัติได้
- reversible metadata ครบ
- compare/search ไม่พังหลัง matching เปลี่ยน

## 8. Phase 5: Verification Workflow

เกี่ยวกับอะไร:
- generic verification engine
- risk level
- queue / assignee
- overdue / escalation
- strict transitions
- transactional approval

Role ที่ใช้เทส:
- `OWNER`
- `DEV`
- `ADMIN`
- `STOCK`

ลำดับ:
1. `ADMIN` หรือ `OWNER` สร้าง request
2. `DEV` verify
3. `OWNER` verify
4. `ADMIN` ลอง verify ต้อง fail
5. `STOCK` ลอง submit protected flow ต้อง fail

สิ่งที่ต้องเทส:

1. create valid request
2. create invalid request ไม่มี items ต้อง fail
3. pending -> approve
4. pending -> reject
5. pending -> return_for_revision
6. pending -> cancel
7. invalid transition หลัง terminal ต้อง fail
8. overdue > 2h
9. escalation level เพิ่ม
10. blocked request approve ไม่ได้
11. warning request approve ได้
12. handler fail แล้ว rollback ทั้ง request
13. audit/action trail ครบ

ผลที่ต้องได้:
- protected changes ไม่ bypass verification
- queue ใช้งานจริง
- all-or-nothing approval ทำงาน

## 9. Phase 6: Search / Compare / History

เกี่ยวกับอะไร:
- quick search
- deep comparison
- historical queries
- verification/admin search
- projection/read-model search

Role ที่ใช้เทส:
- `STOCK`
- `DEV`
- `OWNER`
- `ADMIN`

ลำดับ:
1. `STOCK` เทส quick search/read compare
2. `DEV` เทส verification/admin queue search
3. `OWNER` เทส global compare/history
4. user คนละ branch เทส scope leak

สิ่งที่ต้องเทส:

1. quick search:
  - SKU exact
  - alias
  - name fuzzy
2. deep compare:
  - canonical group context ถูก
  - ranking by `final_total_cost`
  - latest vs active behavior
  - tie-break คงที่
3. filters:
  - product
  - supplier
  - branch
  - delivery_mode
  - area_scope
  - lifecycle
  - cost range
4. historical:
  - as_of
  - range
  - effective/expire overlap
5. admin search:
  - workflow_status
  - risk_level
  - assignee
  - overdue
6. projection freshness:
  - เปลี่ยนราคาแล้ว compare/search สะท้อน

ผลที่ต้องได้:
- search ใช้ data ที่ filter ได้จริง
- compare เห็นตัวที่ดีที่สุดตาม context
- branch scope ไม่รั่ว

## 10. Phase 7: Notification System

เกี่ยวกับอะไร:
- event-driven notifications
- outbox
- retry
- LINE / Email abstraction
- deep-link targets

Role ที่ใช้เทส:
- `DEV`
- `OWNER`
- `ADMIN`

ลำดับ:
1. trigger event
2. ดู outbox
3. ตรวจ recipient
4. ตรวจ deep-link
5. ตรวจ retry/failure

สิ่งที่ต้องเทส:

1. verification notifications:
  - submit
  - approve
  - reject
  - overdue
  - escalate
2. supplier verification-required notification
3. pricing critical change notification
4. routing:
  - DEV
  - OWNER
  - assignee
  - branch scope
5. critical ignore opt-out
6. duplicate event ไม่ส่งซ้ำ
7. success recorded
8. failure recorded
9. retry จน max_attempts
10. ไม่มี stuck `processing` rows

ผลที่ต้องได้:
- main transaction ไม่ถูก block เพราะส่งแจ้งเตือน
- deep-link ใช้งานได้จริง

## 11. Phase 8: UI Zones / Dashboard

เกี่ยวกับอะไร:
- role-based zones
- landing pages
- dashboard summaries
- safe deep-links

Role ที่ใช้เทส:
- ทุก role

ลำดับ:
1. `OWNER`
2. `DEV`
3. `ADMIN`
4. `STOCK`
5. branch-scoped user

สิ่งที่ต้องเทส:

1. landing per role:
  - OWNER -> owner zone
  - DEV -> dev zone
  - ADMIN -> admin zone
  - STOCK -> stock search
2. cross-role forbidden access
3. search workspace deep-link
4. verification deep-link
5. notification open related item
6. dashboard summary ถูก role
7. refresh behavior:
  - summary polling/manual
  - queue near-real-time polling
  - heavy data manual refresh

ผลที่ต้องได้:
- role ไม่เห็น zone ที่ไม่ควรเห็น
- deep-link ไม่พาไป context ผิด

## 12. Phase 9: Historical Snapshots

เกี่ยวกับอะไร:
- immutable snapshot
- historical reproducibility
- decision trace
- report safety

Role ที่ใช้เทส:
- `DEV`
- `OWNER`

ลำดับ:
1. approval/change ที่ควรสร้าง snapshot
2. เปิด snapshot query
3. เปลี่ยน live data
4. กลับมาเปิด snapshot เดิม

สิ่งที่ต้องเทส:

1. verification approval creates snapshot
2. pricing replace/archive creates snapshot
3. version tokens ถูกเก็บ
4. missing version token ต้อง block
5. snapshot update/delete ถูก block
6. cancelled snapshot ไม่ถูกใช้ default
7. report/query จาก snapshot ไม่ mix live data

ผลที่ต้องได้:
- historical report เสถียร
- audit trace ย้อนดูได้

## 13. Phase 10: Hardening / Production Safety

เกี่ยวกับอะไร:
- limits
- timeouts
- payload guards
- queue guards
- deploy readiness

Role ที่ใช้เทส:
- `OWNER`
- `DEV`
- `ADMIN`
- `STOCK`

สิ่งที่ต้องเทส:

1. query limit cap
2. historical range cap
3. snapshot payload size cap
4. notification retry/batch cap
5. invalid deep-link rejected
6. queue processing timeout path
7. migration upgrade head ผ่าน
8. config safe defaults มี

ผลที่ต้องได้:
- ไม่มี query ไม่จำกัด
- ไม่มีงาน queue ค้าง
- พร้อม deploy

## 14. Recommended Test Run จริงก่อนใช้งาน

### รอบที่ 1: Core data
- Login ทุก role
- สร้าง supplier
- สร้าง product ที่เกี่ยวข้อง
- สร้าง price tiers
- สร้าง canonical group

### รอบที่ 2: Protected workflow
- Admin แก้ supplier
- Dev เปิด verification queue
- approve / reject / return
- เช็ก notification
- เช็ก snapshot

### รอบที่ 3: Search and compare
- Stock quick search
- Compare by product
- Compare by canonical group
- History query

### รอบที่ 4: Cross-role safety
- Stock ลองเข้า verify route
- Admin ลอง verify action
- branch-scoped user ลองดู branch อื่น

### รอบที่ 5: End-to-end production path
- Search -> Compare -> Decision
- Verification -> Approval -> Snapshot -> Notification
- Notification -> Open related item
- Price change -> Snapshot -> Search reflect

## 15. Acceptance Criteria ก่อน Go-Live

ปล่อยใช้งานจริงได้เมื่อ:

1. ทุก role login และ route access ถูกต้อง
2. supplier/pricing/matching/verification/search/notification/snapshot flow ผ่าน
3. branch scope ไม่รั่ว
4. audit เกิดครบใน critical action
5. no hard delete ใน critical entities
6. queue ไม่มี stuck processing
7. migrations run ได้บน staging copy
8. build ผ่าน
9. backend tests ผ่าน
10. provider config จริงถูกใส่ครบ

## 16. Provider Config ที่ควรเช็กก่อนใช้งานจริง

LINE:
- มี token สำหรับ role/recipient ที่ต้องใช้
- ถ้าใช้ Dev notification config ให้เช็กว่าบันทึก token ถูก role

Email:
- มี SMTP host
- SMTP port
- SMTP username
- SMTP password
- from email
- notification email per role ตามที่ต้องใช้

ถ้ายังไม่ใส่ provider credentials:
- core system ยังทำงานได้
- แต่ notification delivery ออกจริงจะไม่ครบ

## 17. ถ้าจะให้ทีมเทสแบบสั้นที่สุด

ขั้นต่ำสุดแนะนำ:

1. `OWNER`
- เทส owner dashboard
- เทส compare
- เทส pricing replace

2. `DEV`
- เทส verification queue
- เทส approve + notification + snapshot
- เทส matching move/merge

3. `ADMIN`
- เทส supplier edit -> pending verify

4. `STOCK`
- เทส quick search + compare read-only

5. `DEV_OTHER_BRANCH`
- เทส branch scope leak

## 18. ไฟล์/พื้นที่หลักที่ระบบใหม่กระจุกอยู่

Backend:
- `C:\\Stock Penaek Webapp\\server\\services`
- `C:\\Stock Penaek Webapp\\server\\api`
- `C:\\Stock Penaek Webapp\\server\\db\\models.py`
- `C:\\Stock Penaek Webapp\\alembic`

Frontend:
- `C:\\Stock Penaek Webapp\\src\\pages\\app\\zones`
- `C:\\Stock Penaek Webapp\\src\\pages\\app\\SuppliersPage.tsx`
- `C:\\Stock Penaek Webapp\\src\\services\\zones.ts`
- `C:\\Stock Penaek Webapp\\src\\services\\suppliers.ts`

Tests:
- `C:\\Stock Penaek Webapp\\tests`

## 19. สรุปสั้นที่สุด

ลำดับเทสที่ดีที่สุด:

1. OWNER สร้างฐานข้อมูลใช้งาน
2. ADMIN ทำ protected business change
3. DEV verify / matching / review
4. STOCK ใช้งาน read-only search/compare
5. user branch อื่น เทส scope leak
6. OWNER ปิดท้ายด้วย end-to-end + dashboard + historical snapshot

ถ้าไล่ตามนี้ จะเห็นทั้ง:
- data creation
- protected approval
- compare/search correctness
- permission correctness
- deploy-readiness
