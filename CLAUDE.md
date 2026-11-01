# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Graduation project for a no-code course ("AI-ERP with n8n", John Bryce): a demo ERP for a fictional Israeli
electronics retailer, **Shlomi Electronics / שלומי אלקטרוניקה**. Deadline 2026-09-30, deliverable is this GitHub repo plus
a live demo in the exam. Quality bar is "convincing demo", not production. `PLAN.md` holds the step-by-step plan and
who does what; `README.md` is the public description.

There is no application code, build or test suite. The repo holds n8n workflow exports, the RAG source data, setup
scripts and docs. Everything runs in the cloud: n8n Cloud (or local Docker), Airtable, Google Gemini, Gmail, Google Drive, Telegram, Lovable.

Content is Hebrew (RTL): UI text, prompts, sticky notes, customer-facing policies, docs. Agent-instruction policies
(07–10) are English by design. Keep that split.

## Layout

- `workflows/*.json` — 11 n8n workflows (00 error handler, 01–09, 13). **They contain placeholders**
  (`__AIRTABLE_BASE_ID__`, `__TBL_*__`, `__CRED_*__`, `__OWNER_TELEGRAM_CHAT_ID__`, `__OWNER_EMAIL__`) that
  `scripts/n8n_import.py` substitutes from `.env` and `.local/airtable_tables.json`. Never commit real ids.
- `scripts/` — stdlib-only Python 3.9: `airtable_setup.py` (tables + seed) → `n8n_import.py` (upsert by name,
  wire error workflow, activate) → `load_rag.py` (submit policies + CSV to the two form triggers) → `smoke_test.py`.
  `_common.py` has the `.env` loader and HTTP helper. Run from anywhere; they resolve paths from `ROOT`.
- `policies/` (12 md files) and `data/products.csv` — the RAG corpus; also seeded into Airtable `Products`.
- `data/seed/*.json` — demo records. Emails use `__OWNER_EMAIL_PLUS__<tag>` → owner's Gmail with plus-addressing
  so cold emails and replies land in the owner's own inbox.
- `app/lovable-prompt.md` — the app is built in Lovable from this prompt; it only talks to WF13. No frontend code lives here.
- `docker-compose.yml` — optional local n8n (+ Cloudflare tunnel profile for Telegram/Lovable HTTPS). Reads `.env`.
  `docs/setup-guide.md` is the end-to-end setup, `docs/frontend-integration.md` the app/landing endpoint contract.
- `docs/` — architecture, schema, VAT, demo script, exam Q&A, screenshots, the course brief (`final-project-spec.docx`).
- `course-materials/` — gitignored. Lesson notes there contain a shared class MongoDB password; never copy it anywhere.

## Workflow conventions

- Vector store memory keys are `mypolicies` and `theproducts`; WF5's tools must match WF6/WF7. Embedding model
  `models/gemini-embedding-001`, chat model `models/gemini-3-flash-preview` (Google Gemini, credential `googlePalmApi` →
  `__CRED_GEMINI__`). Switched from OpenAI in Oct 2026; insert (WF6/WF7) and query (WF5) must use the same embedding model.
- Webhook paths are fixed: `/webhook/lead` (WF2), `/webhook/app` (WF13). Form Trigger v2.6 ignores `path` and serves
  `/form/<trigger id>`; the ids live in `.env` as `FORM_POLICIES_ID` / `FORM_PRODUCTS_ID` (read from the node's Production URL).
- n8n Cloud trial has no public API: `n8n_import.py --render` + paste via the browser pane was the actual import route
  (paste JSON onto the canvas with a synthetic paste event; `.click()` does not open element-plus selects, dispatch real mouse
  events or click by coordinates). Live workflow ids are in `.local/n8n_workflows.json`.
- Node versions must exist on the target n8n: the self-hosted server rejects Set v3.5 ("Cannot read properties of undefined (reading 'execute')" on activation), so Set nodes are v3.4. Probe with a throwaway workflow before bumping versions.
- Airtable nodes use resource-locator `mode: "id"` with placeholders; WF13 passes table *names* from the request body,
  which the Airtable API accepts.
- Status values are free text and part of the contract: Invoices `Ready → Issued → Paid | Invalid`,
  Leads `New → Contacted → Replied | EmailFailed`, Tasks `Open | Done`.
- Error handling is a graded requirement: keep WF0 as the global error workflow **and** a local error branch in every
  workflow (see the README table). Don't remove branches to "simplify".
- Every node gets a Hebrew sticky note; each workflow gets a title note. The examiner reads the canvas.
- VAT: 18% from 2025-01-01, 17% before, computed as numbers in WF1. Invoice numbers `INV-0001` from max existing.
- WF3 intentionally handles one lead per run (brief requirement).
- Keep workflows event-driven and frugal (the student's explicit requirement: never approach any provider's rate limit or quota).
  Invoices are a chain: WF13 `Is Invoice?` → Execute Workflow WF1 → Execute Workflow WF8 (`__WF_ID_01__` / `__WF_ID_08__`
  placeholders, resolved by `n8n_import.py` in a second pass). WF1/WF8 start with an Execute Workflow Trigger and are not
  activated. Only WF3/WF4 run on a clock (every 3 h). A per-minute schedule burned the n8n Cloud trial quota in a day.
- Pace anything that touches external APIs (activations call Telegram's setWebhook; the scripts sleep between calls).

## Editing workflows

Edit the JSON directly, keep node names stable (expressions reference them by name, e.g. `$('Lead Webhook')`),
then re-run `python3 scripts/n8n_import.py` which updates in place by workflow name. Validate connections reference
existing node names before importing. When exporting from n8n back into the repo, replace real ids with the placeholders.

## Business identity used across files

Shlomi Electronics, שלומי אלקטרוניקה, support@Shlomi-electronics.co.il, billing@Shlomi-electronics.co.il,
רחוב הברזל 30 תל אביב, 03-555-1234, עוסק מורשה 515000000. Keep consistent if you touch policies, prompts or the invoice template.

