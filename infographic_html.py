# -*- coding: utf-8 -*-
"""infographic_html.py — Dựng trang HTML "tổng hợp kiến thức" (infographic)
từ Learning Object. THUẦN CODE, 0 token AI, không bao giờ lỗi cú pháp và
KHÔNG BAO GIỜ sai chính tả (chữ là text HTML thật, trình duyệt tự render
font có sẵn — khác hẳn model sinh ảnh "vẽ" từng nét chữ như pixel).

Đây là bản HTML/CSS thay cho 2 hướng đã thử trước:
- v1 (SVG code): bố cục đúng nhưng phải tự tính tay từng dòng chữ xuống
  dòng ở đâu (word-wrap thủ công) — CSS làm việc này tự động, tốt hơn nhiều.
- v2 (model sinh ảnh): có minh hoạ đẹp nhưng tốn 1 request/topic, không
  deterministic, và chữ tiếng Việt hay sai chính tả trong ảnh AI vẽ.

HTML này KHÔNG dùng trực tiếp — file `html_render.py` chụp nó thành PNG
bằng headless Chromium (Playwright) để gắn vào pipeline ảnh hiện có
(topics.csv/manifest.json vẫn tham chiếu 1 file ảnh như trước). File .html
gốc cũng được lưu lại cùng chỗ, phòng khi frontend muốn nhúng HTML trực
tiếp thay vì dùng ảnh chụp.
"""
import html as _html

COLORS = ["#2563eb", "#059669", "#7c3aed", "#db2777", "#0891b2", "#4f46e5"]
REVIEW_COLOR = "#d97706"
WIDTH = 860


def _esc(s) -> str:
    return _html.escape(str(s), quote=True)


def _blocks(lo: dict) -> list:
    """Learning Object -> list khối nội dung (chưa gán màu/số thứ tự)."""
    out = []

    overview = str(lo.get("concept_overview", "")).strip()
    objectives = [str(o).strip() for o in (lo.get("objectives") or []) if str(o).strip()]
    if overview or objectives:
        out.append({"kind": "overview", "heading": "Khái niệm trọng tâm", "icon": "🧠",
                    "overview": overview, "objectives": objectives})

    for s in (lo.get("sections") or []):
        heading = str(s.get("heading", "")).strip()
        points = [str(p).strip() for p in (s.get("points") or []) if str(p).strip()]
        if not heading and not points:
            continue
        out.append({"kind": "section", "heading": heading or "Nội dung",
                    "icon": str(s.get("icon_hint", "")).strip() or "📌",
                    "formula": s.get("formula") or {}, "points": points})

    key_terms = lo.get("key_terms") or []
    if key_terms:
        out.append({"kind": "terms", "heading": "Từ khoá cần nhớ", "icon": "🔑",
                    "terms": key_terms})

    notes = {"real_life": [x for x in (lo.get("real_life") or []) if str(x).strip()],
             "misconceptions": lo.get("misconceptions") or [],
             "memory_hooks": [x for x in (lo.get("memory_hooks") or []) if str(x).strip()]}
    if any(notes.values()):
        out.append({"kind": "notes", "heading": "Lưu ý & mẹo nhớ", "icon": "💡", "notes": notes})

    quick_review = [x for x in (lo.get("quick_review") or []) if str(x).strip()]
    if quick_review:
        out.append({"kind": "review", "heading": "Ghi nhớ nhanh", "icon": "⭐",
                    "items": quick_review})

    return out


def _card_body(b: dict) -> str:
    if b["kind"] == "overview":
        parts = []
        if b["overview"]:
            parts.append(f'<p class="overview">{_esc(b["overview"])}</p>')
        if b["objectives"]:
            items = "".join(f"<li>{_esc(o)}</li>" for o in b["objectives"])
            parts.append(f'<ul class="plain">{items}</ul>')
        return "".join(parts)

    if b["kind"] == "section":
        parts = []
        formula = b["formula"]
        expr = str(formula.get("expression", "")).strip()
        if expr:
            variables = "".join(
                f'<li><b>{_esc(v.get("symbol",""))}</b> — {_esc(v.get("meaning",""))}</li>'
                for v in (formula.get("variables") or []) if v.get("symbol"))
            parts.append(f'<div class="formula"><code>{_esc(expr)}</code>'
                         f'{f"<ul>{variables}</ul>" if variables else ""}</div>')
        if b["points"]:
            items = "".join(f"<li>{_esc(p)}</li>" for p in b["points"])
            parts.append(f'<ul>{items}</ul>')
        return "".join(parts)

    if b["kind"] == "terms":
        items = []
        for t in b["terms"]:
            term, definition = str(t.get("term", "")).strip(), str(t.get("definition", "")).strip()
            if not term:
                continue
            ex = str(t.get("example", "")).strip()
            items.append(f'<li><b>{_esc(term)}</b>: {_esc(definition)}'
                         f'{f"<br><i>Ví dụ: {_esc(ex)}</i>" if ex else ""}</li>')
        return f'<ul>{"".join(items)}</ul>'

    if b["kind"] == "notes":
        items = []
        for x in b["notes"]["real_life"]:
            items.append(f"<li>🌍 {_esc(x)}</li>")
        for m in b["notes"]["misconceptions"]:
            items.append(f'<li>❌ {_esc(m.get("wrong",""))} '
                         f'<br>✅ {_esc(m.get("correct",""))}</li>')
        for x in b["notes"]["memory_hooks"]:
            items.append(f"<li>💡 {_esc(x)}</li>")
        return f'<ul>{"".join(items)}</ul>'

    if b["kind"] == "review":
        items = "".join(f"<li>{_esc(x)}</li>" for x in b["items"])
        return f'<ul class="review-list">{items}</ul>'

    return ""


def render(lo: dict, title: str) -> str:
    """Learning Object -> chuỗi HTML infographic hoàn chỉnh (có <style> nhúng
    sẵn). Ném ValueError nếu không có field nào để vẽ."""
    lo = lo or {}
    blocks = _blocks(lo)
    if not blocks:
        raise ValueError("Learning Object rỗng — không có field nào để vẽ infographic.")

    hook = str(lo.get("hook", "")).strip()
    hook_html = (f'<div class="hook">🤔 <b>Câu hỏi khởi động</b><br>{_esc(hook)}</div>'
                if hook else "")

    cards = []
    for i, b in enumerate(blocks, 1):
        is_review = b["kind"] == "review"
        color = REVIEW_COLOR if is_review else COLORS[(i - 1) % len(COLORS)]
        cls = "card review" if is_review else "card"
        cards.append(
            f'<section class="{cls}" style="--c:{color}">'
            f'<span class="badge">{i}</span>'
            f'<h2><span class="icon">{_esc(b["icon"])}</span>{_esc(b["heading"])}</h2>'
            f'{_card_body(b)}'
            f'</section>')

    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; width: {WIDTH}px;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    background: #fdfaf3; color: #1f2937;
  }}
  .banner {{
    background: linear-gradient(135deg, #1e3a8a, #2563eb);
    color: #fff; text-align: center; padding: 30px 28px 24px;
  }}
  .banner h1 {{ margin: 0 0 12px; font-size: 26px; font-weight: 800; line-height: 1.3; }}
  .pill {{
    display: inline-block; background: #fbbf24; color: #78350f;
    font-weight: 700; font-size: 12.5px; letter-spacing: .04em;
    padding: 7px 20px; border-radius: 999px; text-transform: uppercase;
  }}
  .hook {{
    margin: 20px 28px 0; background: #fef3c7; border-radius: 12px;
    padding: 14px 18px; font-style: italic; color: #78350f; font-size: 14.5px;
    line-height: 1.5;
  }}
  .blocks {{ padding: 22px 28px 30px; }}
  .card {{
    position: relative; background: #fff; border: 2px dashed var(--c);
    border-radius: 16px; padding: 18px 22px 16px 26px; margin-top: 22px;
  }}
  .card:first-child {{ margin-top: 0; }}
  .card.review {{
    border: none; background: linear-gradient(135deg, #fef3c7, #fde68a);
  }}
  .badge {{
    position: absolute; top: -16px; left: 18px; width: 34px; height: 34px;
    border-radius: 50%; background: var(--c); color: #fff; font-weight: 800;
    font-size: 15px; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 3px 8px rgba(0,0,0,.18);
  }}
  .card h2 {{
    margin: 6px 0 10px; font-size: 18px; font-weight: 800; color: var(--c);
    display: flex; align-items: center; gap: 8px;
  }}
  .card.review h2 {{ color: #92400e; }}
  .icon {{ font-size: 20px; line-height: 1; }}
  .card p.overview {{ margin: 0 0 8px; font-size: 15px; line-height: 1.55; font-style: italic; }}
  .card ul {{ margin: 0; padding-left: 22px; font-size: 14.5px; line-height: 1.6; color: #374151; }}
  .card ul.plain {{ list-style: "🎯  "; }}
  .card.review ul.review-list {{ list-style: "⭐  "; color: #78350f; font-weight: 600; }}
  .card li {{ margin: 3px 0; }}
  .card li + li {{ margin-top: 6px; }}
  .formula {{
    background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 10px;
    padding: 10px 14px; margin-bottom: 10px;
  }}
  .formula code {{
    display: block; font-family: 'Consolas', 'SF Mono', Menlo, monospace;
    font-weight: 700; color: #3730a3; font-size: 15px; margin-bottom: 6px;
  }}
  .formula ul {{ margin: 0; padding-left: 18px; font-size: 13px; color: #4338ca; }}
</style>
</head>
<body>
  <div class="banner">
    <h1>{_esc(title)}</h1>
    <span class="pill">Tổng hợp kiến thức</span>
  </div>
  {hook_html}
  <div class="blocks">
    {''.join(cards)}
  </div>
</body>
</html>"""
