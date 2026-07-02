# -*- coding: utf-8 -*-
"""Tiện ích chung: slugify tiếng Việt, đọc/ghi JSON, log."""
import json
import re
import sys
import unicodedata
from pathlib import Path

ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}


def roman_to_int(s: str) -> int:
    s = s.lower()
    total, prev = 0, 0
    for ch in reversed(s):
        val = ROMAN.get(ch, 0)
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total


def strip_diacritics(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def slugify(text: str, max_len: int = 60) -> str:
    text = strip_diacritics(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "untitled"


def module_slug(title: str) -> str:
    """'Chương I – Mở đầu' -> 'chuong-1'; 'Chương 2 ...' -> 'chuong-2';
    fallback: slugify toàn bộ title."""
    m = re.match(r"\s*(chương|chuong|chapter|phần|phan|part)\s+([IVXLCivxlc]+|\d+)\b",
                 strip_diacritics(title), re.IGNORECASE)
    if m:
        kw = slugify(m.group(1))
        num = m.group(2)
        n = int(num) if num.isdigit() else roman_to_int(num)
        if n > 0:
            return f"{kw}-{n}"
    return slugify(title, max_len=40)


def topic_slug(mod_slug: str, title: str) -> str:
    """'Bài 1. Giới thiệu' + 'chuong-1' -> 'chuong-1-bai-1';
    fallback: mod_slug + slug title rút gọn."""
    m = re.match(r"\s*(bài|bai|lesson|unit|mục|muc)\s+(\d+)\b",
                 strip_diacritics(title), re.IGNORECASE)
    if m:
        return f"{mod_slug}-{slugify(m.group(1))}-{int(m.group(2))}"
    return f"{mod_slug}-{slugify(title, max_len=40)}"


def uniquify(slug: str, taken: set) -> str:
    if slug not in taken:
        taken.add(slug)
        return slug
    i = 2
    while f"{slug}-{i}" in taken:
        i += 1
    s = f"{slug}-{i}"
    taken.add(s)
    return s


def load_json(path: Path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log(msg: str):
    print(msg, flush=True)


def warn(msg: str):
    print(f"⚠️  {msg}", file=sys.stderr, flush=True)
