# -*- coding: utf-8 -*-
"""test_render.py — Nghiệm thu bước 1-2. Chạy: python3 test_render.py
KHÔNG gọi API, KHÔNG cần key. 0 token.
"""
import csv
import io
import sys

from mindmap_svg import to_mermaid, to_svg, _validate
from render_markdown import render

LO = {
    "objectives": ["Nêu được khái niệm lịch sử và môn Lịch sử.",
                   "Giải thích được vì sao cần học lịch sử."],
    "hook": "Chiếc điện thoại em đang cầm, 50 năm trước to bằng cả căn phòng. Vì sao?",
    "key_terms": [
        {"term": "Lịch sử", "definition": "Tất cả những gì đã xảy ra trong quá khứ.",
         "example": "Bức ảnh em chụp hồi lớp 1 đã là lịch sử của chính em."},
        # BẪY: ký tự phá bảng markdown
        {"term": "Quá khứ | Hiện tại", "definition": "Mốc chia\ntheo thời gian",
         "example": "Hôm qua | hôm nay"},
    ],
    "sections": [
        {"heading": "Mọi thứ đều thay đổi theo thời gian",
         "points": ["Con người, đồ vật và xã hội đều không ngừng biến đổi.",
                    "Sự thay đổi đó được gọi là lịch sử."]},
        {"heading": "Vì sao cần học lịch sử?",
         "points": ["Hiểu nguồn gốc của mọi sự vật.",
                    "Rút kinh nghiệm để định hướng tương lai."]},
    ],
    "mindmap": {
        "root": "Lịch sử là gì",
        "branches": [
            {"label": "Sự biến đổi",
             "children": ["Mọi vật thay đổi theo thời gian", "Con người và xã hội cũng vậy"]},
            {"label": "Lịch sử",
             "children": ["Tất cả những gì đã xảy ra", "Khoa học phục dựng quá khứ"]},
            {"label": "Môn Lịch sử",
             "children": ["Tìm hiểu xã hội loài người", "Từ khi có con người đến nay"]},
            {"label": "Vì sao cần học",
             "children": ["Hiểu nguồn gốc", "Hiểu hiện tại", "Định hướng tương lai"]},
        ]},
    "real_life": ["Album ảnh cũ của ông bà ghi lại lịch sử của gia đình em."],
    "memory_hooks": ["Lịch sử = ĐÃ + XẢY RA. Đã xảy ra rồi thì là lịch sử, dù mới hôm qua."],
    "misconceptions": [
        {"wrong": "Lịch sử chỉ là chuyện vua chúa, chiến tranh.",
         "correct": "Lịch sử là mọi thứ đã xảy ra, kể cả việc em học lớp 5 năm ngoái."}],
    "key_points": ["Lịch sử là tất cả những gì đã xảy ra trong quá khứ."],
}

fails = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# --- 1. mindmap ---
check("mindmap hợp lệ", _validate(LO["mindmap"]) == [], str(_validate(LO["mindmap"])))
svg = to_svg(LO["mindmap"], "Lịch sử là gì?")
check("SVG mở/đóng đúng", svg.startswith("<svg") and svg.rstrip().endswith("</svg>"))
check("SVG giữ dấu tiếng Việt", "Định hướng tương lai" in svg)
check("SVG escape XML", "&amp;" in to_svg({"root": "A & B", "branches": LO["mindmap"]["branches"]}))

mer = to_mermaid(LO["mindmap"])
check("mermaid bắt đầu đúng", mer.startswith("mindmap\n  root(("))
check("mermaid không còn ký tự phá cú pháp",
      not any(c in ln for ln in mer.splitlines()[2:] for c in "(),:;"))

# --- 2. markdown ---
md = render(LO, images=[{"file": "ls-bai-1_01.svg", "caption": "Sơ đồ tư duy"}])
check("KHÔNG có fence mermaid (bibeli dùng markdown-it thuần)", "```mermaid" not in md)
check("có heading Mục tiêu", "## 🎯 Mục tiêu" in md)
check("hook nằm trong blockquote", "\n> Chiếc điện thoại" in md)
check("ảnh tham chiếu filename trần", "![Sơ đồ tư duy](ls-bai-1_01.svg)" in md)

# BẪY: bảng markdown phải còn đúng 3 cột
tbl = [l for l in md.splitlines() if l.startswith("|") and "Quá khứ" in l]
check("dòng bảng có dấu | được escape", len(tbl) == 1 and tbl[0].count("\\|") == 2, str(tbl))
# đếm cột thật = số '|' không bị escape
raw = tbl[0].replace("\\|", "")
check("dòng bảng vẫn đúng 3 cột", raw.count("|") == 4, f"{raw.count('|')} thanh dọc")
check("xuống dòng trong ô đã bị làm phẳng", "Mốc chia theo thời gian" in md)

# --- 3. sống sót qua CSV round-trip ---
buf = io.StringIO()
w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
w.writerow(["topic_slug", "content"])
w.writerow(["ls-bai-1", md])
buf.seek(0)
back = list(csv.reader(buf))[1][1]
check("markdown sống sót round-trip CSV", back == md)

# --- 4. bản không dùng bảng (nếu bibeli tắt table) ---
md2 = render(LO, use_tables=False)
check("use_tables=False không sinh bảng", "| --- |" not in md2 and "❌" in md2)

print()
if fails:
    print(f"❌ {len(fails)} check thất bại: {fails}")
    sys.exit(1)
print("✅ Tất cả check đã qua. 0 token đã dùng.")
with open("preview_content.md", "w", encoding="utf-8") as f:
    f.write(md)
with open("preview_mindmap.svg", "w", encoding="utf-8") as f:
    f.write(svg)
print("   Xem: preview_content.md, preview_mindmap.svg")
