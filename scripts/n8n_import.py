#!/usr/bin/env python3
"""Import (or update) all workflows into n8n via the public REST API, wire the error workflow, activate.

Reads placeholders from .env and .local/airtable_tables.json, substitutes them into workflows/*.json,
creates or updates each workflow by name, points every workflow at the Error Handler, and activates them.
Safe to re-run: existing workflows (matched by name) are updated in place.

Usage:  python3 scripts/n8n_import.py [--no-activate] [--only=13]   # --only limits to matching file names
        python3 scripts/n8n_import.py --render     # no API (e.g. n8n Cloud trial): write filled JSON files to
                                                   # .local/rendered/ for pasting into the n8n canvas by hand
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, load_env, env, request, local_read, local_write, die  # noqa: E402

load_env()
RENDER = "--render" in sys.argv
N8N = env("N8N_URL").rstrip("/")
H = {"X-N8N-API-KEY": env("N8N_API_KEY", required=not RENDER, default="")}
API = f"{N8N}/api/v1"
tables = local_read("airtable_tables.json")
if not tables:
    die("Run scripts/airtable_setup.py first (needs .local/airtable_tables.json)")

SUBS = {
    "__AIRTABLE_BASE_ID__": env("AIRTABLE_BASE_ID"),
    "__TBL_INVOICES__": tables["Invoices"],
    "__TBL_LEADS__": tables["Leads"],
    "__TBL_PRODUCTS__": tables["Products"],
    "__TBL_TASKS__": tables["Tasks"],
    "__OWNER_TELEGRAM_CHAT_ID__": env("OWNER_TELEGRAM_CHAT_ID"),
    "__OWNER_EMAIL__": env("OWNER_EMAIL"),
    "__CRED_GEMINI__": env("CRED_GEMINI"),
    "__CRED_AIRTABLE__": env("CRED_AIRTABLE"),
    "__CRED_TELEGRAM_MANAGER__": env("CRED_TELEGRAM_MANAGER"),
    "__CRED_TELEGRAM_SUPPORT__": env("CRED_TELEGRAM_SUPPORT"),
    "__CRED_GMAIL__": env("CRED_GMAIL"),
    "__CRED_GDRIVE__": env("CRED_GDRIVE"),
}
ACTIVATE = "--no-activate" not in sys.argv
# WF13 calls WF1 and WF1 calls WF8 (Execute Workflow). Their ids are only known after creation,
# so files that reference them are imported twice on a fresh instance.
WF_REFS = {"__WF_ID_01__": "Shlomi ERP - 01 - Tax Validation", "__WF_ID_08__": "Shlomi ERP - 08 - Invoice Maker"}
# n8n refuses to publish a workflow that calls an unpublished sub-workflow, so import order matters:
# WF8 first, then WF1 (calls WF8), then everything else (WF13 calls WF1).
IMPORT_FIRST = ["08-", "01-"]


def refresh_wf_refs(existing, ids):
    for ph, name in WF_REFS.items():
        SUBS[ph] = ids.get(name) or existing.get(name, {}).get("id") or "PENDING"
PACE = 5  # seconds between API calls that touch external providers


def existing_by_name():
    out, cursor = {}, None
    while True:
        url = f"{API}/workflows?limit=250" + (f"&cursor={cursor}" if cursor else "")
        status, data = request("GET", url, H)
        if status != 200:
            die(f"Cannot list workflows ({status}): {data}. Check N8N_URL / N8N_API_KEY.")
        for w in data.get("data", []):
            out[w["name"]] = w
        cursor = data.get("nextCursor")
        if not cursor:
            return out


def check_credentials(files):
    """Make sure every __CRED_*__ id from .env exists in n8n with the type the workflows expect.

    Re-creating a credential in the n8n UI (e.g. reconnecting Google OAuth) gives it a new id, and nodes that
    still point at the old id fail at run time ("Credential with ID ... does not exist"). If the .env id is
    stale and n8n holds exactly one credential of the right type, use that one; otherwise stop with a list.
    """
    wanted = {}  # placeholder -> credential type, read from the workflow files themselves
    for path in files:
        for node in json.load(open(path, encoding="utf-8"))["nodes"]:
            for ctype, cred in (node.get("credentials") or {}).items():
                if cred.get("id") in SUBS:
                    wanted[cred["id"]] = ctype
    creds, cursor = [], None
    while True:
        status, data = request("GET", f"{API}/credentials?limit=250" + (f"&cursor={cursor}" if cursor else ""), H)
        if status != 200:
            print(f"WARNING cannot list credentials ({status}); skipping the credential id check")
            return
        creds += data.get("data", [])
        cursor = data.get("nextCursor")
        if not cursor:
            break
    for ph, ctype in sorted(wanted.items()):
        if any(c["id"] == SUBS[ph] and c["type"] == ctype for c in creds):
            continue
        same_type = [c for c in creds if c["type"] == ctype]
        key = ph.strip("_")
        if len(same_type) == 1:
            c = same_type[0]
            print(f"NOTE {key}={SUBS[ph]} is not a {ctype} credential in n8n; using '{c['name']}' ({c['id']}). "
                  f"Put {key}={c['id']} in .env.")
            SUBS[ph] = c["id"]
        else:
            listing = "; ".join(f"{c['id']} '{c['name']}'" for c in same_type) or "none - create it in n8n first"
            die(f"{key}={SUBS[ph]} is not a {ctype} credential in n8n. Set {key} in .env to one of: {listing}")


def load(path):
    raw = open(path, encoding="utf-8").read()
    for k, v in SUBS.items():
        raw = raw.replace(k, str(v))
    left = [k for k in SUBS if k in raw]
    if left:
        die(f"{path}: unreplaced placeholders {left}")
    return json.loads(raw)


def upsert(wf, existing, error_wf_id=None):
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": {"executionOrder": "v1"}}
    if error_wf_id:
        body["settings"]["errorWorkflow"] = error_wf_id
    if wf["name"] in existing:
        wid = existing[wf["name"]]["id"]
        status, data = request("PUT", f"{API}/workflows/{wid}", H, body)
        verb = "updated"
    else:
        status, data = request("POST", f"{API}/workflows", H, body)
        verb = "created"
    if status not in (200, 201):
        die(f"{wf['name']}: {verb} failed ({status}): {data}")
    return data["id"], verb


def set_active(wid, name, active):
    status, data = request("POST", f"{API}/workflows/{wid}/{'activate' if active else 'deactivate'}", H)
    if status != 200:
        print(f"  WARNING could not {'activate' if active else 'deactivate'} {name} ({status}): "
              f"{data if isinstance(data, str) else data.get('message', data)}")
        return False
    return True


def render():
    out = os.path.join(ROOT, ".local", "rendered")
    os.makedirs(out, exist_ok=True)
    for path in sorted(glob.glob(os.path.join(ROOT, "workflows", "*.json"))):
        wf = load(path)
        with open(os.path.join(out, os.path.basename(path)), "w", encoding="utf-8") as f:
            json.dump({"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
                       "settings": {"executionOrder": "v1"}}, f, ensure_ascii=False, indent=2)
        print("rendered", os.path.basename(path))
    print(f"\nFilled workflows are in {out}. In n8n: Create Workflow -> paste the file contents on the canvas -> Save.")
    print("Then set Settings -> Error Workflow = 'Shlomi ERP - 00 - Error Handler' on each, and activate.")


def main():
    if RENDER:
        return render()
    files = sorted(glob.glob(os.path.join(ROOT, "workflows", "*.json")))
    files.sort(key=lambda f: next((i for i, p in enumerate(IMPORT_FIRST) if os.path.basename(f).startswith(p)), 99))
    check_credentials(files)
    existing = existing_by_name()
    ids = {}

    # 1) error handler first, so the others can reference it
    err_path = [f for f in files if os.path.basename(f).startswith("00-")][0]
    err = load(err_path)
    err_id, verb = upsert(err, existing)
    ids[err["name"]] = err_id
    print(f"{verb}: {err['name']} ({err_id})")

    # 2) everything else, pointing at the error handler
    only = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")]  # e.g. --only=13
    pending = []
    for path in files:
        if path == err_path or (only and not any(o in os.path.basename(path) for o in only)):
            continue
        refresh_wf_refs(existing, ids)
        raw = open(path, encoding="utf-8").read()
        needs_ids = any(ph in raw for ph in WF_REFS)
        wf = load(path)
        wid, verb = upsert(wf, existing, error_wf_id=err_id)
        ids[wf["name"]] = wid
        print(f"{verb}: {wf['name']} ({wid})")
        if needs_ids and "PENDING" in json.dumps(wf):
            pending.append(path)  # second pass below, once the referenced ids exist
            continue
        if ACTIVATE:
            # re-activate so n8n re-registers webhooks/polling with the new version.
            # Pace it: every (de)activation of a Telegram workflow calls Telegram's setWebhook, and
            # Telegram rate-limits that; keep a wide margin so we never hit any provider's limit.
            if wf["name"] in existing and existing[wf["name"]].get("active"):
                set_active(wid, wf["name"], False)
                time.sleep(PACE)
            if set_active(wid, wf["name"], True):
                print("  active")
            time.sleep(PACE)

    for path in pending:
        refresh_wf_refs(existing, ids)
        wf = load(path)
        wid, verb = upsert(wf, existing, error_wf_id=err_id)
        print(f"{verb} (2nd pass, ids resolved): {wf['name']} ({wid})")
        if ACTIVATE and set_active(wid, wf["name"], True):
            print("  active")
        time.sleep(PACE)

    local_write("n8n_workflows.json", {**(local_read("n8n_workflows.json") or {}), **ids})
    print("\nEndpoints:")
    print(f"  Leads webhook (WF2):     POST {N8N}/webhook/lead")
    print(f"  App API (WF13):          POST {N8N}/webhook/app")
    print(f"  Policies upload (WF6):   {N8N}/form/policies-upload")
    print(f"  Products upload (WF7):   {N8N}/form/products-upload")
    print("\nNext: python3 scripts/load_rag.py   (fills the vector store), then python3 scripts/smoke_test.py")


if __name__ == "__main__":
    main()

