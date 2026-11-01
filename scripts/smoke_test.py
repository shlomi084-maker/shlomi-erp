#!/usr/bin/env python3
"""End-to-end smoke test of the live system. Run before every demo.

1. WF2  - posts a new lead, then the same lead again (expects created, then duplicate), then no email (400)
2. WF1+WF8 - creates an invoice in Airtable and waits for Ready -> Issued with a Drive link
3. WF1  - creates an invalid invoice (Amount 0) and expects Status = Invalid
4. WF13 - read / chat / unknown action
5. Lists failed n8n executions from the last run, if any

Usage:  python3 scripts/smoke_test.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import load_env, env, request, plus_address  # noqa: E402

load_env()
N8N = env("N8N_URL").rstrip("/")
N8N_KEY = env("N8N_API_KEY", required=False, default="")
NH = {"X-N8N-API-KEY": N8N_KEY}
PAT = env("AIRTABLE_PAT")
BASE = env("AIRTABLE_BASE_ID")
AH = {"Authorization": f"Bearer {PAT}"}
OWNER_EMAIL = env("OWNER_EMAIL")
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    return ok


def airtable_create(table, fields):
    status, data = request("POST", f"https://api.airtable.com/v0/{BASE}/{table}", AH,
                           {"records": [{"fields": fields}], "typecast": True})
    if status != 200:
        print("   airtable error", status, data)
        return None
    return data["records"][0]["id"]


def airtable_get(table, rid):
    status, data = request("GET", f"https://api.airtable.com/v0/{BASE}/{table}/{rid}", AH)
    return data.get("fields", {}) if status == 200 else {}


def wait_for(table, rid, predicate, timeout=200, every=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        f = airtable_get(table, rid)
        if predicate(f):
            return f
        print(f"     ... waiting ({int(time.time() - t0)}s) status={f.get('Status')}")
        time.sleep(every)
    return airtable_get(table, rid)


PACE = 3  # seconds between calls: stay far below every provider's rate limit


def paced(*a, **k):
    time.sleep(PACE)
    return request(*a, **k)


def main():
    tag = str(int(time.time()))[-6:]
    print("1) WF2 Leads intake")
    lead = {"name": f"בדיקה {tag}", "email": plus_address(OWNER_EMAIL, f"smoke{tag}"), "phone": "050-0000000",
            "company": "Smoke Test Ltd", "interest": "אוזניות לצוות"}
    s, d = paced("POST", f"{N8N}/webhook/lead", body=lead)
    check("new lead -> created", s == 200 and isinstance(d, dict) and d.get("created") is True, f"HTTP {s} {d}")
    s, d = paced("POST", f"{N8N}/webhook/lead", body=lead)
    check("same lead -> duplicate", s == 200 and isinstance(d, dict) and d.get("reason") == "duplicate", f"HTTP {s} {d}")
    s, d = paced("POST", f"{N8N}/webhook/lead", body={"name": "no email"})
    check("missing email -> 400", s == 400, f"HTTP {s}")

    print("2) WF1 -> WF8 invoice pipeline (event chain, usually under 30 seconds)")
    s, d = paced("POST", f"{N8N}/webhook/app", body={"action": "create", "table": "Invoices",
                                                        "payload": {"CustomerId": f"CUST-{tag}", "Amount": 1000}})
    rid = d.get("id") if isinstance(d, dict) else None
    if check("invoice created via app (WF13 -> WF1 -> WF8)", s == 200 and bool(rid), f"HTTP {s} {d}"):
        f = wait_for("Invoices", rid, lambda x: x.get("Status") == "Issued" and x.get("PdfUrl"))
        check("WF1 computed VAT + number",
              f.get("InvoiceNumber", "").startswith("INV-") and f.get("VatAmount") == 180 and f.get("Total") == 1180,
              f"{f.get('InvoiceNumber')} vat={f.get('VatAmount')} total={f.get('Total')}")
        check("WF8 issued document to Drive", f.get("Status") == "Issued" and bool(f.get("PdfUrl")),
              f"status={f.get('Status')} url={f.get('PdfUrl', '')[:60]}")

    print("3) WF1 invalid invoice")
    s, d = paced("POST", f"{N8N}/webhook/app", body={"action": "create", "table": "Invoices",
                                                        "payload": {"CustomerId": "", "Amount": 0}})
    rid = d.get("id") if isinstance(d, dict) else None
    if rid:
        f = wait_for("Invoices", rid, lambda x: x.get("Status") in ("Invalid", "Ready", "Issued"), timeout=120)
        check("invalid invoice -> Status Invalid", f.get("Status") == "Invalid", f"status={f.get('Status')}")

    print("4) WF13 App API")
    s, d = paced("POST", f"{N8N}/webhook/app", body={"action": "read", "table": "Leads", "limit": 5})
    check("read Leads", s == 200 and isinstance(d, dict) and isinstance(d.get("data"), list), f"HTTP {s} {str(d)[:120]}")
    s, d = paced("POST", f"{N8N}/webhook/app", body={"action": "chat", "message": "מה ההבדל בין סטטוס Ready ל-Issued בחשבונית?"}, timeout=120)
    check("chat reply", s == 200 and isinstance(d, dict) and bool(d.get("reply")), f"HTTP {s} {str(d)[:120]}")
    s, d = paced("POST", f"{N8N}/webhook/app", body={"action": "nope"})
    check("unknown action -> 400", s == 400, f"HTTP {s}")

    print("5) Failed executions in n8n (last 10)")
    if not N8N_KEY:
        print("     (no N8N_API_KEY - skipped; check n8n > Executions by hand)")
        s, d = 0, None
    else:
        s, d = request("GET", f"{N8N}/api/v1/executions?status=error&limit=10", NH)
    if s == 200 and isinstance(d, dict):
        errs = d.get("data", [])
        for e in errs:
            print(f"     workflow {e.get('workflowId')} execution {e.get('id')} at {e.get('startedAt')}")
        check("no failed executions", not errs, f"{len(errs)} failed")
    elif N8N_KEY:
        check("could list executions", False, f"HTTP {s}")

    passed = sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
