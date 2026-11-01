#!/usr/bin/env python3
"""Fill the in-memory vector store: submits policies/*.md to WF6 and data/products.csv to WF7.

The vector store lives in n8n's memory and is wiped on every restart, so run this again whenever
the customer-service bot stops finding policy/product answers (and always before a demo).

Usage:  python3 scripts/load_rag.py
If the form submission is rejected, open the two form URLs in a browser and upload the files by hand.
"""
import glob
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, load_env, env, request  # noqa: E402

load_env()
N8N = env("N8N_URL").rstrip("/")
# n8n's Form Trigger (v2.6+) serves the form at /form/<trigger id>; the id is shown as the
# "Production URL" inside the trigger node. Put them in .env as FORM_POLICIES_ID / FORM_PRODUCTS_ID.
FORM_POLICIES = env("FORM_POLICIES_ID", required=False, default="policies-upload")
FORM_PRODUCTS = env("FORM_PRODUCTS_ID", required=False, default="products-upload")


def multipart(files, field="field-0"):
    """Build a multipart/form-data body. files = [(filename, bytes, content_type)]."""
    boundary = "----Shlomierp" + uuid.uuid4().hex
    parts = []
    for fname, blob, ctype in files:
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{fname}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n".encode("utf-8") + blob + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def submit(path, files):
    body, ctype = multipart(files)
    status, data = request("POST", f"{N8N}/form/{path}", {"Content-Type": ctype}, data=body, timeout=300)
    ok = status in (200, 201)
    print(f"{'OK ' if ok else 'FAIL'} {path}: HTTP {status}" + ("" if ok else f" -> {str(data)[:300]}"))
    if not ok:
        print(f"     open {N8N}/form/{path} in a browser and upload the file(s) manually.")
    return ok


def main():
    policies = sorted(glob.glob(os.path.join(ROOT, "policies", "*.md")))
    pol_files = [(os.path.basename(p), open(p, "rb").read(), "text/markdown") for p in policies]
    print(f"Uploading {len(pol_files)} policy files to WF6 ...")
    submit(FORM_POLICIES, pol_files)

    csv_path = os.path.join(ROOT, "data", "products.csv")
    print("Uploading products.csv to WF7 ...")
    submit(FORM_PRODUCTS, [("products.csv", open(csv_path, "rb").read(), "text/csv")])

    print("\nCheck n8n > Executions: both runs should be green. Then ask the support bot a policy question.")


if __name__ == "__main__":
    main()

