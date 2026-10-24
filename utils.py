# -*- coding: utf-8 -*-
"""utils.py — BẢN DỰNG LẠI CHO SANDBOX TEST (file gốc không có trong bộ upload).
Nếu repo của bạn đã có utils.py thì GIỮ BẢN GỐC, bỏ qua file này.
"""
import json
import os
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


# .env của repo — cạnh utils.py, KHÔNG phụ thuộc thư mục đang đứng khi chạy script.
ENV_FILE = Path(__file__).resolve().with_name(".env")
# Biến mà giá trị trong .env THẮNG biến cùng tên đã có trong shell: tài khoản Claude
# riêng cho pdf2learn phải luôn là thư mục ghi trong .env.
ENV_OVERRIDE = ("CLAUDE_CONFIG_DIR",)


def _parse_env_file(path: Path) -> dict:
    """Đọc KEY=VALUE (bỏ dòng trống/#, tiền tố export, dấu nháy bao ngoài) — dùng khi
    chưa cài python-dotenv."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, val = line.split("=", 1)
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            val = val[1:-1]
        out[key.strip()] = val
    return out


def load_env(path=None) -> dict:
    """Nạp .env vào os.environ. Không ghi đè biến shell đã có, TRỪ ENV_OVERRIDE.
    Có python-dotenv thì dùng, không có thì tự đọc (không còn trường hợp lặng lẽ bỏ
    qua .env). Trả về các cặp đọc được từ file."""
    p = Path(path) if path else ENV_FILE
    if not p.is_file():
        return {}
    try:
        from dotenv import dotenv_values
        values = {k: v for k, v in dotenv_values(p).items() if v is not None}
    except ImportError:
        values = _parse_env_file(p)
    for key, val in values.items():
        if key in ENV_OVERRIDE:
            old = os.environ.get(key)
            if old is not None and old != val:
                warn(f"{key} trong shell ({old}) khác .env -> dùng giá trị trong .env ({val}).")
            os.environ[key] = val
        else:
            os.environ.setdefault(key, val)
    return values


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
