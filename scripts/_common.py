"""Shared helpers for the setup scripts. Standard library only (Python 3.9+)."""
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DIR = os.path.join(ROOT, ".local")


def load_env():
    """Load KEY=VALUE lines from <repo>/.env into os.environ (without overriding)."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        die(".env not found. Copy .env.example to .env and fill it in.")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def env(key, required=True, default=None):
    v = os.environ.get(key, default)
    if required and not v:
        die(f"Missing {key} in .env")
    return v


def die(msg):
    print("ERROR:", msg, file=sys.stderr)
    sys.exit(1)


def request(method, url, headers=None, body=None, data=None, timeout=60):
    """Small JSON HTTP helper. Returns (status, parsed-json-or-text)."""
    headers = dict(headers or {})
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif data is not None:
        payload = data
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = e.code
    try:
        return status, json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return status, raw


def local_read(name, default=None):
    path = os.path.join(LOCAL_DIR, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def local_write(name, data):
    os.makedirs(LOCAL_DIR, exist_ok=True)
    with open(os.path.join(LOCAL_DIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def plus_address(email, tag):
    """user@gmail.com + 'lead1' -> user+lead1@gmail.com (lands in the same inbox)."""
    local, _, domain = email.partition("@")
    return f"{local}+{tag}@{domain}"
