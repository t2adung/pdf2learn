# -*- coding: utf-8 -*-
"""infographic_svg.py — Vẽ 1 ảnh "tổng hợp kiến thức" (infographic) từ Learning
Object bằng CODE THUẦN (SVG), 0 token AI, không bao giờ lỗi cú pháp.

KHÔNG nhắm tái tạo y hệt phong cách minh hoạ tay (nhân vật, hoạ tiết trang trí)
của các tờ tổng hợp kiến thức mẫu — việc đó cần hoạ sĩ hoặc AI vẽ ảnh, không
thể sinh bằng code hình học. Module này chỉ tái hiện ĐÚNG BỐ CỤC: banner tiêu
đề, các khối đánh số viền màu kèm icon (emoji từ icon_hint), khối công thức
tách riêng biến số, khối "Ghi nhớ nhanh" tô màu nổi bật chốt cuối.

Input là Learning Object (xem CONTENT_SCHEMA ở stage_content.py). Field nào
rỗng thì bỏ qua khối tương ứng — bài không có "sections" vẫn ra ảnh hợp lệ
miễn có concept_overview hoặc quick_review.
"""
import html

WIDTH = 820
PAD_X = 40
CONTENT_W = WIDTH - 2 * PAD_X
BOX_PAD = 20
GAP = 22
FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
MONO = "'Consolas', 'SF Mono', Menlo, monospace"
BG = "#fdfaf3"
INK = "#1f2937"
SUBINK = "#4b5563"
COLORS = ["#2563eb", "#059669", "#7c3aed", "#db2777", "#0891b2", "#4f46e5"]
REVIEW_COLOR = "#d97706"
REVIEW_BG = "#fef3c7"


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _wrap(text: str, max_chars: int) -> list:
    words = str(text).split()
    if not words:
        return [""]
    max_chars = max(max_chars, 8)
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def _chars_for(width_px: float, size: float) -> int:
    return max(10, int(width_px / (size * 0.52)))


class _Svg:
    def __init__(self):
        self.parts = []
        self.y = 0.0

    def rect(self, x, y, w, h, fill="#ffffff", stroke=None, sw=2, rx=14, dash=None):
        s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}"{s}{d}/>')

    def circle(self, cx, cy, r, fill):
        self.parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"/>')

    def text(self, x, y, s, size=15, weight="normal", fill=INK, anchor="start",
              family=FONT, style="normal"):
        if not str(s).strip():
            return
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" font-style="{style}" fill="{fill}" '
            f'text-anchor="{anchor}">{_esc(s)}</text>')

    def para(self, x, y, text, box_w, size=15, lh=22, fill=SUBINK, weight="normal",
              style="normal") -> float:
        """Đoạn văn tự xuống dòng, KHÔNG bullet. Trả về y sau khi vẽ."""
        for ln in _wrap(text, _chars_for(box_w, size)):
            self.text(x, y, ln, size=size, fill=fill, weight=weight, style=style)
            y += lh
        return y

    def bullets(self, x, y, items, box_w, size=14.5, lh=21, fill=SUBINK,
                 marker="•", indent=18) -> float:
        max_chars = _chars_for(box_w - indent, size)
        for it in items:
            it = str(it).strip()
            if not it:
                continue
            wrapped = _wrap(it, max_chars)
            self.text(x, y, f"{marker} {wrapped[0]}", size=size, fill=fill)
            y += lh
            for cont in wrapped[1:]:
                self.text(x + indent, y, cont, size=size, fill=fill)
                y += lh
        return y


def _badge_heading(svg: _Svg, num: int, heading: str, color: str, y: float) -> float:
    """Số tròn + tiêu đề mục. Trả về y để bắt đầu vẽ khối nội dung bên dưới."""
    cy = y + 17
    svg.circle(PAD_X + 17, cy, 17, color)
    svg.parts.append(
        f'<text x="{PAD_X + 17:.1f}" y="{cy + 6:.1f}" font-family="{FONT}" '
        f'font-size="16" font-weight="bold" fill="#ffffff" text-anchor="middle">{num}</text>')
    svg.text(PAD_X + 46, cy + 6, heading, size=19, weight="bold", fill=color)
    return y + 44


def _formula_box(svg: _Svg, x: float, y: float, w: float, formula: dict) -> float:
    expr = str(formula.get("expression", "")).strip()
    variables = [v for v in (formula.get("variables") or [])
                 if v.get("symbol") or v.get("meaning")]
    if not expr and not variables:
        return y
    n_lines = 1 + len(variables)
    h = 16 + n_lines * 21 + 10
    svg.rect(x, y, w, h, fill="#eef2ff", stroke="#c7d2fe", sw=1.5, rx=10)
    ty = y + 26
    svg.text(x + 16, ty, expr, size=16, weight="bold", fill="#3730a3", family=MONO)
    ty += 24
    for v in variables:
        sym = str(v.get("symbol", "")).strip()
        meaning = str(v.get("meaning", "")).strip()
        svg.text(x + 16, ty, f"{sym} — {meaning}", size=13.5, fill="#4338ca")
        ty += 21
    return y + h + 12


def _measure_formula_box(formula: dict) -> float:
    if not formula:
        return 0
    variables = [v for v in (formula.get("variables") or [])
                 if v.get("symbol") or v.get("meaning")]
    if not formula.get("expression", "").strip() and not variables:
        return 0
    n_lines = 1 + len(variables)
    return 16 + n_lines * 21 + 10 + 12


def _measure_para(text: str, box_w: float, size: float, lh: float) -> float:
    if not str(text).strip():
        return 0
    return len(_wrap(text, _chars_for(box_w, size))) * lh


def _measure_bullets(items, box_w: float, size: float, lh: float, indent: float = 18) -> float:
    items = [str(i).strip() for i in (items or []) if str(i).strip()]
    if not items:
        return 0
    max_chars = _chars_for(box_w - indent, size)
    total = 0
    for it in items:
        total += len(_wrap(it, max_chars)) * lh
    return total


def render(lo: dict, title: str) -> str:
    """Learning Object -> chuỗi SVG infographic. Ném ValueError nếu không có
    field nào để vẽ (caller nên bắt và bỏ qua ảnh cho topic đó)."""
    lo = lo or {}
    blocks = []  # list of dict: kind, heading, icon, body-render-fn

    if str(lo.get("concept_overview", "")).strip():
        blocks.append({"kind": "overview", "heading": "Khái niệm trọng tâm", "icon": "🧠"})

    for s in (lo.get("sections") or []):
        if not str(s.get("heading", "")).strip() and not (s.get("points") or []):
            continue
        blocks.append({"kind": "section", "data": s,
                        "heading": s.get("heading", ""), "icon": s.get("icon_hint", "")})

    if lo.get("key_terms"):
        blocks.append({"kind": "terms", "heading": "Từ khoá cần nhớ", "icon": "🔑"})

    notes = {"real_life": lo.get("real_life") or [],
             "misconceptions": lo.get("misconceptions") or [],
             "memory_hooks": lo.get("memory_hooks") or []}
    if any(notes.values()):
        blocks.append({"kind": "notes", "heading": "Lưu ý & mẹo nhớ", "icon": "💡"})

    if lo.get("quick_review"):
        blocks.append({"kind": "review", "heading": "Ghi nhớ nhanh", "icon": "⭐"})

    if not blocks:
        raise ValueError("Learning Object rỗng — không có field nào để vẽ infographic.")

    inner_w = CONTENT_W - 2 * BOX_PAD

    def _measure(block) -> float:
        kind = block["kind"]
        if kind == "overview":
            h = _measure_para(lo.get("concept_overview", ""), inner_w, 15.5, 23)
            objs = lo.get("objectives") or []
            if objs:
                h += 8 + _measure_bullets(objs, inner_w, 14, 20)
            return h
        if kind == "section":
            s = block["data"]
            h = _measure_formula_box(s.get("formula") or {})
            h += _measure_bullets(s.get("points") or [], inner_w, 14.5, 21)
            return h
        if kind == "terms":
            h = 0.0
            for t in lo.get("key_terms") or []:
                line = f"{t.get('term','')}: {t.get('definition','')}"
                h += _measure_para(line, inner_w, 14, 20) + 4
                if t.get("example"):
                    h += _measure_para(f"Ví dụ: {t['example']}", inner_w - 16, 12.5, 18)
            return h
        if kind == "notes":
            items = []
            for x in notes["real_life"]:
                items.append(x)
            for m in notes["misconceptions"]:
                items.append(f"{m.get('wrong','')} → thực ra: {m.get('correct','')}")
            for m in notes["memory_hooks"]:
                items.append(m)
            return _measure_bullets(items, inner_w, 14, 20)
        if kind == "review":
            return _measure_bullets(lo.get("quick_review") or [], inner_w, 15, 23)
        return 0.0

    # ---- pass 1: tính tổng chiều cao ----
    y = 0.0
    y += 108  # banner
    hook = str(lo.get("hook", "")).strip()
    if hook:
        y += 14 + _measure_para(hook, CONTENT_W - 32, 14, 20) + 18
    for i, b in enumerate(blocks, 1):
        y += 44  # badge + heading
        body_h = _measure(b)
        y += body_h + 2 * BOX_PAD
        y += GAP
    y += 24  # bottom margin
    total_h = y

    # ---- pass 2: vẽ thật ----
    svg = _Svg()
    svg.rect(0, 0, WIDTH, total_h, fill=BG, rx=0)

    svg.rect(0, 0, WIDTH, 108, fill="#1e3a8a", rx=0)
    title_lines = _wrap(title, _chars_for(WIDTH - 80, 24))[:2]
    ty = 42 if len(title_lines) > 1 else 54
    for ln in title_lines:
        svg.text(WIDTH / 2, ty, ln, size=24, weight="bold", fill="#ffffff", anchor="middle")
        ty += 30
    svg.rect(WIDTH / 2 - 110, 82, 220, 22, fill="#fbbf24", rx=11)
    svg.text(WIDTH / 2, 97.5, "TỔNG HỢP KIẾN THỨC", size=12, weight="bold",
              fill="#78350f", anchor="middle")

    y = 108
    if hook:
        y += 14
        svg.text(PAD_X, y, "🤔  Câu hỏi khởi động", size=13, weight="bold", fill="#92400e")
        y += 20
        y = svg.para(PAD_X, y, hook, CONTENT_W - 32, size=14, lh=20,
                      fill="#78350f", style="italic")
        y += 18

    for i, b in enumerate(blocks, 1):
        kind = b["kind"]
        color = REVIEW_COLOR if kind == "review" else COLORS[(i - 1) % len(COLORS)]
        box_bg = REVIEW_BG if kind == "review" else "#ffffff"
        dash = None if kind == "review" else "6,5"
        icon = b.get("icon") or ""
        heading = f"{icon}  {b['heading']}".strip()

        body_top = _badge_heading(svg, i, heading, color, y)
        body_h = _measure(b)
        box_h = body_h + 2 * BOX_PAD
        svg.rect(PAD_X, body_top, CONTENT_W, box_h, fill=box_bg, stroke=color,
                  sw=1.5, rx=12, dash=dash)

        cy = body_top + BOX_PAD
        cx = PAD_X + BOX_PAD
        if kind == "overview":
            cy = svg.para(cx, cy + 16, lo.get("concept_overview", ""), inner_w,
                           size=15.5, lh=23, fill=INK, weight="normal", style="italic")
            objs = lo.get("objectives") or []
            if objs:
                cy += 8
                cy = svg.bullets(cx, cy + 16, objs, inner_w, size=14, lh=20,
                                  fill=SUBINK, marker="🎯")
        elif kind == "section":
            s = b["data"]
            cy = _formula_box(svg, cx, cy, inner_w, s.get("formula") or {})
            cy = svg.bullets(cx, cy + 16, s.get("points") or [], inner_w,
                              size=14.5, lh=21, fill=SUBINK)
        elif kind == "terms":
            for t in lo.get("key_terms") or []:
                term = str(t.get("term", "")).strip()
                definition = str(t.get("definition", "")).strip()
                line = f"{term}: {definition}"
                wrapped = _wrap(line, _chars_for(inner_w, 14))
                svg.text(cx, cy + 16, wrapped[0], size=14, fill=INK, weight="bold")
                cy += 20
                for cont in wrapped[1:]:
                    svg.text(cx, cy + 16, cont, size=14, fill=INK)
                    cy += 20
                if t.get("example"):
                    ex_lines = _wrap(f"Ví dụ: {t['example']}", _chars_for(inner_w - 16, 12.5))
                    for ln in ex_lines:
                        svg.text(cx + 16, cy + 14, ln, size=12.5, fill="#6b7280", style="italic")
                        cy += 18
                cy += 4
        elif kind == "notes":
            items = list(notes["real_life"])
            items += [f"{m.get('wrong','')} → thực ra: {m.get('correct','')}"
                       for m in notes["misconceptions"]]
            items += list(notes["memory_hooks"])
            cy = svg.bullets(cx, cy + 16, items, inner_w, size=14, lh=20, fill=SUBINK)
        elif kind == "review":
            cy = svg.bullets(cx, cy + 16, lo.get("quick_review") or [], inner_w,
                              size=15, lh=23, fill="#78350f", marker="⭐")

        y = body_top + box_h + GAP

    svg.parts.append("</svg>")
    header = (f'<svg width="{WIDTH}" height="{total_h:.1f}" '
              f'viewBox="0 0 {WIDTH} {total_h:.1f}" xmlns="http://www.w3.org/2000/svg">')
    return header + "".join(svg.parts)
