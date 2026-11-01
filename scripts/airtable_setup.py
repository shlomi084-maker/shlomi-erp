#!/usr/bin/env python3
"""Create the 6 Airtable tables the workflows need, and seed demo data.

Idempotent: existing tables are reused, tables that already contain records are not re-seeded.
Writes the table IDs to .local/airtable_tables.json for n8n_import.py.

Usage:  python3 scripts/airtable_setup.py
"""
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, load_env, env, request, local_write, plus_address, die  # noqa: E402

load_env()
PAT = env("AIRTABLE_PAT")
BASE = env("AIRTABLE_BASE_ID")
OWNER_EMAIL = env("OWNER_EMAIL")
H = {"Authorization": f"Bearer {PAT}"}
META = f"https://api.airtable.com/v0/meta/bases/{BASE}/tables"
VAT = 0.18


def created_time():
    return {"name": "Created", "type": "createdTime",
            "options": {"result": {"type": "dateTime", "options": {
                "dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}, "timeZone": "Asia/Jerusalem"}}}}


def last_modified():
    # Airtable "Last modified time"; WF8's Airtable Trigger polls this field so it fires only when an invoice changes.
    return {"name": "StatusChanged", "type": "lastModifiedTime",
            "options": {"result": {"type": "dateTime", "options": {
                "dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}, "timeZone": "Asia/Jerusalem"}}}}


def text(name):
    return {"name": name, "type": "singleLineText"}


def number(name, precision=2):
    return {"name": name, "type": "number", "options": {"precision": precision}}


TABLES = {
    "Invoices": [text("InvoiceNumber"), text("CustomerId"), number("Amount"), number("VatAmount"),
                 number("Total"), text("Status"), {"name": "PdfUrl", "type": "url"}, text("DocType"), created_time()],
    "Customers": [text("CustomerId"), text("Name"), {"name": "Email", "type": "email"}, {"name": "Phone", "type": "phoneNumber"},
                  text("Company"), {"name": "Notes", "type": "multilineText"}, created_time()],
    "Orders": [text("OrderId"), text("CustomerId"), text("Product"), number("Quantity", 0), number("Total"),
               text("Status"), created_time()],
    "Leads": [text("Name"), {"name": "Email", "type": "email"}, {"name": "Phone", "type": "phoneNumber"},
              text("Company"), text("Interest"), text("Status"), created_time()],
    "Products": [text("Name"), text("Category"), number("Price", 0),
                 {"name": "Description", "type": "multilineText"},
                 {"name": "InStock", "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}}],
    "Tasks": [text("Title"), text("Status"), {"name": "Notes", "type": "multilineText"}, created_time()],
}


def existing_tables():
    status, data = request("GET", META, H)
    if status != 200:
        die(f"Cannot read base schema ({status}): {data}. Check AIRTABLE_PAT scopes (schema.bases:read) and AIRTABLE_BASE_ID.")
    return {t["name"]: t for t in data["tables"]}


def create_table(name, fields):
    """Airtable refuses createdTime/lastModifiedTime fields at table creation; create the table, then add them."""
    computed = ("createdTime", "lastModifiedTime")
    base_fields = [f for f in fields if f["type"] not in computed]
    status, data = request("POST", META, H, {"name": name, "fields": base_fields})
    if status != 200:
        die(f"Cannot create table {name} ({status}): {data}")
    for f in fields:
        if f["type"] in computed:
            add_field(data["id"], name, f)
    return data


def add_field(table_id, table_name, field):
    url = f"{META}/{table_id}/fields"
    status, data = request("POST", url, H, field)
    if status != 200:  # retry without options
        status, data = request("POST", url, H, {"name": field["name"], "type": field["type"]})
    if status != 200:
        die(f"Cannot add field {field['name']} to {table_name} ({status}): {data}")


def count_records(table):
    status, data = request("GET", f"https://api.airtable.com/v0/{BASE}/{table}?maxRecords=1", H)
    if status != 200:
        die(f"Cannot read {table} ({status}): {data}")
    return len(data.get("records", []))


def insert(table, rows):
    for i in range(0, len(rows), 10):
        batch = [{"fields": r} for r in rows[i:i + 10]]
        status, data = request("POST", f"https://api.airtable.com/v0/{BASE}/{table}", H,
                               {"records": batch, "typecast": True})
        if status != 200:
            die(f"Insert into {table} failed ({status}): {data}")
        time.sleep(0.25)  # stay under 5 req/s
    print(f"  seeded {len(rows)} records into {table}")


def seed_products():
    rows = []
    with open(os.path.join(ROOT, "data", "products.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"Name": r["Name"], "Category": r["Category"], "Price": float(r["Price"]),
                         "Description": r["Description"],
                         "InStock": str(r["InStock"]).strip().lower() in ("checked", "true", "1", "yes")})
    return rows


def seed_from_json(name):
    with open(os.path.join(ROOT, "data", "seed", name), encoding="utf-8") as f:
        rows = json.load(f)
    for r in rows:
        for k, v in list(r.items()):
            if isinstance(v, str) and v.startswith("__OWNER_EMAIL_PLUS__"):
                r[k] = plus_address(OWNER_EMAIL, v.replace("__OWNER_EMAIL_PLUS__", ""))
    return rows


def seed_invoices():
    rows = seed_from_json("invoices.json")
    for r in rows:
        amt = float(r["Amount"])
        r["VatAmount"] = round(amt * VAT, 2)
        r["Total"] = round(amt + r["VatAmount"], 2)
    return rows


def main():
    print(f"Base {BASE}")
    have = existing_tables()
    ids = {}
    for name, fields in TABLES.items():
        if name in have:
            print(f"- {name}: exists ({have[name]['id']})")
            ids[name] = have[name]["id"]
            missing = {f["name"] for f in fields} - {f["name"] for f in have[name]["fields"]}
            for f in fields:
                if f["name"] in missing:
                    add_field(have[name]["id"], name, f)
                    print(f"  added field {f['name']}")
        else:
            t = create_table(name, fields)
            ids[name] = t["id"]
            print(f"- {name}: created ({t['id']})")

    print("Seeding demo data (skipped for tables that already have records):")
    seeds = {"Products": seed_products, "Leads": lambda: seed_from_json("leads.json"),
             "Invoices": seed_invoices, "Tasks": lambda: seed_from_json("tasks.json"),
             "Customers": lambda: seed_from_json("customers.json"), "Orders": lambda: seed_from_json("orders.json")}
    for table, fn in seeds.items():
        if count_records(table):
            print(f"  {table}: already has data, skipped")
        else:
            insert(table, fn())

    local_write("airtable_tables.json", ids)
    print("\nTable IDs saved to .local/airtable_tables.json")
    print("Next: python3 scripts/n8n_import.py")


if __name__ == "__main__":
    main()
