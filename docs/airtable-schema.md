# סכימת Airtable — Shlomi ERP

Base אחד (למשל `Shlomi-ERP`) עם **שש טבלאות**. שמות הטבלאות והשדות חייבים להיות **בדיוק** כמו כאן (כולל אותיות
גדולות), כי ה-workflows והאפליקציה פונים אליהם בשם.

`scripts/airtable_setup.py` יוצר את כל הטבלאות והשדות, מוסיף שדות חסרים לטבלאות קיימות, טוען נתוני דמו
מ-`data/` ושומר את מזהי הטבלאות ב-`.local/airtable_tables.json` (שם `n8n_import.py` קורא אותם). המסמך הזה הוא
המפרט המלא, לבנייה ידנית או לבדיקה.

## לפני שמתחילים

1. יוצרים Base ריק ב-Airtable. מזהה ה-Base מופיע בכתובת: `https://airtable.com/appXXXXXXXXXXXXXX/...` → `AIRTABLE_BASE_ID`.
2. יוצרים Personal Access Token (Builder hub → Personal access tokens) עם ההרשאות
   `data.records:read`, `data.records:write`, `schema.bases:read`, `schema.bases:write`, וגישה ל-Base הזה בלבד → `AIRTABLE_PAT`.
3. אותו PAT נכנס גם ל-credential של Airtable ב-n8n.

## מפת הטבלאות והקשרים

```
 Customers ──CustomerId──┐
   (CUST-0001)           ├──▶ Invoices.CustomerId   (חשבוניות של הלקוח)
                         └──▶ Orders.CustomerId     (הזמנות של הלקוח)
 Products ──Name───────────▶ Orders.Product         (שם המוצר כטקסט)

 Leads   — עצמאית (WF2 → WF3 → WF4). ליד שנסגר נרשם ידנית כ-Customer.
 Tasks   — עצמאית (משימות של בעל העסק, מהאפליקציה).
```

**הקשרים הם מפתחות טקסט, לא Linked records — וזה מכוון.** האפליקציה כותבת דרך WF13 ערכים כמו `"CUST-0001"`
ישירות לשדה; שדה Link דורש מזהי רשומה (`rec...`) והכתיבה הייתה נכשלת. WF8 מדפיס את `CustomerId` כמו שהוא על
החשבונית. אל תמירו את השדות האלה ל-Link.

## Invoices — חשבוניות

| שדה | סוג Airtable | הגדרות | מי כותב / קורא |
|---|---|---|---|
| InvoiceNumber | Single line text (**primary**) | — | ריק ביצירה. WF1 ממלא `INV-0001`, `INV-0002`… (הגבוה הקיים + 1) |
| CustomerId | Single line text | `CUST-0001` | האפליקציה (טופס חשבונית חדשה). מפתח ל-Customers |
| Amount | Number | 2 ספרות עשרוניות | האפליקציה. **לפני מע"מ**, חייב להיות > 0 (אחרת WF1 מסמן `Invalid`) |
| VatAmount | Number | 2 ספרות עשרוניות | WF1 מחשב: 18% מ-1.1.2025, 17% לפני |
| Total | Number | 2 ספרות עשרוניות | WF1 מחשב: Amount + VatAmount. WF9 וה-דשבורד סוכמים אותו |
| Status | Single line text | **לא** Single select | ריק → `Ready` (WF1) → `Issued` (WF8) → `Paid` (האפליקציה). או `Invalid` (WF1) / `UploadFailed` (WF8) |
| PdfUrl | URL | — | WF8 כותב קישור Google Drive של המסמך |
| DocType | Single line text | `חשבונית מס` / `קבלה` / `חשבונית` | האפליקציה. WF1 ממלא `חשבונית מס` אם ריק. WF8 מדפיס בכותרת |
| Created | Created time | ISO, 24h, `Asia/Jerusalem` | אוטומטי. WF1 קובע לפיו את שיעור המע"מ |

## Customers — לקוחות

| שדה | סוג Airtable | הגדרות | הערות |
|---|---|---|---|
| CustomerId | Single line text (**primary**) | `CUST-0001` | מפתח הלקוח. ייחודי (שומרים על כך ידנית) |
| Name | Single line text | — | |
| Email | Email | — | |
| Phone | Phone number | — | |
| Company | Single line text | — | אופציונלי |
| Notes | Long text | — | |
| Created | Created time | ISO, 24h, `Asia/Jerusalem` | |

## Orders — הזמנות

| שדה | סוג Airtable | הגדרות | הערות |
|---|---|---|---|
| OrderId | Single line text (**primary**) | `ORD-0001` | |
| CustomerId | Single line text | `CUST-0001` | מפתח ל-Customers |
| Product | Single line text | — | שם המוצר כפי שהוא ב-Products.Name |
| Quantity | Number | 0 ספרות עשרוניות | |
| Total | Number | 2 ספרות עשרוניות | ש"ח |
| Status | Single line text | **לא** Single select | `New` → `Shipped` → `Delivered` |
| Created | Created time | ISO, 24h, `Asia/Jerusalem` | |

## Leads — לידים

| שדה | סוג Airtable | הגדרות | מי כותב / קורא |
|---|---|---|---|
| Name | Single line text (**primary**) | — | WF2 (מהטופס / האפליקציה) |
| Email | Email | — | WF2 בודק כפילויות לפיו (lowercase). WF4 מתאים לפיו תשובות במייל |
| Phone | Phone number | — | |
| Company | Single line text | — | אופציונלי |
| Interest | Single line text | — | נכנס לפרומפט של המייל הקר ב-WF3 |
| Status | Single line text | **לא** Single select | `New` (WF2) → `Contacted` (WF3) → `Replied` (WF4). או `EmailFailed` (WF3) |
| Created | Created time | ISO, 24h, `Asia/Jerusalem` | WF3 בוחר את הליד ה-`New` הוותיק ביותר |

## Products — מוצרים

| שדה | סוג Airtable | הגדרות | הערות |
|---|---|---|---|
| Name | Single line text (**primary**) | — | |
| Category | Single line text | — | |
| Price | Number | 0 ספרות עשרוניות | ש"ח כולל מע"מ |
| Description | Long text | — | מק"ט, מפרט, מה באריזה, אחריות |
| InStock | Checkbox | — | |

נטען מ-`data/products.csv`. בוט התמיכה (WF5) לא קורא את הטבלה הזו: הוא עונה מה-vector store ש-WF7 בונה מאותו CSV.
אם משנים מוצר, מעדכנים את ה-CSV ומריצים שוב `load_rag.py`.

## Tasks — משימות

| שדה | סוג Airtable | הגדרות | הערות |
|---|---|---|---|
| Title | Single line text (**primary**) | — | |
| Status | Single line text | **לא** Single select | `Open` / `Done` |
| Notes | Long text | — | |
| Created | Created time | ISO, 24h, `Asia/Jerusalem` | |

## איך ה-workflows ניגשים לטבלאות

| טבלה | גישה דרך | הערה |
|---|---|---|
| Invoices | מזהה טבלה (`__TBL_INVOICES__`) ב-WF1, WF8, WF9; שם הטבלה ב-WF13 | |
| Leads | מזהה טבלה (`__TBL_LEADS__`) ב-WF2, WF3, WF4; שם הטבלה ב-WF13 | |
| Customers, Orders, Products, Tasks | שם הטבלה בלבד, דרך WF13 (האפליקציה) | לכן שינוי שם טבלה שובר את האפליקציה |

## מלכודות

1. `Created` חייב להיות מסוג *Created time* ולא Date רגיל: WF1 מחשב ממנו מע"מ ו-WF3 ממיין לפיו.
   Airtable לא מאפשר ליצור אותו יחד עם הטבלה, לכן הסקריפט מוסיף אותו אחרי היצירה.
2. כל `Status` הוא טקסט חופשי ולא *Single select*. אחרת כתיבת ערך שלא הוגדר מראש (`EmailFailed`, `UploadFailed`) נכשלת.
3. השדה הראשון בכל טבלה הוא ה-primary field. ב-Airtable הוא נוצר עם השם `Name`; משנים את שמו ואת סוגו לפי הטבלאות למעלה.
4. אל תשנו שמות של טבלאות או שדות אחרי הייבוא: הביטויים ב-n8n והאפליקציה פונים אליהם בשם.

## מגבלות

Airtable מאפשר ~5 בקשות לשנייה ל-Base; הסקריפטים ממתינים בין קריאות. Free plan: 1,000 רשומות ל-Base, מספיק בהרבה לדמו.
