# -*- coding: utf-8 -*-
"""test_images.py — Nghiệm thu: đính kèm NGUYÊN TRANG sách + gán mỗi trang vào
đúng mục nội dung bằng code. Dựng PDF tổng hợp trong bộ nhớ, KHÔNG gọi API. 0 token.
Chạy: python3 test_images.py
"""
import sys
import tempfile
from pathlib import Path

import fitz

from stage_images import _content_words, _match_section, generate_images_one

fails = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


SECTIONS = [
    {"heading": "Cau tao nguyen tu",
     "points": ["Nguyen tu gom hat nhan va electron",
                "Hat nhan mang dien duong"]},
    {"heading": "Bang tuan hoan cac nguyen to",
     "points": ["Sap xep theo so proton", "Chu ki va nhom"]},
]


def _build_pdf(path):
    """2 trang: trang 1 = nội dung mục 0, trang 2 = nội dung mục 1."""
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 100), "1. Cau tao nguyen tu", fontsize=16)
    p1.insert_text((72, 130),
                   "Nguyen tu gom hat nhan mang dien duong va cac electron.",
                   fontsize=12)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((72, 100), "2. Bang tuan hoan cac nguyen to", fontsize=16)
    p2.insert_text((72, 130),
                   "Sap xep nguyen to hoa hoc theo so proton, thanh chu ki va nhom.",
                   fontsize=12)
    doc.save(path)
    doc.close()


tmp = Path(tempfile.mkdtemp())
pdf_path = tmp / "syn.pdf"
_build_pdf(str(pdf_path))

# --- 1. khớp trang -> mục theo text ---
doc = fitz.open(str(pdf_path))
check("trang 1 khớp mục 0", _match_section(doc[0].get_text(), SECTIONS) == 0)
check("trang 2 khớp mục 1", _match_section(doc[1].get_text(), SECTIONS) == 1)
check("text rỗng (scan) -> -1 (sẽ fallback theo thứ tự)",
      _match_section("", SECTIONS) == -1)

# --- 2. end-to-end: đính NGUYÊN TRANG, gán đúng mục, 0 token ---
row = {"topic_slug": "syn-bai-1", "topic_title": "Nguyen tu",
       "page_start": 1, "page_end": 2}
imgs_dir = tmp / "images"
kept = generate_images_one(doc, row, {"sections": SECTIONS}, client=None,
                           images_dir=imgs_dir, book_images=True)
doc.close()

book = [k for k in kept if str(k.get("source", "")).startswith("pdf_page")]
check("đính đúng 2 trang sách", len(book) == 2, f"{len(book)} trang")
by_page = {k["source"]: k for k in book}
check("trang 1 -> mục 0", by_page.get("pdf_page_1", {}).get("section_index") == 0,
      str(by_page.get("pdf_page_1")))
check("trang 2 -> mục 1", by_page.get("pdf_page_2", {}).get("section_index") == 1,
      str(by_page.get("pdf_page_2")))
check("ảnh trang là PNG, đã ghi ra đĩa",
      all(k["file"].endswith(".png") and (imgs_dir / k["file"]).exists() for k in book))
check("caption ghi rõ số trang", by_page.get("pdf_page_1", {}).get("caption", "").startswith("Trang 1"))

# --- 3. sách scan (không text) -> fallback ánh xạ theo thứ tự trang ---
doc2 = fitz.open()
doc2.new_page(width=400, height=560)   # trang trắng, không text layer
doc2.new_page(width=400, height=560)
row2 = {"topic_slug": "scan-bai", "topic_title": "X", "page_start": 1, "page_end": 2}
kept2 = generate_images_one(doc2, row2, {"sections": SECTIONS}, client=None,
                            images_dir=tmp / "images2", book_images=True)
doc2.close()
book2 = [k for k in kept2 if str(k.get("source", "")).startswith("pdf_page")]
check("scan: vẫn đính đủ 2 trang", len(book2) == 2, f"{len(book2)} trang")
si2 = [k["section_index"] for k in sorted(book2, key=lambda k: k["source"])]
check("scan: ánh xạ theo thứ tự (trang1->mục0, trang2->mục1)", si2 == [0, 1], str(si2))

# --- 4. _content_words bỏ từ dừng ---
w = _content_words("Trang 1 - Hình nguyên tử của hạt nhân")
check("_content_words bỏ 'trang'/'hình'/'của'",
      "trang" not in w and "hình" not in w and "nguyên" in w, str(sorted(w)))

print()
if fails:
    print(f"❌ {len(fails)} check thất bại: {fails}")
    sys.exit(1)
print("✅ Tất cả check đã qua. 0 token đã dùng.")
