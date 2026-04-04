# Trae AI Prompts สำหรับสรุปโปรเจกต์และเริ่ม Phase 6

เอกสารนี้มี 2 Prompt:

1. **Prompt สรุปโปรเจกต์ทั้งหมดแบบยังไม่เริ่มทำงาน**
2. **Prompt เริ่ม PHASE 6: SEARCH / COMPARISON แบบละเอียด**

---

## Prompt 1 — สรุปทุกเฟสทั้งหมดแบบ “ยังไม่เริ่มทำงาน”

> ใช้ Prompt นี้ก่อน เพื่อให้ Trae AI อ่าน codebase และสรุปสถานะทั้งหมดของโปรเจกต์อย่างละเอียดมาก โดย **ยังไม่ต้องเริ่ม implement phase ใหม่**

```text
คุณคือ Principal System Architect + Senior Fullstack Engineer + Senior Database Designer + Senior QA Lead

ภารกิจของคุณตอนนี้:
- ยังไม่ต้องเริ่ม implement feature ใหม่
- ยังไม่ต้องแก้โค้ด
- ยังไม่ต้องเริ่ม Phase 6
- ให้ทำหน้าที่ “สรุปสถานะโปรเจกต์ทั้งหมด” จาก codebase ปัจจุบันแบบละเอียดมากที่สุด เพื่อเตรียมส่งงานต่อและทำงานต่ออย่างปลอดภัยใน Trae AI

==================================================
สิ่งที่ต้องทำตอนนี้
==================================================

1. อ่าน codebase ปัจจุบันทั้งหมดที่เกี่ยวข้องกับ phase ที่ทำมาแล้ว
2. สรุปว่าโปรเจกต์นี้ทำถึงเฟสไหนแล้ว
3. สรุปให้ละเอียดว่า “แต่ละ Phase ทำอะไรเสร็จแล้วบ้าง”
4. สรุปว่า “ยังขาดอะไรบ้าง” ในแต่ละ Phase
5. สรุปว่า “อะไรคือ blocker / risk / technical debt / residual risk”
6. สรุปว่า “สิ่งใดห้ามเปลี่ยน” เพื่อไม่ให้ระบบพัง
7. สรุปว่า “ตอนนี้ควรเริ่ม Phase 6 อย่างไร” แต่ยังไม่ต้อง implement
8. สรุปแบบละเอียดมาก ให้ใช้เป็น handoff document สำหรับ Trae AI ทำต่อได้ทันที

==================================================
ข้อกำหนดสำคัญ
==================================================

- ห้ามเริ่ม implement feature ใหม่
- ห้ามแก้โค้ด
- ห้ามเริ่ม Phase 6
- ห้ามเพิ่ม migration ใหม่
- ห้าม refactor
- ให้สรุปอย่างเดียว
- ถ้าพบ ambiguity ให้สรุป assumption แยกให้ชัด
- ให้เขียนเป็นภาษาไทยทั้งหมด
- ให้ละเอียดระดับ production handoff
- ต้องสรุปจากสิ่งที่ “มีอยู่จริงใน codebase” ไม่ใช่เดา

==================================================
ข้อมูลความคืบหน้าที่ต้องถือเป็น baseline
==================================================

PHASE 1: FOUNDATION / DATA MODEL BASE — เสร็จแล้ว
- foundation schema
- audit foundation
- branch-ready foundation
- attachment base
- alias/tag/spec base
- canonical group base
- supplier reliability base
- soft delete/archive base

PHASE 2: SUPPLIER / ATTACHMENT / CORE MANAGEMENT — เสร็จแล้ว
- supplier entity
- supplier detail fields
- supplier-product relation
- attachment validation/security
- admin edit supplier -> dev verify flow
- supplier reliability calculation base

PHASE 3: PRICE MODEL / PRICE TIER / COST FORMULA — เสร็จแล้ว
- price_records
- quantity tiers
- THB/USD normalization
- VAT breakdown
- shipping/fuel/labor/utility cost
- conflict detection
- cost formula
- cost formula versioning
- lifecycle: active / replaced / archived
- timezone normalization fix
- tests ผ่าน
- manual QA ผ่าน

PHASE 4: PRODUCT MATCHING — เสร็จแล้ว
- canonical product groups
- temporal membership rows
- matching operations
- add / remove / move / merge / split
- lock_state
- dependency checks
- rollback-safe transaction flow
- tests ผ่าน
- manual QA ผ่าน

PHASE 5: VERIFICATION WORKFLOW / RISK ENGINE — เสร็จแล้ว
- generic verification requests
- request items
- actions / audit trail
- assignments
- dependency warnings
- escalations / SLA
- strict workflow transitions
- risk_score 0–100
- transactional approval engine
- tests ผ่าน
- manual QA ผ่าน

PHASE 6: SEARCH / COMPARISON — ยังไม่เริ่ม
PHASE 7: NOTIFICATION SYSTEM — ยังไม่เริ่ม
PHASE 8: UI ZONES — ยังไม่เริ่ม
PHASE 9: HISTORICAL SNAPSHOT / REPORT SAFETY — ยังไม่เริ่ม
PHASE 10: HARDENING / PERFORMANCE / MIGRATION / ROLLOUT — ยังไม่เริ่ม

==================================================
สิ่งที่ต้องสรุปอย่างละเอียด
==================================================

A. Executive Summary
- โปรเจกต์นี้คืออะไร
- สถาปัตยกรรมรวมตอนนี้เป็นอย่างไร
- ตอนนี้อยู่ phase ไหน
- พร้อมทำ phase ต่อไปหรือยัง

B. Phase-by-Phase Detailed Status
สำหรับทุก Phase 1–10 ให้สรุป:
- เป้าหมายของเฟส
- สิ่งที่ทำเสร็จแล้ว
- ไฟล์หลักที่เกี่ยวข้อง
- migration ที่เกี่ยวข้อง
- tests ที่มี
- manual QA ที่มี
- สิ่งที่ยังไม่ทำ
- risk ที่ยังเหลือ
- พร้อมไป phase ถัดไปหรือไม่

C. Current Data Model Summary
- ตารางหลักที่มีอยู่ตอนนี้
- ตารางที่เพิ่มมาในแต่ละ phase
- ความสัมพันธ์สำคัญ
- soft delete / archive / temporal models ที่มี
- จุดที่ต้องระวังเรื่อง backward compatibility

D. Current Business Rules Summary
- pricing rules
- formula rules
- matching rules
- verification rules
- role / permission / visibility rules
- dependency / rollback / transaction rules
- สิ่งที่ห้ามพัง

E. Testing Status Summary
- test files ที่มี
- coverage เชิงตรรกะที่ครอบคลุมแล้ว
- regression status
- ส่วนไหนยังไม่มี test หรือยังไม่ลึกพอ

F. Remaining Work Summary
- Phase 6 ต้องทำอะไร
- Phase 7 ต้องทำอะไร
- Phase 8 ต้องทำอะไร
- Phase 9 ต้องทำอะไร
- Phase 10 ต้องทำอะไร

G. Risks / Technical Debt / Residual Risk
- สิ่งที่ยังเสี่ยง
- สิ่งที่ควรตรวจบน Postgres/Staging จริง
- สิ่งที่ควรทำระวังมากเป็นพิเศษใน phase ต่อไป

H. Handoff Guidance for Trae AI
- ถ้าจะทำ Phase 6 ต่อ ต้องเริ่มจากอะไร
- สิ่งใดห้ามเปลี่ยน
- สิ่งใดควรตรวจซ้ำก่อนเริ่ม
- ลำดับที่ปลอดภัยที่สุดในการ implement

==================================================
รูปแบบผลลัพธ์ที่ต้องการ
==================================================

ให้ตอบเป็น Markdown ภาษาไทยละเอียดมาก โดยใช้หัวข้อแบบนี้:

# สรุปโปรเจกต์ปัจจุบัน
## 1. Executive Summary
## 2. สถานะราย Phase
### PHASE 1
### PHASE 2
...
### PHASE 10
## 3. สรุป Data Model ปัจจุบัน
## 4. สรุป Business Rules ปัจจุบัน
## 5. สรุป Test / QA ปัจจุบัน
## 6. งานที่ยังเหลือ
## 7. ความเสี่ยงและจุดที่ต้องระวัง
## 8. แนวทางเริ่ม Phase 6 อย่างปลอดภัย

ห้ามเริ่ม implement
ห้าม generate code
ห้ามเริ่ม migration
ให้สรุปอย่างเดียว
```

---

## Prompt 2 — เริ่ม PHASE 6 ใน Trae AI แบบละเอียด

> ใช้ Prompt นี้หลังจากได้สรุปจาก Prompt 1 แล้ว และพร้อมเริ่มทำ Phase 6 จริง

```text
คุณคือ Principal System Architect + Senior Backend Engineer + Senior Search Engineer + Senior Database Designer + Senior QA Lead

ตอนนี้โปรเจกต์นี้ทำเสร็จแล้วถึง PHASE 5 และพร้อมเริ่ม PHASE 6

==================================================
สถานะปัจจุบันของระบบ
==================================================

เสร็จแล้ว:
- PHASE 1: FOUNDATION
- PHASE 2: SUPPLIER / ATTACHMENT
- PHASE 3: PRICE MODEL / COST FORMULA
- PHASE 4: PRODUCT MATCHING
- PHASE 5: VERIFICATION WORKFLOW / RISK ENGINE

ยังไม่เริ่ม:
- PHASE 6: SEARCH / COMPARISON
- PHASE 7: NOTIFICATION
- PHASE 8: UI ZONES
- PHASE 9: HISTORICAL SNAPSHOT
- PHASE 10: HARDENING

==================================================
เป้าหมายของ PHASE 6
==================================================

สร้างระบบ Search / Comparison ที่ใช้งานจริงได้ โดยรองรับ:

1. Quick Search
- ค้นหาสินค้าเร็ว
- ค้นหาตามชื่อ
- SKU
- alias
- supplier
- category
- tags

2. Deep Comparison Search
- เทียบสินค้าชนิดเดียวกันใน canonical group
- เปรียบเทียบจาก:
  - base price
  - after VAT
  - with shipping
  - real total cost
- เลือก filter ได้ละเอียด
- เลือก sorting ได้ละเอียด

3. Historical Analysis
- ดูราคาย้อนหลัง
- ดู lifecycle ของ price record
- ดูข้อมูลตามช่วงเวลา

4. Verification/Admin Search
- ค้นหารายการ verification request
- filter ตาม status / risk / assignee / overdue

==================================================
PHASE 6 RULES
==================================================

- ห้ามกระโดดไปทำ Phase 7
- ต้องทำทีละ step
- ต้องหยุดทุก step
- ต้องมี test ก่อนจบแต่ละ step
- ต้องมี manual QA ก่อนจบ phase
- ต้องรักษา backward compatibility
- ห้ามพังของ Phase 1–5
- ห้ามทำ UI ใหญ่ก่อน design/implementation backend พร้อม

==================================================
PHASE 6 - STEP STRUCTURE
==================================================

ทำงานตามลำดับนี้:

STEP 1: DESIGN ONLY
STEP 2: IMPLEMENTATION
STEP 3: TESTS ONLY
STEP 4: MANUAL QA ONLY

==================================================
PHASE 6 - STEP 1: DESIGN ONLY
==================================================

GOAL:
ออกแบบ search/comparison architecture ที่รองรับ scale, filter ลึก, compare logic, และ historical queries โดยไม่ทำให้ระบบเดิมพัง

REQUIREMENTS:

1. Search Scope
ออกแบบให้รองรับการค้นหาอย่างน้อย:
- product
- supplier
- canonical group
- price records
- verification requests

2. Search Modes
- quick search
- deep comparison
- historical analysis
- admin/verification search

3. Filters
รองรับอย่างน้อย:
- product name
- alias
- SKU
- category
- tag
- supplier
- branch
- currency
- price range
- final_total_cost
- delivery_mode
- area_scope
- verification status
- risk level
- lock state
- archived / active / replaced

4. Comparison Logic
ต้องออกแบบการ compare จาก:
- normalized_amount
- final_total_cost
- VAT
- shipping/fuel/labor/utility
- active price only
- latest effective price
- historical period
- canonical group based comparison

5. Search Architecture
ให้เสนอว่า:
- ใช้ DB query อย่างเดียวพอไหม
- ต้องมี index อะไร
- อะไรควรเป็น materialized view / cached read model
- อะไรควรเป็น future search engine integration point

6. Performance
- target search <= 5 วินาที
- รองรับข้อมูลหลักล้าน–สิบล้าน records
- อย่าทำให้ phase นี้ over-engineered เกินจำเป็น

==================================================
สิ่งที่ต้องทำใน STEP 1
==================================================

ออกแบบ:
- search architecture
- query model
- table/index implications
- comparison result model
- filter/sort strategy
- historical query strategy
- saved views / presets strategy (ถ้าเหมาะสม)

OUTPUT:
- schema/index recommendation
- service/query design
- assumptions
- risk notes

STOP after STEP 1
WAIT for confirmation

==================================================
รูปแบบผลลัพธ์
==================================================

PHASE 6 - STEP 1

1. Goal
2. What you are doing
3. Search / Comparison Design
4. Schema / Index Recommendations
5. Validation / Performance Notes
6. Assumptions
7. Risks
8. Ready for next step? (Yes/No)
```

---

## วิธีใช้งานที่แนะนำ

ใช้ลำดับนี้:

1. เอา **Prompt 1** ไปให้ Trae AI อ่านก่อน  
2. ให้มันสรุปเป็น handoff document ให้เสร็จ  
3. ตรวจว่า handoff ครบและตรงกับของจริง  
4. ค่อยใช้ **Prompt 2** เพื่อเริ่ม PHASE 6

---

## หมายเหตุสำคัญ

- ตอนนี้ **PHASE 5 เสร็จแล้ว** จาก manual QA ล่าสุด fileciteturn13file0
- ดังนั้นการเริ่ม PHASE 6 ต่อใน Trae AI ถือว่าเหมาะสม
- แต่ควรให้ Trae AI “สรุปของเดิมก่อน” ตาม Prompt 1 เพื่อกัน context หลุด

