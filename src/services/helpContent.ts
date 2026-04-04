import type { SupportedLocale } from './i18n'

export interface HelpEntry {
  title: string
  body: string
  example?: string
}

const HELP_CONTENT: Record<SupportedLocale, Record<string, HelpEntry>> = {
  th: {
    'login.username': {
      title: 'ชื่อผู้ใช้',
      body: 'กรอกชื่อผู้ใช้ที่ใช้เข้าระบบ ถ้าไม่แน่ใจให้ใช้ชื่อที่ผู้ดูแลระบบสร้างให้',
      example: 'ตัวอย่าง: owner หรือ stock01',
    },
    'login.password': {
      title: 'รหัสผ่าน',
      body: 'กรอกรหัสผ่านของบัญชีนี้ให้ครบทุกตัวอักษร ถ้าพิมพ์ผิดระบบจะไม่ให้เข้า',
      example: 'ตัวอย่าง: รหัสผ่านที่ได้รับจากผู้ดูแลระบบ',
    },
    'login.totp': {
      title: 'รหัสยืนยัน 6 หลัก',
      body: 'กรอกเฉพาะเมื่อบัญชีนี้เปิดใช้การยืนยันตัวตนสองชั้น ถ้าไม่ได้เปิดไว้ ปล่อยว่างได้',
      example: 'ตัวอย่าง: 123456',
    },
    'search.quick': {
      title: 'ค้นหาเร็ว',
      body: 'ใช้หาสินค้าด้วย SKU, ชื่อสินค้า หรือคำที่เคยตั้งเป็นชื่อเรียก/alias',
      example: 'ตัวอย่าง: SKU-MAIN-001 หรือ เหล็กฉาก',
    },
    'search.compare': {
      title: 'เทียบราคา',
      body: 'ใช้เทียบราคาที่ใช้งานได้จริง โดยระบบจะเรียงจากต้นทุนรวมที่ถูกที่สุดก่อน',
      example: 'ตัวอย่าง: ใส่จำนวน 20 เพื่อดูว่าร้านไหนคุ้มที่สุดในช่วง 20 ชิ้น',
    },
    'search.history': {
      title: 'ดูราคาย้อนหลัง',
      body: 'ใช้ตรวจว่าราคาเคยเป็นเท่าไรในช่วงเวลาที่ต้องการ เหมาะกับเช็กประวัติและอ้างอิงย้อนหลัง',
      example: 'ตัวอย่าง: เลือกวันที่เริ่มและวันที่สิ้นสุดเพื่อดูการเปลี่ยนราคา',
    },
    'verification.queue': {
      title: 'คิวตรวจสอบ',
      body: 'ใช้เปิดรายการที่ต้องมีคนอนุมัติหรือทบทวนก่อนให้ระบบเดินต่อ',
      example: 'ตัวอย่าง: กรองตาม risk = critical เพื่อดูงานเร่งด่วน',
    },
    'verification.filters': {
      title: 'ตัวกรองคิว',
      body: 'ใช้แยกงานตามสถานะ ความเสี่ยง หรือผู้รับผิดชอบ เพื่อหาเคสที่ต้องทำต่อให้เร็วขึ้น',
      example: 'ตัวอย่าง: ใส่ me ในช่องผู้รับผิดชอบเพื่อดูงานของตัวเอง',
    },
    'notifications.center': {
      title: 'ศูนย์แจ้งเตือน',
      body: 'รวมการแจ้งเตือนสำคัญ เช่น งานรอตรวจ งานเลยเวลา หรือปัญหาการส่งแจ้งเตือน',
      example: 'ตัวอย่าง: กด Open related item เพื่อไปยังหน้าที่เกี่ยวข้องทันที',
    },
    'settings.general': {
      title: 'ตั้งค่าระบบหลัก',
      body: 'ใช้ตั้งค่าชื่อระบบ ภาษาเริ่มต้น สีหลัก และข้อจำกัดพื้นฐานของระบบ',
      example: 'ตัวอย่าง: เปลี่ยนภาษาเริ่มต้นเป็น English สำหรับทีมต่างชาติ',
    },
    'settings.theme': {
      title: 'โหมดธีม',
      body: 'เลือกหน้าตาระบบให้เหมาะกับการใช้งานระหว่างโทนสว่าง โทนมืด หรือให้ระบบเลือกให้อัตโนมัติ',
      example: 'ตัวอย่าง: ใช้ Auto เพื่อให้ธีมเปลี่ยนตามเครื่องของผู้ใช้',
    },
    'settings.google': {
      title: 'เชื่อม Google Sheets',
      body: 'ใช้เชื่อมระบบกับ Google เพื่อสร้างหรือซิงก์ชีตสำหรับงานเดิมที่ยังใช้ Google อยู่',
      example: 'ตัวอย่าง: ใส่ OAuth Client ID/Secret แล้วกด Sign in with Google',
    },
    'suppliers.form': {
      title: 'ข้อมูลร้านค้า',
      body: 'กรอกข้อมูลร้านหรือผู้ขายให้ครบพอสำหรับค้นหา ติดต่อ และใช้เทียบราคาในภายหลัง',
      example: 'ตัวอย่าง: ชื่อร้าน, เบอร์โทร, LINE, เว็บไซต์, จุดรับของ',
    },
    'suppliers.attachments': {
      title: 'ไฟล์แนบของร้าน',
      body: 'ใช้เก็บเอกสารอ้างอิง เช่น โปรไฟล์ร้าน ใบเสนอราคา หรือไฟล์ที่ใช้ยืนยันข้อมูล',
      example: 'ตัวอย่าง: อัปโหลดไฟล์ PDF ใบเสนอราคาของร้าน',
    },
    'dashboard.summary': {
      title: 'สรุปภาพรวม',
      body: 'การ์ดด้านบนใช้ดูจำนวนงานค้าง งานเกินเวลา และสัญญาณผิดปกติแบบเร็ว ๆ',
      example: 'ตัวอย่าง: ถ้า Overdue สูง ให้เปิดคิวตรวจสอบต่อทันที',
    },
  },
  en: {
    'login.username': {
      title: 'Username',
      body: 'Enter the account name used to sign in. Use the username created by your system admin.',
      example: 'Example: owner or stock01',
    },
    'login.password': {
      title: 'Password',
      body: 'Enter the password for this account exactly as it was set.',
      example: 'Example: the password provided by your admin',
    },
    'login.totp': {
      title: '6-digit verification code',
      body: 'Only fill this in when the account uses two-factor authentication. Leave it blank otherwise.',
      example: 'Example: 123456',
    },
    'search.quick': {
      title: 'Quick search',
      body: 'Use this to find a product by SKU, product name, or saved alias.',
      example: 'Example: SKU-MAIN-001 or Angle steel',
    },
    'search.compare': {
      title: 'Compare prices',
      body: 'Compare real usable prices. Results are ranked by the lowest final total cost first.',
      example: 'Example: enter quantity 20 to see the best supplier for 20 units',
    },
    'search.history': {
      title: 'Price history',
      body: 'Check what the price was during a specific time window for audit or review.',
      example: 'Example: pick a start and end date to inspect price changes',
    },
    'verification.queue': {
      title: 'Verification queue',
      body: 'Review requests that must be approved or checked before the system can continue.',
      example: 'Example: filter by critical risk to focus on urgent requests',
    },
    'verification.filters': {
      title: 'Queue filters',
      body: 'Filter by status, risk, or assignee so you can find the next action faster.',
      example: 'Example: type me in assignee to show only your items',
    },
    'notifications.center': {
      title: 'Notification center',
      body: 'Shows important alerts such as approvals, overdue work, and delivery issues.',
      example: 'Example: use Open related item to jump straight to the source record',
    },
    'settings.general': {
      title: 'Core system settings',
      body: 'Configure the app name, default language, brand colors, and base system limits.',
      example: 'Example: switch the default language to English for an international team',
    },
    'settings.theme': {
      title: 'Theme mode',
      body: 'Choose a light theme, dark theme, or let the app follow the device automatically.',
      example: 'Example: use Auto to match the user device theme',
    },
    'settings.google': {
      title: 'Google Sheets setup',
      body: 'Connect the system to Google when you still need the legacy Sheets workflow.',
      example: 'Example: enter OAuth Client ID and Secret, then click Sign in with Google',
    },
    'suppliers.form': {
      title: 'Supplier details',
      body: 'Fill in enough supplier information for search, contact, and future price comparison.',
      example: 'Example: supplier name, phone, LINE, website, pickup notes',
    },
    'suppliers.attachments': {
      title: 'Supplier attachments',
      body: 'Store reference files such as supplier profiles, quotes, or supporting documents.',
      example: 'Example: upload a PDF quote from the supplier',
    },
    'dashboard.summary': {
      title: 'Summary cards',
      body: 'Top cards give you a fast read on pending work, overdue items, and warning signals.',
      example: 'Example: when overdue rises, open the verification queue right away',
    },
  },
}

export async function loadHelpEntry(locale: SupportedLocale, key: string): Promise<HelpEntry | null> {
  const safeLocale: SupportedLocale = locale === 'en' ? 'en' : 'th'
  const entry = HELP_CONTENT[safeLocale][key]
  return entry ?? null
}
