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
                     use_tables: bool = True) -> str:
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
    return render(entry, images=images, use_tables=use_tables)


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


def _bullets(items) -> list:
    return [f"- {_line(x)}" for x in (items or []) if str(x).strip()]


def render(lo: dict, images: list = None, use_tables: bool = True) -> str:
    """Learning object -> markdown string. images: list {file, caption}."""
    p = []

    if lo.get("objectives"):
        p.append(H_OBJECTIVES)
        p += _bullets(lo["objectives"])
        p.append("")

    if lo.get("hook"):
        p.append(H_HOOK)
        p.append(f"> {_line(lo['hook'])}")
        p.append("")

    if lo.get("key_terms"):
        p.append(H_TERMS)
        if use_tables:
            p.append("| Thuật ngữ | Nghĩa là gì | Ví dụ |")
            p.append("| --- | --- | --- |")
            for t in lo["key_terms"]:
                p.append(f"| **{_cell(t.get('term',''))}** "
                         f"| {_cell(t.get('definition',''))} "
                         f"| {_cell(t.get('example',''))} |")
        else:
            for t in lo["key_terms"]:
                p.append(f"- **{_line(t.get('term',''))}**: {_line(t.get('definition',''))}")
                if t.get("example"):
                    p.append(f"  - *Ví dụ:* {_line(t['example'])}")
        p.append("")

    if lo.get("sections"):
        p.append(H_MAIN)
        for s in lo["sections"]:
            p.append("")
            icon = _line(s.get("icon_hint", ""))
            head = f"{icon} " if icon else ""
            p.append(f"### {head}{_line(s.get('heading',''))}")
            p += _bullets(s.get("points"))
        p.append("")

    if lo.get("real_life"):
        p.append(H_REAL)
        p += _bullets(lo["real_life"])
        p.append("")

    if lo.get("misconceptions"):
        p.append(H_MISC)
        if use_tables:
            p.append("| Nhiều bạn nghĩ | Thực ra |")
            p.append("| --- | --- |")
            for m in lo["misconceptions"]:
                p.append(f"| {_cell(m.get('wrong',''))} | {_cell(m.get('correct',''))} |")
        else:
            for m in lo["misconceptions"]:
                p.append(f"- ❌ {_line(m.get('wrong',''))}")
                p.append(f"  - ✅ {_line(m.get('correct',''))}")
        p.append("")

    if lo.get("memory_hooks"):
        p.append(H_HOOKS)
        p += _bullets(lo["memory_hooks"])
        p.append("")

    if images:
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
