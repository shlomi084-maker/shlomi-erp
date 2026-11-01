# Lovable — פרומפט הבנייה לאפליקציית הניהול

לפני שמדביקים: להחליף `WEBHOOK_URL` בכתובת ה-Production של WF13 (`<BASE>/webhook/app`; ראו [docs/frontend-integration.md](../docs/frontend-integration.md)).

---

## פרומפט ראשון (להדביק כמו שהוא)

```
Build an internal admin web app for a small Israeli electronics store called "Shlomi Electronics" (שלומי אלקטרוניקה).

Language & layout: Hebrew UI, RTL layout (dir="rtl"), ILS currency (₪), dates as dd/mm/yyyy. Clean, modern, light theme, blue accent (#1f4e79). Mobile-friendly.

Backend: there is NO database in this app. All data comes from one REST endpoint (an n8n webhook). Put the URL in a single config constant:
  API_URL = "WEBHOOK_URL"
Every call is HTTP POST to API_URL with a JSON body and returns JSON. Do not add authentication headers.

API contract:
- Read:   { "action": "read", "table": "<Leads|Invoices|Products|Tasks>", "filter": "<optional Airtable formula>", "limit": 100 }
          → { "data": [ { "id": "rec...", "createdTime": "...", "fields": { ...columns } }, ... ] }
- Create: { "action": "create", "table": "<name>", "payload": { ...columns } }
          → { "id": "rec...", "fields": { ... } }
- Update: { "action": "update", "table": "<name>", "payload": { "id": "rec...", ...changed columns } }
          → { "id": "rec...", "fields": { ... } }
- Chat:   { "action": "chat", "message": "<user text>" }
          → { "reply": "<assistant text>" }
Errors return HTTP 400 with { "ok": false, "error": "..." } — show a toast.

Tables and columns (exact names):
- Leads:    Name, Email, Phone, Company, Interest, Status (New | Contacted | Replied | EmailFailed), Created
- Invoices: InvoiceNumber, CustomerId, Amount, VatAmount, Total, Status (Ready | Issued | Paid | Invalid), PdfUrl, Created
- Products: Name, Category, Price, Description, InStock (boolean)
- Tasks:    Title, Status (Open | Done), Notes, Created

Screens (sidebar navigation on the right, RTL):
1. דשבורד (Dashboard): four stat cards computed client-side from read calls — הכנסות (sum of Total where Status is Issued or Paid), חוב לקוחות (sum of Total where Status = Issued), לידים חדשים (count Status = New), משימות פתוחות (count Status = Open). Below: a bar chart of invoice totals by Status, and a list of the 5 newest leads.
2. לידים (Leads): table with search and a Status filter; colored status badges; "ליד חדש" button opens a form (Name, Email, Phone, Company, Interest) that calls create with Status "New".
3. חשבוניות (Invoices): table sorted by InvoiceNumber desc; Amount/VatAmount/Total formatted as ₪ with 2 decimals; PdfUrl shown as a "פתח מסמך" link when present; a "סמן כשולם" action that calls update with Status "Paid" (only for Issued rows); "חשבונית חדשה" form with CustomerId and Amount only (VAT, number and document are generated automatically by the backend — say so in a helper text).
4. מוצרים (Products): card grid with Name, Category, Price, InStock badge, expandable Description; search box.
5. משימות (Tasks): checklist; toggling calls update with Status Open/Done; "משימה חדשה" form (Title, Notes).
6. עוזר (Chat): a chat panel that POSTs { action: "chat", message } and renders "reply". Keep message history in component state. Show a typing indicator while waiting.

General: loading skeletons, empty states in Hebrew, toast on success/error, refresh button on each screen. No auto-refresh anywhere (every call is an n8n execution and the Cloud trial has a 1,000-execution quota). Keep the code simple: one API helper function, one page per screen.
```

## שיפורים אחרי הבנייה הראשונה (הודעה אחת בכל פעם)

0. (בוצע 19.9.2026) `בטל את הרענון האוטומטי של הדשבורד (כל 60 שניות). הנתונים ייטענו פעם אחת בכניסה למסך ורק בלחיצה על כפתור הרענון. אל תשנה שום דבר אחר.`

1. `הוסף בדשבורד גרף עוגה של לידים לפי סטטוס ליד גרף החשבוניות.`
2. `בטבלת החשבוניות הוסף סינון לפי סטטוס וסכום כולל בתחתית הטבלה.`
3. `במסך הלידים, ליד שהסטטוס שלו EmailFailed יוצג באדום עם טולטיפ "שליחת המייל נכשלה".`
4. `הוסף בראש כל מסך את הזמן של הרענון האחרון.`
5. `הפוך את הצ'אט לזמין גם כחלון צף בפינה השמאלית התחתונה בכל המסכים.`

## השלמה לפי המפרט (בוצע 20.9.2026, הודעה אחת)

```
Add two admin screens using the same API (tables "Customers" and "Orders"):
- לקוחות (Customers): table with search; columns CustomerId, Name, Email, Phone, Company, Notes, Created; "לקוח חדש" form (CustomerId, Name, Email, Phone, Company, Notes) that calls create.
- הזמנות (Orders): table with search and Status filter (New | Shipped | Delivered) with colored badges; columns OrderId, CustomerId, Product, Quantity, Total (₪), Status, Created; "הזמנה חדשה" form (OrderId, CustomerId, Product, Quantity, Total) that calls create with Status "New".
Add both to the sidebar between לידים and חשבוניות.
Invoices: add a "סוג מסמך" select to the "חשבונית חדשה" form with options חשבונית מס (default), קבלה, חשבונית, sent as field "DocType"; show a "סוג" column in the invoices table (DocType, default חשבונית מס when empty).
Dashboard: add a pie chart "לידים לפי סטטוס" next to the invoices bar chart.
Do not change anything else.
```

## פרסום

Lovable → Publish. פורסם ב-Lovable (פרויקט "Shlomi Electronics Hub", shlomi-erp) וכובה אחרי ההגשה, ספטמבר 2026. הכתובת רשומה ב-README ובתסריט ההדגמה. ה-webhook פתוח ל-CORS (`allowedOrigins: *`) ב-WF13, אז אין צורך ב-proxy.

## הערת אבטחה להצגה

כתובת ה-webhook נמצאת בקוד הלקוח. זה מקובל לדמו: היא לא מכילה סוד, ו-n8n הוא שמחזיק את ה-PAT של Airtable ואוכף מה מותר.
בפרודקשן: header סודי שנבדק ב-WF13, או Edge Function ב-Lovable (Supabase) שמחזיקה את הכתובת.

