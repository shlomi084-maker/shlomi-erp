# Shlomi ERP — AI-ERP with n8n (Graduation Project)

A small, no-code ERP for a fictional Israeli electronics retailer, **Shlomi Electronics (שלומי אלקטרוניקה)**, built on
**n8n Cloud** (automation, AI agents, RAG), **Airtable** (data) and a **Lovable** admin app.
Course brief: [`docs/final-project-spec.docx`](docs/final-project-spec.docx).

> מערכת ניהול עסק קטנה לחנות אלקטרוניקה ישראלית דמיונית: לידים נכנסים ומקבלים מייל אישי, לקוחות מקבלים
> תשובות מבוט טלגרם שמעוגן במדיניות ובקטלוג (RAG), חשבוניות מקבלות מע"מ ומספר עוקב ומופקות כמסמך לדרייב,
> ובעל העסק שואל בוט פרטי "מה ההכנסות?". אפס קוד: כל הלוגיקה בצמתים מוכנים של n8n.

> **Project status:** submitted and graded (September 2026). The live demo (self-hosted n8n, Airtable base, Lovable apps, Telegram bots) was shut down after grading, so there are no live URLs. Everything needed to rebuild it is in this repo: `scripts/` recreate the Airtable base and import the workflows, `app/` holds the Lovable prompts, and the screenshots below show the running system.

## Three layers, one data model

| Layer | Where | Role |
|---|---|---|
| Data | Airtable | 6 tables (`Invoices`, `Leads`, `Customers`, `Orders`, `Products`, `Tasks`) — single source of truth |
| Logic | n8n Cloud | 10 workflows + 1 error handler, 3 AI agents, in-memory vector store (RAG) |
| UI | Lovable | Admin app: dashboard, customers, leads, orders, invoices, products, tasks, chat — talks to n8n through **one** webhook. Plus a demo landing page whose lead form posts to WF2. |

```
 website / app form ──POST──▶ WF2 Leads Intake ──▶ Airtable.Leads ──▶ WF3 Cold Email (every 3h) ──▶ Gmail
                                                        ▲                                            │
                                                        └──── WF4 Reply Check (every 30m) ◀── Gmail ◀┘
 customer ──Telegram bot #2──▶ WF5 Customer-Service Agent ◀── RAG (WF6 policies, WF7 products)
 owner    ──Telegram bot #1──▶ WF9 Manager Agent ◀── Summarize(Airtable.Invoices)
 app ──POST /webhook/app──▶ WF13 App API ──▶ Airtable (read / create / update) + chat agent
 app (new invoice) ──▶ WF13 ──▶ WF1 Tax Validation (VAT, numbering) ──▶ WF8 Invoice Maker ──▶ Google Drive
 any failure ──▶ WF0 Error Handler ──▶ Telegram to owner
```

## The workflows

| # | Workflow | Trigger | What it does | Local error handling |
|---|---|---|---|---|
| 0 | [Error Handler](workflows/00-error-handler.json) | Error Trigger | Telegram alert to the owner with workflow, node, error and link. Set as *Error Workflow* on every other workflow. | — |
| 1 | [Tax Validation](workflows/01-tax-validation.json) | Called by WF13 when the app creates an invoice (Execute Workflow) | Validates, computes VAT 18% (17% before 2025), running number `INV-0001`, marks `Ready` | Invalid invoice → `Status=Invalid` |
| 2 | [Leads Intake](workflows/02-leads-intake.json) | `POST /webhook/lead` | Dedupe by email, create lead, email alert to owner, JSON response | No email → HTTP 400; Gmail failure doesn't block |
| 3 | [Sales Cold Emails](workflows/03-sales-cold-emails.json) | Every 3 h | One `New` lead per run → LLM writes a Hebrew cold email → Gmail → `Contacted` | Send failure → `Status=EmailFailed` |
| 4 | [Sales Reply Check](workflows/04-sales-reply-check.json) | Every 3 h | Unread inbox → mark read → sender email → matching `Contacted` lead → `Replied` + Telegram alert | Mark-read failure doesn't stop the check; non-lead mail stops quietly |
| 5 | [Customer Service Agent](workflows/05-customer-service-agent.json) | Telegram bot #2 | RAG agent: answers only from policy + product vector stores, per-chat memory | Agent error → polite fallback message |
| 6 | [Policies → Vector Store](workflows/06-policies-to-vector-store.json) | Form upload (`/form/<trigger id>`, manual) | `policies/*.md` → chunks → Gemini embeddings → memory key `mypolicies` | — |
| 7 | [Products → Vector Store](workflows/07-products-to-vector-store.json) | Form upload (`/form/<trigger id>`, manual) | `data/products.csv` → one doc per row → memory key `theproducts` | — |
| 8 | [Invoice Maker](workflows/08-invoice-maker.json) | Called by WF1 once the invoice is `Ready` (Execute Workflow) | `Ready` invoices → Hebrew RTL HTML (doc type: חשבונית מס / קבלה / חשבונית) → file → Google Drive → `PdfUrl`, `Issued` | Drive upload failure → `Status=UploadFailed` |
| 9 | [Manager Agent](workflows/09-manager-agent.json) | Telegram bot #1 | Owner-only (chat-id gate) → Summarize invoices by status → agent phrases the answer | Non-owner → refusal; model error → message |
| 13 | [App API](workflows/13-app-api.json) | `POST /webhook/app` | `{action: read\|create\|update\|chat, table, payload, filter, message}` | Unknown action → 400; chat error → reply |

Numbers 10–12 are intentionally unused (the brief keeps numbering stable). Every node has a Hebrew sticky note
explaining what it does, so the n8n canvas is self-documenting.

## Data model (Airtable)

| Table | Fields |
|---|---|
| Invoices | `InvoiceNumber` · `CustomerId` · `Amount` · `VatAmount` · `Total` · `Status` (Ready → Issued → Paid / Invalid / UploadFailed) · `PdfUrl` · `DocType` (חשבונית מס / קבלה / חשבונית) · `Created` |
| Customers | `CustomerId` · `Name` · `Email` · `Phone` · `Company` · `Notes` · `Created` |
| Orders | `OrderId` · `CustomerId` · `Product` · `Quantity` · `Total` · `Status` (New / Shipped / Delivered) · `Created` |
| Leads | `Name` · `Email` · `Phone` · `Company` · `Interest` · `Status` (New → Contacted → Replied / EmailFailed) · `Created` |
| Products | `Name` · `Category` · `Price` · `Description` · `InStock` |
| Tasks | `Title` · `Status` · `Notes` · `Created` |

`Created` must be a *Created time* field (WF1 uses it for the VAT-rate date, WF3 for lead age). `Status` is plain text, not single-select,
so workflows can write new values freely. Foreign keys are plain text (`CUST-0001`). Details: [docs/airtable-schema.md](docs/airtable-schema.md).

## RAG knowledge base

- [`policies/`](policies/) — 12 documents: returns, warranty, shipping, pricing, payments, Israeli VAT & invoice rules,
  agent guardrails, service tone, sales playbook, manager brief, business overview, FAQ.
- [`data/products.csv`](data/products.csv) — 34 products with full Hebrew specs.

Both are embedded with Gemini `gemini-embedding-001` into n8n's in-memory vector store. The customer-service agent gets
them as two tools and is instructed to answer **only** from retrieved text.

## Setup (from zero to running)

Full step-by-step guide (Docker, Airtable, Telegram bots, credentials, import, RAG, Lovable):
[docs/setup-guide.md](docs/setup-guide.md). App endpoints: [docs/frontend-integration.md](docs/frontend-integration.md).

**Local n8n in Docker** (instead of n8n Cloud): set `N8N_ENCRYPTION_KEY` (and for Telegram/Lovable the tunnel
variables) in `.env`, then `docker compose --profile tunnel up -d` and use the tunnel URL as `N8N_URL`.
See [`docker-compose.yml`](docker-compose.yml).

Accounts: n8n Cloud (or local Docker), Airtable, Google AI Studio (Gemini API key), two Telegram bots (BotFather), a Google account (Gmail + Drive), Lovable.

1. In n8n create 6 credentials: Google Gemini, Airtable token, Telegram (manager bot), Telegram (support bot), Gmail OAuth, Google Drive OAuth.
2. `cp .env.example .env` and fill it in (n8n URL, Airtable PAT + base id, your Telegram chat id, the 6 credential ids).
   The n8n public API is disabled on the Cloud trial, so `n8n_import.py --render` writes filled JSON files to `.local/rendered/`
   that you paste into the n8n canvas (Create workflow → paste → Save → Settings → Error Workflow → Publish). With an API key,
   `n8n_import.py` does all of that itself.
3. Create tables + seed demo data, import and activate all workflows, fill the vector store, verify:

```bash
python3 scripts/airtable_setup.py
python3 scripts/n8n_import.py          # or: --render, then paste by hand
python3 scripts/load_rag.py            # needs FORM_POLICIES_ID / FORM_PRODUCTS_ID in .env
python3 scripts/smoke_test.py
```

4. Build the admin app in Lovable with [`app/lovable-prompt.md`](app/lovable-prompt.md) and the `/webhook/app` URL, then Publish.
5. Optional: build the demo landing page as a separate Lovable project with [`app/landing-prompt.md`](app/landing-prompt.md) and the `/webhook/lead` URL.

Workflow JSON files contain placeholders (`__AIRTABLE_BASE_ID__`, `__CRED_GEMINI__`, …) that the import script
substitutes, so the repository holds **no ids and no secrets**. They can also be pasted into the n8n canvas by hand;
then pick your base, tables and credentials in each node.

## Screenshots

**Admin app and landing page (Lovable)** — built separately in Lovable from the prompts in [`app/`](app/);
the connection details are in [docs/frontend-integration.md](docs/frontend-integration.md). Screenshots of the
Shlomi ERP app go here once it is built.

**Telegram bots**

| Customer-service bot (RAG: returns policy, ANC headphones) | Guardrail: refuses a discount | Manager bot (revenue, debt) |
|---|---|---|
| ![support](docs/images/telegram-support-bot.png) | ![discount](docs/images/telegram-support-bot-discount.png) | ![manager](docs/images/telegram-manager-bot.png) |

**n8n workflows** (every node carries a Hebrew sticky note)

| | |
|---|---|
| WF0 Error Handler ![wf0](docs/images/n8n-00-error-handler.jpg) | WF1 Tax Validation ![wf1](docs/images/n8n-01-tax-validation.jpg) |
| WF2 Leads Intake ![wf2](docs/images/n8n-02-leads-intake.jpg) | WF3 Sales Cold Emails ![wf3](docs/images/n8n-03-sales-cold-emails.jpg) |
| WF4 Sales Reply Check ![wf4](docs/images/n8n-04-sales-reply-check.jpg) | WF5 Customer Service Agent ![wf5](docs/images/n8n-05-customer-service-agent.jpg) |
| WF6 Policies → Vector Store ![wf6](docs/images/n8n-06-policies-to-vector-store.jpg) | WF7 Products → Vector Store ![wf7](docs/images/n8n-07-products-to-vector-store.jpg) |
| WF8 Invoice Maker ![wf8](docs/images/n8n-08-invoice-maker.jpg) | WF9 Manager Agent ![wf9](docs/images/n8n-09-manager-agent.jpg) |
| WF13 App API ![wf13](docs/images/n8n-13-app-api.jpg) | |

## Demo

See [docs/demo-script.md](docs/demo-script.md) for the 7-minute walkthrough and [docs/exam-qa.md](docs/exam-qa.md)
for likely questions. Before a demo run `load_rag.py` (the vector store is in memory) and `smoke_test.py`.

## Known limitations (by design, for simplicity)

- The vector store and agent memory live in n8n's memory and reset on restart → re-run WF6 + WF7 (`load_rag.py`).
- Invoices are HTML documents in Drive; PDF is one manual click (open with Google Docs → download as PDF).
- Running invoice numbers can collide if two invoices are created in the same polling minute.
- Nothing runs on a clock except WF3/WF4 (every 3 h). Invoices are processed as an event chain, app → WF13 → WF1 → WF8, instead of the course sample's per-minute polling: zero API calls when idle, a document within seconds, and no running-number collisions because invoices are processed one at a time. The trade-off: an invoice typed directly into Airtable is not picked up; create it from the app.
- The manager agent is read-only, has no tools, and sees at most 100 invoices.
- WF3 emails one lead per run so a mistake can never mass-mail.
- The app is single-user; the webhook URL is a front-end constant. The Airtable token never reaches the browser
  (all writes go through n8n), which is the rule the brief insists on.

## Layout

```
workflows/     11 n8n workflow exports (placeholders instead of ids; safe to commit)
policies/      RAG source: company policies (Hebrew) + agent instructions (English)
data/          products.csv + seed records for the demo
scripts/       airtable_setup.py · n8n_import.py · load_rag.py · smoke_test.py
app/           Lovable build prompts (admin app, demo landing page)
docs/          architecture, schema, VAT rules, demo script, exam Q&A, screenshots, course brief
```

