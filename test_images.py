# -*- coding: utf-8 -*-
"""test_images.py — Nghiệm thu "phần A": trích hình sách theo vùng + caption
thật + gán mục bằng code. Dựng PDF tổng hợp trong bộ nhớ, KHÔNG gọi API. 0 token.
Chạy: python3 test_images.py
"""
import os
import sys
import tempfile
from pathlib import Path

import fitz

from stage_images import (_caption_near, _content_words, _match_section,
                          _text_lines, generate_images_one)

fails = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def _noisy_png(w=300, h=220):
    """Ảnh nhiễu ngẫu nhiên -> PNG đủ lớn (>6KB) để qua ngưỡng MIN_BYTES."""
    pix = fitz.Pixmap(fitz.csRGB, w, h, os.urandom(w * h * 3), False)
    return pix.tobytes("png")


def _build_pdf(path):
    """1 trang A4: heading mục 1 (trên), 1 hình có caption 'Hình 1...' ngay dưới,
    và text của mục 2 ở cuối trang (xa hình)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Mục 1 — ngay phía trên hình
    page.insert_text((90, 120), "1. Cau tao nguyen tu", fontsize=14)
    page.insert_text((90, 140),
                     "Nguyen tu gom hat nhan mang dien duong va cac electron.",
                     fontsize=11)
    # Hình đặt tại vùng (90,150)-(390,370)
    rect = fitz.Rect(90, 150, 390, 370)
    page.insert_image(rect, stream=_noisy_png())
    # Caption THẬT ngay dưới hình
    page.insert_text((90, 386),
                     "Hinh 1. Mo hinh nguyen tu gom hat nhan va electron",
                     fontsize=11)
    # Mục 2 — cuối trang, xa hình
    page.insert_text((90, 720), "2. Bang tuan hoan cac nguyen to", fontsize=14)
    page.insert_text((90, 740),
                     "Sap xep nguyen to hoa hoc theo so proton tang dan.",
                     fontsize=11)
    doc.save(path)
    doc.close()


SECTIONS = [
    {"heading": "Cau tao nguyen tu",
     "points": ["Nguyen tu gom hat nhan va electron",
                "Hat nhan mang dien duong"]},
    {"heading": "Bang tuan hoan cac nguyen to",
     "points": ["Sap xep theo so proton", "Chu ki va nhom"]},
]

tmp = Path(tempfile.mkdtemp())
pdf_path = tmp / "syn.pdf"
_build_pdf(str(pdf_path))
doc = fitz.open(str(pdf_path))
page = doc[0]

# --- 1. dò caption thật ---
lines = _text_lines(page)
rect = None
for info in page.get_images(full=True):
    rs = page.get_image_rects(info[0])
    if rs:
        rect = rs[0]
cap = _caption_near(rect, lines) if rect else ""
check("lấy được caption THẬT bắt đầu bằng 'Hinh 1'", cap.lower().startswith("hinh 1"), repr(cap))

# --- 2. gán mục bằng code ---
si = _match_section(cap, "", SECTIONS)
check("caption khớp ĐÚNG mục 0 (Cau tao nguyen tu)", si == 0, f"section_index={si}")
si_wrong = _match_section("Hinh 2. Bang tuan hoan cac nguyen to hoa hoc", "", SECTIONS)
check("caption khác khớp mục 1 (Bang tuan hoan)", si_wrong == 1, f"section_index={si_wrong}")

# --- 3. end-to-end generate_images_one (book_images=True, 0 token) ---
row = {"topic_slug": "syn-bai-1", "topic_title": "Nguyen tu",
       "page_start": 1, "page_end": 1}
content_entry = {"sections": SECTIONS}   # không có mindmap -> chỉ có hình sách
imgs_dir = tmp / "images"
kept = generate_images_one(doc, row, content_entry, client=None,
                           images_dir=imgs_dir, book_images=True)
doc.close()

book = [k for k in kept if str(k.get("source", "")).startswith("pdf_page")]
check("trích được đúng 1 hình sách", len(book) == 1, f"{len(book)} hình")
if book:
    b = book[0]
    check("hình sách gắn source=pdf_page_1", b["source"] == "pdf_page_1", b["source"])
    check("hình sách gán vào mục 0", b.get("section_index") == 0, str(b.get("section_index")))
    check("caption hình sách là caption thật", b["caption"].lower().startswith("hinh 1"), b["caption"])
    check("file ảnh đã ghi ra đĩa", (imgs_dir / b["file"]).exists(), b["file"])
    check("ảnh render là PNG", b["file"].endswith(".png"), b["file"])

# --- 4. so khớp từ nội dung bỏ từ dừng ---
w = _content_words("Hình 1. Mô hình nguyên tử gồm hạt nhân")
check("_content_words bỏ từ dừng 'hình'/'của'", "hình" not in w and "nguyên" in w, str(sorted(w)))

print()
if fails:
    print(f"❌ {len(fails)} check thất bại: {fails}")
    sys.exit(1)
print("✅ Tất cả check đã qua. 0 token đã dùng.")
