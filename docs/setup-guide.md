# מדריך הקמה — Shlomi ERP מאפס

הסדר חשוב: n8n → Airtable → credentials → ייבוא → RAG → אפליקציה. כל הפקודות מתיקיית הריפו.
דרישות: Docker Desktop, Python 3.9+, חשבונות Airtable, Google AI Studio (Gemini), Google (Gmail + Drive), Telegram, Lovable,
ו-Cloudflare (חינם, בשביל כתובת HTTPS קבועה).

## 1. n8n מקומי ב-Docker

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"     # → N8N_ENCRYPTION_KEY ב-.env
```

**Tunnel (חובה לטלגרם ולאפליקציה):** Cloudflare Zero Trust → Networks → Tunnels → Create tunnel (Cloudflared) →
מעתיקים את ה-token ל-`CLOUDFLARE_TUNNEL_TOKEN`. בלשונית Public Hostname מגדירים hostname (למשל `n8n.example.com`)
ו-Service `http://n8n:5678`. ב-`.env`:

```
N8N_WEBHOOK_URL=https://n8n.example.com/
N8N_PROXY_HOPS=1
N8N_URL=https://n8n.example.com
```

```bash
docker compose --profile tunnel up -d
docker compose ps        # n8n צריך להיות healthy
```

פותחים את `N8N_URL`, יוצרים משתמש owner, ואז Settings → n8n API → Create an API key → `N8N_API_KEY`.

> **בלי חשבון/דומיין ב-Cloudflare:** `docker compose --profile quicktunnel up -d quicktunnel`, ואז
> `docker compose logs quicktunnel` מציג כתובת `https://<מילים>.trycloudflare.com`. שמים אותה (עם `/` בסוף) ב-`N8N_WEBHOOK_URL`,
> `N8N_PROXY_HOPS=1`, ומריצים `docker compose up -d n8n`. הכתובת מתחלפת בכל הפעלה מחדש של ה-tunnel — מתאים לבדיקות, לא להצגה.
>
> בלי tunnel (`docker compose up -d`) הכל עובד ב-`http://localhost:5678` חוץ מבוטי הטלגרם והאפליקציה ב-Lovable.
> n8n Cloud במקום Docker: מדלגים על השלב, `N8N_URL` = כתובת ה-instance.

## 2. Airtable

Base ריק + PAT לפי [airtable-schema.md](airtable-schema.md) → `AIRTABLE_BASE_ID`, `AIRTABLE_PAT`. מלאים גם את
`OWNER_EMAIL` (כתובת ה-Gmail שתחובר ל-n8n), ואז:

```bash
python3 scripts/airtable_setup.py      # 6 טבלאות + נתוני דמו + .local/airtable_tables.json
```

## 3. בוטים בטלגרם

1. ב-[@BotFather](https://t.me/BotFather): `/newbot` פעמיים.
   - **בוט מנהל** (פרטי לבעל העסק): WF9 עונה בו לשאלות כמו "מה ההכנסות?", ו-WF0/WF4 שולחים בו התראות.
   - **בוט תמיכה** (ציבורי ללקוחות): WF5, סוכן RAG שעונה מהמדיניות ומהקטלוג.
2. שולחים הודעה כלשהי לבוט המנהל, ופותחים `https://api.telegram.org/bot<MANAGER_TOKEN>/getUpdates`.
   מעתיקים את `"chat":{"id":...}` ל-`OWNER_TELEGRAM_CHAT_ID`.
   (עושים את זה **לפני** הייבוא: אחרי שה-webhook רשום, `getUpdates` מחזיר ריק.)

## 4. Credentials ב-n8n

Credentials → Add, שישה. אחרי השמירה מעתיקים את ה-id מכתובת הדף (`/home/credentials/<ID>`) ל-`.env`:

| Credential ב-n8n | סוג | משתנה |
|---|---|---|
| Google Gemini | Google Gemini(PaLM) API, מפתח מ-aistudio.google.com | `CRED_GEMINI` |
| Airtable | Airtable Personal Access Token (אותו PAT) | `CRED_AIRTABLE` |
| Telegram Manager | Telegram API, token של בוט המנהל | `CRED_TELEGRAM_MANAGER` |
| Telegram Support | Telegram API, token של בוט התמיכה | `CRED_TELEGRAM_SUPPORT` |
| Gmail | Gmail OAuth2 | `CRED_GMAIL` |
| Google Drive | Google Drive OAuth2 | `CRED_GDRIVE` |

Gmail/Drive: ב-Google Cloud Console יוצרים OAuth client (Web), מפעילים את Gmail API ו-Drive API, ומוסיפים ל-Authorized
redirect URIs את ה-OAuth Redirect URL שמופיע בטופס ה-credential ב-n8n (`<N8N_URL>/rest/oauth2-credential/callback`).

## 5. ייבוא ה-workflows

```bash
python3 scripts/n8n_import.py
```

הסקריפט מחליף את ה-placeholders (`__AIRTABLE_BASE_ID__`, `__TBL_*__`, `__CRED_*__`, `__OWNER_*__`) בערכים מ-`.env`,
יוצר או מעדכן כל workflow לפי שם, מגדיר את WF0 כ-Error Workflow של כולם, מקשר את WF13 → WF1 → WF8 ומפעיל.
בהפעלה n8n רושם את ה-webhook של כל בוט בטלגרם (WF5, WF9) מול `N8N_WEBHOOK_URL`.

בלי API (n8n Cloud trial): `python3 scripts/n8n_import.py --render` כותב קבצים מלאים ל-`.local/rendered/`,
ומדביקים כל אחד בקנבס (Create workflow → Ctrl+V → Save → Settings → Error Workflow = WF0 → Publish).

> שיניתם את `N8N_WEBHOOK_URL`? מכבים ומדליקים את WF5 ו-WF9 כדי שטלגרם יקבל את הכתובת החדשה.
> כל בוט יכול להיות מחובר ל-Telegram Trigger אחד פעיל בלבד.

## 6. בסיס הידע (RAG)

פותחים ב-n8n את WF6 ואת WF7, בכל אחד את צומת ה-Form Trigger, ומעתיקים את ה-id מה-Production URL (החלק אחרי `/form/`)
ל-`FORM_POLICIES_ID` ול-`FORM_PRODUCTS_ID`. ואז:

```bash
python3 scripts/load_rag.py      # 12 מסמכי מדיניות + 34 מוצרים → vector store
python3 scripts/smoke_test.py
```

ה-vector store נשמר בזיכרון: אחרי כל `docker compose restart` או עדכון של n8n מריצים שוב `load_rag.py`.

## 7. אפליקציה ודף נחיתה

לפי [frontend-integration.md](frontend-integration.md): בונים ב-Lovable מ-`app/lovable-prompt.md` עם `<BASE>/webhook/app`,
ואת דף הנחיתה מ-`app/landing-prompt.md` עם `<BASE>/webhook/lead`.

## תחזוקה

| פעולה | פקודה |
|---|---|
| לוגים | `docker compose logs -f n8n` |
| עצירה (הנתונים נשמרים) | `docker compose --profile tunnel down` |
| עדכון n8n | `docker compose pull && docker compose --profile tunnel up -d`, ואז `load_rag.py` |
| גיבוי | `docker run --rm -v shlomi-erp_n8n_data:/d -v "$PWD":/b alpine tar czf /b/n8n-backup.tgz -C /d .` |
| מחיקה מלאה (כולל credentials) | `docker compose down -v` |

מכסות: רק WF3 ו-WF4 רצים לפי שעון (כל 3 שעות). כל השאר מופעל מאירוע, כך שבמנוחה אין קריאות ל-Gemini, Airtable או Gmail.
