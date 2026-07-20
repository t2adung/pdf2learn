# -*- coding: utf-8 -*-
"""utils.py — BẢN DỰNG LẠI CHO SANDBOX TEST (file gốc không có trong bộ upload).
Nếu repo của bạn đã có utils.py thì GIỮ BẢN GỐC, bỏ qua file này.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path


def log(msg: str):
    print(msg, flush=True)


def warn(msg: str):
    print(f"⚠️  {msg}", flush=True)


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def strip_diacritics(s: str) -> str:
    s = str(s).replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _slugify(s: str, max_len: int = 48) -> str:
    s = strip_diacritics(s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len].rstrip("-") or "x"


def module_slug(title: str) -> str:
    return _slugify(title, 32)


def topic_slug(mod_slug: str, title: str) -> str:
    return f"{mod_slug}-{_slugify(title, 48)}"


def uniquify(base: str, taken: set) -> str:
    slug, n = base, 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    taken.add(slug)
    return slug
