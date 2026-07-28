# -*- coding: utf-8 -*-
"""render_markdown.py — Learning Object (JSON) -> Markdown cho cột `content`.

THUẦN CODE, 0 token AI.

Ràng buộc đã biết về bibeli:
- Frontend dùng markdown-it/marked THUẦN => KHÔNG có mermaid.
  => tuyệt đối không sinh fence ```mermaid (sẽ hiện thành khối code xấu).
- Bảng: markdown-it và marked đều bật table mặc định. Nếu bibeli tắt,
  đặt use_tables=False để đổ sang dạng danh sách. Bài học tóm tắt bằng BẢNG
  SO SÁNH (thay cho mindmap ảnh cũ) — thuần markdown, hiển thị mọi nơi.
"""

def content_markdown(entry: dict, images: list = None,
                     use_tables: bool = True, density: str = "full") -> str:
    """Điểm vào DUY NHẤT cho mọi stage cần text của một topic.

    - Cache v2 (Learning Object JSON) -> render ra markdown bằng code (0 token).
    - Cache v1 (còn field content_markdown) -> trả nguyên blob cũ.
    Nhờ đó stage_questions / stage_review / stage_export không cần biết
    content đang ở phiên bản nào.
    """
    if not entry:
        return ""
    if "content_markdown" in entry:          # v1
        return entry["content_markdown"]
    return render(entry, images=images, use_tables=use_tables, density=density)


H_OBJECTIVES = "## 🎯 Mục tiêu"
H_HOOK = "## 🤔 Câu hỏi khởi động"
H_TERMS = "## 🔑 Từ khoá cần nhớ"
H_MAIN = "## 📚 Nội dung chính"
H_COMPARE = "## 📊 Bảng so sánh ghi nhớ"
H_REAL = "## 🌍 Liên hệ thực tế"
H_IMAGES = "## 🖼️ Hình minh hoạ"
H_VIDEO = "## 🎬 Video bài giảng"
H_ANSWER = "## ✅ Trả lời câu hỏi khởi động"


def _cell(s: str) -> str:
    """Thoát ký tự phá vỡ bảng markdown.

    KHÔNG phải chi tiết vụn vặt: một dấu '|' trong định nghĩa là đủ để
    lệch cột toàn bảng, và lỗi chỉ lộ ra sau khi đã import xong.
    """
    return (str(s).replace("\\", "\\\\")
            .replace("|", "\\|")
            .replace("\r", " ")
            .replace("\n", " ")
            .strip())


def _line(s: str) -> str:
    """Làm sạch text 1 dòng ngoài bảng (giữ nguyên dấu |)."""
    return " ".join(str(s).split()).strip()


def _bullets(items, max_words: int = 0) -> list:
    out = []
    for x in (items or []):
        if not str(x).strip():
            continue
        out.append(f"- {_trim(_line(x), max_words)}")
    return out


def _comparison(cmp: dict, use_tables: bool = True) -> list:
    """Bảng so sánh nội dung bài -> markdown. Đệm/cắt mỗi hàng cho đúng số cột
    (một hàng lệch cột là đủ vỡ cả bảng sau khi import). Trả list dòng, [] nếu
    thiếu dữ liệu."""
    if not isinstance(cmp, dict):
        return []
    headers = [str(h) for h in (cmp.get("headers") or []) if str(h).strip()]
    rows = [r for r in (cmp.get("rows") or []) if isinstance(r, (list, tuple)) and any(str(c).strip() for c in r)]
    if len(headers) < 2 or not rows:
        return []
    n = len(headers)
    out = []
    if cmp.get("title"):
        out.append(f"*{_line(cmp['title'])}*")
        out.append("")
    if use_tables:
        out.append("| " + " | ".join(_cell(h) for h in headers) + " |")
        out.append("| " + " | ".join("---" for _ in headers) + " |")
        for r in rows:
            cells = ([_cell(c) for c in r] + [""] * n)[:n]
            out.append("| " + " | ".join(cells) + " |")
    else:
        for r in rows:
            cells = ([_line(c) for c in r] + [""] * n)[:n]
            out.append(f"- **{cells[0]}**")
            for h, c in zip(headers[1:], cells[1:]):
                out.append(f"  - {_line(h)}: {c}")
    return out


def _trim(s: str, max_words: int) -> str:
    """Cắt bớt point quá dài về max_words từ (0 = không cắt), thêm … nếu cắt.
    Cắt ở ranh giới từ, không cắt giữa chữ."""
    if max_words <= 0:
        return s
    w = s.split()
    if len(w) <= max_words:
        return s
    return " ".join(w[:max_words]).rstrip(" .,;:") + "…"


# Cấu hình 3 mức mật độ hiển thị. Tất cả THUẦN CODE, 0 token — đổi mức chỉ cần
# re-render từ cache, không gọi lại AI.
#   full    : giữ nguyên mọi thứ (mặc định cũ)
#   compact : mỗi section tối đa 3 point, point dài cắt còn 22 từ; bỏ ví dụ ở
#             key_terms; giữ đủ section
#   minimal : chỉ Mục tiêu + Nội dung chính (2 point/section, 18 từ) + Bảng so
#             sánh + Trả lời khởi động. Liên hệ/Dễ nhầm/Mẹo nhớ ẩn (đọc nhanh, ôn tập)
DENSITY = {
    "full":    {"max_points": 0, "max_words": 0,  "term_example": True,
                "keep": {"objectives", "hook", "key_terms", "sections",
                         "comparison", "real_life", "images", "video",
                         "hook_answer"}},
    "compact": {"max_points": 3, "max_words": 22, "term_example": False,
                "keep": {"objectives", "hook", "key_terms", "sections",
                         "comparison", "real_life", "images", "video",
                         "hook_answer"}},
    "minimal": {"max_points": 2, "max_words": 18, "term_example": False,
                "keep": {"objectives", "sections", "comparison", "images",
                         "hook_answer"}},
}


def render(lo: dict, images: list = None, use_tables: bool = True,
           density: str = "full") -> str:
    """Learning object -> markdown string. images: list {file, caption}.
    density: 'full' | 'compact' | 'minimal' — xem DENSITY."""
    cfg = DENSITY.get(density, DENSITY["full"])
    mp, mw, keep = cfg["max_points"], cfg["max_words"], cfg["keep"]

    def _cap(items):
        return items[:mp] if mp > 0 else items

    p = []

    if lo.get("objectives") and "objectives" in keep:
        p.append(H_OBJECTIVES)
        p += _bullets(lo["objectives"], mw)
        p.append("")

    if lo.get("hook") and "hook" in keep:
        p.append(H_HOOK)
        p.append(f"> {_line(lo['hook'])}")
        p.append("")

    if lo.get("key_terms") and "key_terms" in keep:
        p.append(H_TERMS)
        show_ex = cfg["term_example"]
        if use_tables:
            if show_ex:
                p.append("| Thuật ngữ | Nghĩa là gì | Ví dụ |")
                p.append("| --- | --- | --- |")
                for t in lo["key_terms"]:
                    p.append(f"| **{_cell(t.get('term',''))}** "
                             f"| {_cell(t.get('definition',''))} "
                             f"| {_cell(t.get('example',''))} |")
            else:
                p.append("| Thuật ngữ | Nghĩa là gì |")
                p.append("| --- | --- |")
                for t in lo["key_terms"]:
                    p.append(f"| **{_cell(t.get('term',''))}** "
                             f"| {_cell(t.get('definition',''))} |")
        else:
            for t in lo["key_terms"]:
                p.append(f"- **{_line(t.get('term',''))}**: {_line(t.get('definition',''))}")
                if show_ex and t.get("example"):
                    p.append(f"  - *Ví dụ:* {_line(t['example'])}")
        p.append("")

    if lo.get("sections") and "sections" in keep:
        p.append(H_MAIN)
        for s in lo["sections"]:
            p.append("")
            icon = _line(s.get("icon_hint", ""))
            head = f"{icon} " if icon else ""
            p.append(f"### {head}{_line(s.get('heading',''))}")
            p += _bullets(_cap(s.get("points") or []), mw)
        p.append("")

    if lo.get("comparison") and "comparison" in keep:
        rows_md = _comparison(lo["comparison"], use_tables)
        if rows_md:
            p.append(H_COMPARE)
            p += rows_md
            p.append("")

    if lo.get("real_life") and "real_life" in keep:
        p.append(H_REAL)
        p += _bullets(_cap(lo["real_life"]), mw)
        p.append("")

    if images and "images" in keep:
        p.append(H_IMAGES)
        for img in images:
            cap = _line(img.get("caption", "")).replace("]", ")")
            p.append(f"![{cap}]({img['file']})")
        p.append("")

    if lo.get("video_url") and "video" in keep:
        p.append(H_VIDEO)
        q = _line(lo.get("video_query", ""))
        label = "Tìm clip giảng bài trên YouTube" + (f": {q}" if q else "")
        p.append(f"- [{label}]({_line(lo['video_url'])})")
        p.append("")

    # Mục CUỐI CÙNG: chốt lại bằng câu trả lời cho câu hỏi khởi động.
    if lo.get("hook_answer") and "hook_answer" in keep:
        p.append(H_ANSWER)
        if lo.get("hook"):
            p.append(f"> {_line(lo['hook'])}")
            p.append("")
        p.append(f"👉 {_line(lo['hook_answer'])}")
        p.append("")

    # gộp dòng trống thừa
    out, prev_blank = [], False
    for ln in p:
        blank = (ln == "")
        if blank and prev_blank:
            continue
        out.append(ln)
        prev_blank = blank
    return "\n".join(out).strip() + "\n"
