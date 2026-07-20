# -*- coding: utf-8 -*-
"""test_render.py — Nghiệm thu bước 1-2. Chạy: python3 test_render.py
KHÔNG gọi API, KHÔNG cần key. 0 token.
"""
import csv
import io
import sys

from infographic_prompt import build_prompt as build_infographic_prompt
from render_markdown import render

LO = {
    "concept_overview": "Lịch sử là tất cả những gì đã xảy ra trong quá khứ, "
                         "và môn Lịch sử là khoa học tìm hiểu lại điều đó.",
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
        {"heading": "Vì sao cần học lịch sử?", "icon_hint": "🌍",
         "formula": {"expression": "Không có công thức, dùng thử render",
                     "variables": [{"symbol": "t", "meaning": "mốc thời gian (năm)"}]},
         "points": ["Hiểu nguồn gốc của mọi sự vật.",
                    "Rút kinh nghiệm để định hướng tương lai."]},
    ],
    "real_life": ["Album ảnh cũ của ông bà ghi lại lịch sử của gia đình em."],
    "memory_hooks": ["Lịch sử = ĐÃ + XẢY RA. Đã xảy ra rồi thì là lịch sử, dù mới hôm qua."],
    "misconceptions": [
        {"wrong": "Lịch sử chỉ là chuyện vua chúa, chiến tranh.",
         "correct": "Lịch sử là mọi thứ đã xảy ra, kể cả việc em học lớp 5 năm ngoái."}],
    "quick_review": ["Lịch sử = mọi thứ đã xảy ra, kể cả chuyện hôm qua.",
                      "Học lịch sử để hiểu hiện tại, định hướng tương lai."],
    "key_points": ["Lịch sử là tất cả những gì đã xảy ra trong quá khứ."],
}

fails = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# --- 1. markdown ---
md = render(LO, images=[{"file": "ls-bai-1_01.jpg", "caption": "Ảnh minh hoạ"}])
check("KHÔNG có fence mermaid (bibeli dùng markdown-it thuần)", "```mermaid" not in md)
check("có heading Khái niệm trọng tâm", "## 🧠 Khái niệm trọng tâm" in md)
check("concept_overview nằm trong blockquote", "\n> Lịch sử là tất cả" in md)
check("có heading Mục tiêu", "## 🎯 Mục tiêu" in md)
check("hook nằm trong blockquote", "\n> Chiếc điện thoại" in md)
check("có công thức section trong khối code", "`Không có công thức, dùng thử render`" in md)
check("có biến số của công thức", "**t**: mốc thời gian (năm)" in md)
check("có heading Ghi nhớ nhanh", "## ⭐ Ghi nhớ nhanh" in md)
check("ảnh tham chiếu filename trần", "![Ảnh minh hoạ](ls-bai-1_01.jpg)" in md)

# BẪY: bảng markdown phải còn đúng 3 cột
tbl = [l for l in md.splitlines() if l.startswith("|") and "Quá khứ" in l]
check("dòng bảng có dấu | được escape", len(tbl) == 1 and tbl[0].count("\\|") == 2, str(tbl))
# đếm cột thật = số '|' không bị escape
raw = tbl[0].replace("\\|", "")
check("dòng bảng vẫn đúng 3 cột", raw.count("|") == 4, f"{raw.count('|')} thanh dọc")
check("xuống dòng trong ô đã bị làm phẳng", "Mốc chia theo thời gian" in md)

# --- 2. sống sót qua CSV round-trip ---
buf = io.StringIO()
w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
w.writerow(["topic_slug", "content"])
w.writerow(["ls-bai-1", md])
buf.seek(0)
back = list(csv.reader(buf))[1][1]
check("markdown sống sót round-trip CSV", back == md)

# --- 3. bản không dùng bảng (nếu bibeli tắt table) ---
md2 = render(LO, use_tables=False)
check("use_tables=False không sinh bảng", "| --- |" not in md2 and "❌" in md2)

# --- 4. prompt mô tả ảnh cho model sinh infographic (thuần code, 0 token) ---
prompt = build_infographic_prompt(LO, 'Bài 1: Lịch sử là gì? & "khoa học" <thử ký tự lạ>')
check("prompt nhắc đúng tiêu đề (kể cả ký tự đặc biệt)",
      'tiêu đề lớn "Bài 1: Lịch sử là gì? & "khoa học" <thử ký tự lạ>"' in prompt)
check("prompt có khối Khái niệm trọng tâm", "Khái niệm trọng tâm" in prompt)
check("prompt có công thức", "Không có công thức, dùng thử render" in prompt)
check("prompt có khối Ghi nhớ nhanh (khối cuối, cố định)", '"Ghi nhớ nhanh"' in prompt)
check("prompt yêu cầu đúng chính tả tiếng Việt", "ĐÚNG CHÍNH TẢ" in prompt)
check("dấu | trong key_terms giữ nguyên (prompt văn bản, không cần escape XML)",
      "Quá khứ | Hiện tại" in prompt)
try:
    build_infographic_prompt({}, "Bài rỗng")
    check("Learning Object rỗng -> raise ValueError", False)
except ValueError:
    check("Learning Object rỗng -> raise ValueError", True)

print()
if fails:
    print(f"❌ {len(fails)} check thất bại: {fails}")
    sys.exit(1)
print("✅ Tất cả check đã qua. 0 token đã dùng.")
with open("preview_content.md", "w", encoding="utf-8") as f:
    f.write(md)
with open("preview_infographic_prompt.txt", "w", encoding="utf-8") as f:
    f.write(prompt)
print("   Xem: preview_content.md, preview_infographic_prompt.txt")
