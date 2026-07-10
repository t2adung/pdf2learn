# -*- coding: utf-8 -*-
"""render_markdown.py — Learning Object (JSON) -> Markdown cho cột `content`.

THUẦN CODE, 0 token AI.

Ràng buộc đã biết về bibeli:
- Frontend dùng markdown-it/marked THUẦN => KHÔNG có mermaid.
  => tuyệt đối không sinh fence ```mermaid (sẽ hiện thành khối code xấu).
  Mindmap đi đường ảnh SVG qua stage_images.
- Bảng: markdown-it và marked đều bật table mặc định. Nếu bibeli tắt,
  đặt use_tables=False để đổ sang dạng danh sách.
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
H_REAL = "## 🌍 Liên hệ thực tế"
H_MISC = "## ⚠️ Dễ nhầm lẫn"
H_HOOKS = "## 💡 Mẹo nhớ"
H_IMAGES = "## 🖼️ Hình minh hoạ"


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
#   minimal : chỉ Mục tiêu + Nội dung chính (2 point/section, 18 từ) + Mindmap.
#             Các phần Liên hệ/Dễ nhầm/Mẹo nhớ ẩn đi (đọc nhanh, ôn tập)
DENSITY = {
    "full":    {"max_points": 0, "max_words": 0,  "term_example": True,
                "keep": {"objectives", "hook", "key_terms", "sections",
                         "real_life", "misconceptions", "memory_hooks", "images"}},
    "compact": {"max_points": 3, "max_words": 22, "term_example": False,
                "keep": {"objectives", "hook", "key_terms", "sections",
                         "real_life", "misconceptions", "memory_hooks", "images"}},
    "minimal": {"max_points": 2, "max_words": 18, "term_example": False,
                "keep": {"objectives", "sections", "images"}},
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

    if lo.get("real_life") and "real_life" in keep:
        p.append(H_REAL)
        p += _bullets(_cap(lo["real_life"]), mw)
        p.append("")

    if lo.get("misconceptions") and "misconceptions" in keep:
        p.append(H_MISC)
        if use_tables:
            p.append("| Nhiều bạn nghĩ | Thực ra |")
            p.append("| --- | --- |")
            for m in _cap(lo["misconceptions"]):
                p.append(f"| {_cell(m.get('wrong',''))} | {_cell(m.get('correct',''))} |")
        else:
            for m in _cap(lo["misconceptions"]):
                p.append(f"- ❌ {_line(m.get('wrong',''))}")
                p.append(f"  - ✅ {_line(m.get('correct',''))}")
        p.append("")

    if lo.get("memory_hooks") and "memory_hooks" in keep:
        p.append(H_HOOKS)
        p += _bullets(_cap(lo["memory_hooks"]), mw)
        p.append("")

    if images and "images" in keep:
        p.append(H_IMAGES)
        for img in images:
            cap = _line(img.get("caption", "")).replace("]", ")")
            p.append(f"![{cap}]({img['file']})")
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
