# -*- coding: utf-8 -*-
"""test_render.py — Nghiệm thu bước 1-2. Chạy: python3 test_render.py
KHÔNG gọi API, KHÔNG cần key. 0 token.
"""
import csv
import io
import sys

from render_markdown import H_ANSWER, H_COMPARE, H_VIDEO, render

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
    "comparison": {
        "title": "So sánh Lịch sử và môn Lịch sử",
        "headers": ["Tiêu chí", "Lịch sử", "Môn Lịch sử"],
        "rows": [
            ["Là gì", "Những gì đã xảy ra", "Khoa học nghiên cứu quá khứ"],
            # BẪY: ô chứa dấu | và số ô THIẾU so với headers -> phải escape + đệm
            ["Ví dụ | minh hoạ", "Ảnh cũ của gia đình"],
        ]},
    "real_life": ["Album ảnh cũ của ông bà ghi lại lịch sử của gia đình em."],
    "hook_answer": "Vì công nghệ luôn thay đổi theo thời gian — đó chính là lịch sử.",
    "video_query": "lịch sử là gì lớp 6 bài giảng",
    "video_url": "https://www.youtube.com/results?search_query=l%E1%BB%8Bch+s%E1%BB%AD",
    "key_points": ["Lịch sử là tất cả những gì đã xảy ra trong quá khứ."],
}

fails = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# --- 1. markdown ---
md = render(LO, images=[{"file": "ls-bai-1_01.png", "caption": "Ảnh minh hoạ"}])
check("KHÔNG có fence mermaid (bibeli dùng markdown-it thuần)", "```mermaid" not in md)
check("có heading Mục tiêu", "## 🎯 Mục tiêu" in md)
check("hook nằm trong blockquote", "\n> Chiếc điện thoại" in md)
check("ảnh tham chiếu filename trần", "![Ảnh minh hoạ](ls-bai-1_01.png)" in md)
check("KHÔNG còn mục Mẹo nhớ", "Mẹo nhớ" not in md)
check("KHÔNG còn mục Dễ nhầm lẫn", "Dễ nhầm" not in md)

# --- 2. bảng so sánh (thay cho mindmap cũ) ---
check("có heading Bảng so sánh", H_COMPARE in md)
check("bảng so sánh có tiêu đề cột", "| Tiêu chí | Lịch sử | Môn Lịch sử |" in md)
crow = [l for l in md.splitlines() if l.startswith("|") and "minh hoạ" in l]
check("ô so sánh có dấu | được escape", len(crow) == 1 and crow[0].count("\\|") == 1, str(crow))
# hàng thiếu ô phải được đệm cho đủ 3 cột: đúng 4 thanh | (không tính escape)
check("hàng so sánh thiếu ô vẫn đủ 3 cột",
      crow and crow[0].replace("\\|", "").count("|") == 4,
      f"{crow[0].replace(chr(92)+'|','').count('|') if crow else 0} thanh dọc")

# --- 3. câu trả lời khởi động là MỤC CUỐI CÙNG ---
check("có heading Trả lời câu hỏi khởi động", H_ANSWER in md)
check("hook_answer nằm CUỐI content",
      md.rstrip().rfind(H_ANSWER) > md.rfind(H_COMPARE), "phải sau bảng so sánh")
check("nội dung sau H_ANSWER chính là câu trả lời",
      "Vì công nghệ luôn thay đổi" in md.split(H_ANSWER, 1)[1])

# --- 4. video bài giảng ---
check("có heading Video bài giảng", H_VIDEO in md)
check("link YouTube trỏ đúng URL", "(https://www.youtube.com/results?search_query=" in md)

# BẪY: bảng key_terms phải còn đúng 3 cột
tbl = [l for l in md.splitlines() if l.startswith("|") and "Quá khứ" in l]
check("dòng bảng có dấu | được escape", len(tbl) == 1 and tbl[0].count("\\|") == 2, str(tbl))
# đếm cột thật = số '|' không bị escape
raw = tbl[0].replace("\\|", "")
check("dòng bảng vẫn đúng 3 cột", raw.count("|") == 4, f"{raw.count('|')} thanh dọc")
check("xuống dòng trong ô đã bị làm phẳng", "Mốc chia theo thời gian" in md)

# --- 5. sống sót qua CSV round-trip ---
buf = io.StringIO()
w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
w.writerow(["topic_slug", "content"])
w.writerow(["ls-bai-1", md])
buf.seek(0)
back = list(csv.reader(buf))[1][1]
check("markdown sống sót round-trip CSV", back == md)

# --- 6. bản không dùng bảng (nếu bibeli tắt table) ---
md2 = render(LO, use_tables=False)
check("use_tables=False không sinh bảng", "| --- |" not in md2)
check("use_tables=False: key_terms đổ sang danh sách", "- **Lịch sử**" in md2)
check("use_tables=False: bảng so sánh đổ sang danh sách", H_COMPARE in md2 and "- **Là gì**" in md2)

print()
if fails:
    print(f"❌ {len(fails)} check thất bại: {fails}")
    sys.exit(1)
print("✅ Tất cả check đã qua. 0 token đã dùng.")
with open("preview_content.md", "w", encoding="utf-8") as f:
    f.write(md)
print("   Xem: preview_content.md")
