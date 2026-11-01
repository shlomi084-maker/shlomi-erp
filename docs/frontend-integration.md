# חיבור האפליקציה (Lovable) ל-Backend

האפליקציה ודף הנחיתה נבנים ב-Lovable ולא נמצאים בריפו הזה. הם מדברים עם n8n דרך **שני webhooks בלבד**, בלי
מפתחות ובלי גישה ישירה ל-Airtable. n8n מחזיק את כל הסודות.

| מה | Endpoint | Workflow | מי קורא לו |
|---|---|---|---|
| API של אפליקציית הניהול | `POST <BASE>/webhook/app` | WF13 App API | אפליקציית הניהול (כל המסכים + הצ'אט) |
| קליטת לידים | `POST <BASE>/webhook/lead` | WF2 Leads Intake | הטופס בדף הנחיתה |

## מה זה `<BASE>`

| איך n8n רץ | `<BASE>` |
|---|---|
| Docker מקומי + Cloudflare tunnel | הערך של `N8N_WEBHOOK_URL` בלי הסלאש בסוף, למשל `https://n8n.example.com` |
| n8n Cloud | `https://<instance>.app.n8n.cloud` |

**לא `http://localhost:5678`.** האפליקציה ב-Lovable רצה ב-HTTPS, ודפדפן חוסם קריאות ממנה לכתובת HTTP (mixed content).
לכן ל-n8n מקומי חייבים את ה-tunnel (`docker compose --profile tunnel up -d`).

הכתובות פעילות רק כש-WF13 ו-WF2 **מופעלים (Active/Published)**. הכתובות `/webhook-test/...` עובדות רק כשה-editor
מאזין ("Listen for test event"); לא להכניס אותן לאפליקציה.

## איפה מכניסים את הכתובות ב-Lovable

1. **אפליקציית הניהול** — לפני שמדביקים את הפרומפט מ-[`app/lovable-prompt.md`](../app/lovable-prompt.md), מחליפים
   בו את `WEBHOOK_URL` ב-`<BASE>/webhook/app`. באפליקציה קיימת: שולחים ל-Lovable
   `Change API_URL to "<BASE>/webhook/app". Do not change anything else.`
2. **דף הנחיתה** — בפרומפט מ-[`app/landing-prompt.md`](../app/landing-prompt.md) מחליפים את `LEAD_WEBHOOK_URL` ב-`<BASE>/webhook/lead`.
3. Publish. אין צורך ב-proxy או ב-Supabase: שני ה-webhooks פתוחים ל-CORS (`allowedOrigins: *`).

## `/webhook/app` — החוזה המלא

תמיד `POST`, גוף JSON, תשובה JSON. בלי headers של אימות.

שמות טבלאות מותרים (בדיוק): `Leads`, `Invoices`, `Customers`, `Orders`, `Products`, `Tasks`.
השדות של כל טבלה: [airtable-schema.md](airtable-schema.md).

### read

```json
{ "action": "read", "table": "Leads", "filter": "{Status}='New'", "limit": 100 }
```

`filter` (נוסחת Airtable) ו-`limit` (ברירת מחדל 100) אופציונליים. תשובה:

```json
{ "data": [ { "id": "recXXXX", "createdTime": "2026-10-30T09:00:00.000Z", "fields": { "Name": "...", "Status": "New" } } ] }
```

### create

```json
{ "action": "create", "table": "Tasks", "payload": { "Title": "להתקשר לספק", "Status": "Open" } }
```

תשובה: `{ "id": "recXXXX", "createdTime": "...", "fields": { ... } }`.

**חשבונית חדשה** שולחת רק את מה שהמשתמש מזין:

```json
{ "action": "create", "table": "Invoices", "payload": { "CustomerId": "CUST-0001", "Amount": 1000, "DocType": "חשבונית מס" } }
```

התשובה חוזרת מיד עם רשומה בלי מספר ובלי מע"מ. ברקע WF13 מפעיל את WF1 (מע"מ, `INV-000N`, `Ready`) ואז את WF8
(מסמך ב-Drive, `PdfUrl`, `Issued`). אחרי כמה שניות לחיצה על רענון מציגה את החשבונית המלאה.

### update

```json
{ "action": "update", "table": "Invoices", "payload": { "id": "recXXXX", "Status": "Paid" } }
```

`id` הוא מזהה הרשומה (`rec...`) מתוך תשובת ה-read. רק השדות ששולחים משתנים.

### chat

```json
{ "action": "chat", "message": "מה ההבדל בין Ready ל-Issued?" }
```

תשובה: `{ "reply": "..." }`. יכול לקחת 5–20 שניות (מודל שפה); להציג אינדיקטור הקלדה. בתקלה מגיעה תשובה מנומסת ב-`reply`.

### שגיאות

`action` לא מוכר → HTTP 400 עם `{ "ok": false, "error": "unknown action. use read | create | update | chat" }`.
שגיאת Airtable (טבלה או שדה לא קיימים) → HTTP 500 מ-n8n, והתראה לבעלים בטלגרם דרך WF0. באפליקציה: toast.

## `/webhook/lead` — טופס לידים

```json
{ "name": "דנה לוי", "email": "dana@example.com", "phone": "052-1234567", "company": "סטודיו לוי", "interest": "מסכים למעצבים" }
```

רק `email` חובה (חייב להכיל `@`). תשובות:

| מצב | HTTP | גוף |
|---|---|---|
| ליד חדש | 200 | `{ "ok": true, "created": true, "id": "rec..." }` |
| המייל כבר קיים | 200 | `{ "ok": true, "created": false, "reason": "duplicate", "id": "rec..." }` |
| אין מייל | 400 | `{ "ok": false, "error": "email is required" }` |

ליד חדש מקבל `Status=New`, בעל העסק מקבל מייל התראה, ו-WF3 שולח לו מייל קר בהרצה הבאה (כל 3 שעות).

## בדיקה מהטרמינל

```bash
BASE=https://n8n.example.com
curl -s -X POST "$BASE/webhook/app"  -H "Content-Type: application/json" -d '{"action":"read","table":"Leads","limit":3}'
curl -s -X POST "$BASE/webhook/app"  -H "Content-Type: application/json" -d '{"action":"nope"}'          # 400
curl -s -X POST "$BASE/webhook/lead" -H "Content-Type: application/json" -d '{"name":"Test","email":"test@example.com"}'
```

או `python3 scripts/smoke_test.py` שבודק את שני ה-endpoints ואת שרשרת החשבונית.

## קישורים לבוטים בטלגרם

הבוטים לא עוברים דרך האפליקציה. בדף הנחיתה מקשרים לבוט התמיכה: `https://t.me/<שם המשתמש של בוט התמיכה>`.
בוט המנהל פרטי (WF9 עונה רק ל-`OWNER_TELEGRAM_CHAT_ID`), אין לפרסם אותו.

## אבטחה

כתובת ה-webhook נמצאת בקוד הלקוח. לדמו זה מקובל: היא לא מכילה סוד, ו-n8n מחזיק את ה-PAT של Airtable.
בפרודקשן: header סודי שנבדק ב-WF13, או Edge Function שמחזיקה את הכתובת.
