# -*- coding: utf-8 -*-
"""mindmap_svg.py — Sinh sơ đồ tư duy từ cây dữ liệu. THUẦN CODE, 0 token AI.

Triết lý: cái gì code làm được deterministic thì đừng trả token cho nó.
AI chỉ trả về CÂY DỮ LIỆU {root, branches:[{label, children:[...]}]};
cú pháp SVG/Mermaid do code sinh => không bao giờ lỗi parse.

Layout: tia ngang 3 cột.
    [root]  ──┬── [branch 1] ──┬── child
              │                └── child
              ├── [branch 2] ──── child
              └── ...
Chiều rộng hộp ước lượng theo số ký tự (không có engine đo font).
"""
import re
from xml.sax.saxutils import escape

# ---- hằng số layout ----
FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
FS_ROOT, FS_BRANCH, FS_CHILD = 17, 15, 13
CH_W_ROOT, CH_W_BRANCH, CH_W_CHILD = 9.4, 8.2, 7.0   # px/ký tự (ước lượng)
PAD_X = 18            # padding ngang trong hộp
H_ROOT, H_BRANCH, H_CHILD = 48, 44, 38
GAP_COL = 56          # khoảng cách giữa các cột
GAP_ROW = 12          # khoảng cách dọc giữa 2 child
GAP_BRANCH = 22       # khoảng cách dọc giữa 2 nhóm branch
MARGIN = 24
MAX_W_BRANCH, MAX_W_CHILD = 230, 260

# Bảng màu nhạt, tương phản tốt, in đen trắng vẫn đọc được.
PALETTE = [
    ("#E8EAF6", "#3949AB", "#1A237E"),   # indigo (brand bibeli)
    ("#E0F2F1", "#00897B", "#004D40"),   # teal
    ("#FFF3E0", "#EF6C00", "#E65100"),   # amber
    ("#FCE4EC", "#C2185B", "#880E4F"),   # pink
    ("#E8F5E9", "#43A047", "#1B5E20"),   # green
    ("#EDE7F6", "#5E35B1", "#311B92"),   # deep purple
]
ROOT_COLOR = ("#3949AB", "#283593", "#FFFFFF")   # fill, stroke, text


def _text_w(s: str, ch_w: float) -> float:
    return len(s) * ch_w


def _box_w(s: str, ch_w: float, cap: float) -> float:
    return min(cap, _text_w(s, ch_w) + 2 * PAD_X)


def _wrap(s: str, ch_w: float, max_w: float) -> list:
    """Ngắt dòng theo từ để vừa max_w. Trả về list dòng (tối đa 2)."""
    if _text_w(s, ch_w) + 2 * PAD_X <= max_w:
        return [s]
    words, lines, cur = s.split(), [], ""
    limit = max_w - 2 * PAD_X
    for w in words:
        trial = f"{cur} {w}".strip()
        if _text_w(trial, ch_w) <= limit or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > 2:                       # cắt cụt, thêm dấu …
        lines = lines[:2]
        lines[1] = lines[1][:-1] + "…"
    return lines


def _esc(s: str) -> str:
    return escape(s.strip())


def _clean_label(s: str) -> str:
    """Bỏ ký tự thừa. Không đụng dấu tiếng Việt."""
    return re.sub(r"\s+", " ", s).strip(" .;:,")


def to_mermaid(mm: dict) -> str:
    """Dự phòng: sinh chuỗi mermaid nếu về sau frontend hỗ trợ.
    Vì code sinh chứ không phải AI => không bao giờ lỗi cú pháp."""
    def c(s):
        return re.sub(r"[()\[\]{},:;#\"'`]", "", _clean_label(s))
    lines = ["mindmap", f"  root(({c(mm['root'])}))"]
    for b in mm.get("branches", []):
        lines.append(f"    {c(b['label'])}")
        lines += [f"      {c(x)}" for x in b.get("children", [])]
    return "\n".join(lines)


def _validate(mm: dict) -> list:
    """Kiểm tra cây. Trả về list cảnh báo (rỗng = ổn). 0 token."""
    warns = []
    if not isinstance(mm, dict) or not mm.get("root"):
        return ["mindmap: thiếu 'root'"]
    br = mm.get("branches") or []
    if not (2 <= len(br) <= 6):
        warns.append(f"mindmap: {len(br)} nhánh (nên 3-5)")
    for b in br:
        if not b.get("label"):
            warns.append("mindmap: nhánh thiếu label")
            continue
        n = len(b.get("children") or [])
        if n > 5:
            warns.append(f"mindmap: nhánh '{b['label']}' có {n} con (nên <=4)")
        if len(b["label"].split()) > 7:
            warns.append(f"mindmap: label quá dài '{b['label']}'")
    return warns


def to_svg(mm: dict, title: str = "") -> str:
    """Cây -> SVG hoàn chỉnh. Không phụ thuộc thư viện ngoài."""
    root = _clean_label(mm["root"])
    branches = [b for b in (mm.get("branches") or []) if b.get("label")]
    if not branches:
        raise ValueError("mindmap không có nhánh nào")

    # --- đo cột ---
    root_w = _box_w(root, CH_W_ROOT, 300)
    b_labels = [_clean_label(b["label"]) for b in branches]
    branch_w = max(_box_w(s, CH_W_BRANCH, MAX_W_BRANCH) for s in b_labels)

    all_children = [[_clean_label(c) for c in (b.get("children") or [])]
                    for b in branches]
    flat = [c for cs in all_children for c in cs]
    child_w = max((_box_w(s, CH_W_CHILD, MAX_W_CHILD) for s in flat),
                  default=140.0)

    x_root = MARGIN
    x_branch = x_root + root_w + GAP_COL
    x_child = x_branch + branch_w + GAP_COL
    total_w = x_child + child_w + MARGIN

    # --- đo dòng: mỗi branch chiếm chiều cao = max(H_BRANCH, tổng con) ---
    def child_block_h(n):
        return n * H_CHILD + max(0, n - 1) * GAP_ROW

    heights = [max(H_BRANCH, child_block_h(len(cs))) for cs in all_children]
    total_h = sum(heights) + GAP_BRANCH * (len(branches) - 1) + 2 * MARGIN

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" '
        f'height="{total_h:.0f}" viewBox="0 0 {total_w:.0f} {total_h:.0f}" '
        f'font-family="{FONT}" role="img">',
        f"<title>Sơ đồ tư duy: {_esc(title or root)}</title>",
        f'<rect width="{total_w:.0f}" height="{total_h:.0f}" fill="#FFFFFF"/>',
    ]

    y_cursor = MARGIN
    y_root = total_h / 2
    connectors, boxes = [], []

    for i, (b, children) in enumerate(zip(branches, all_children)):
        blk_h = heights[i]
        y_b = y_cursor + blk_h / 2
        fill, stroke, txt = PALETTE[i % len(PALETTE)]

        # nối root -> branch (đường cong bezier ngang)
        connectors.append(
            f'<path d="M{x_root + root_w:.0f},{y_root:.0f} '
            f'C{x_root + root_w + GAP_COL * 0.6:.0f},{y_root:.0f} '
            f'{x_branch - GAP_COL * 0.6:.0f},{y_b:.0f} '
            f'{x_branch:.0f},{y_b:.0f}" fill="none" stroke="{stroke}" '
            f'stroke-width="2" opacity="0.65"/>')

        boxes.append(_box(x_branch, y_b - H_BRANCH / 2, branch_w, H_BRANCH,
                          _clean_label(b["label"]), fill, stroke, txt,
                          FS_BRANCH, CH_W_BRANCH, bold=True))

        # con
        cy = y_b - child_block_h(len(children)) / 2
        for c in children:
            cy_mid = cy + H_CHILD / 2
            connectors.append(
                f'<path d="M{x_branch + branch_w:.0f},{y_b:.0f} '
                f'C{x_branch + branch_w + GAP_COL * 0.6:.0f},{y_b:.0f} '
                f'{x_child - GAP_COL * 0.6:.0f},{cy_mid:.0f} '
                f'{x_child:.0f},{cy_mid:.0f}" fill="none" stroke="{stroke}" '
                f'stroke-width="1.4" opacity="0.5"/>')
            boxes.append(_box(x_child, cy, child_w, H_CHILD, c,
                              "#FFFFFF", stroke, "#333333",
                              FS_CHILD, CH_W_CHILD, bold=False))
            cy += H_CHILD + GAP_ROW

        y_cursor += blk_h + GAP_BRANCH

    # root vẽ sau connector để nằm trên
    parts += connectors
    rf, rs, rt = ROOT_COLOR
    parts.append(_box(x_root, y_root - H_ROOT / 2, root_w, H_ROOT, root,
                      rf, rs, rt, FS_ROOT, CH_W_ROOT, bold=True))
    parts += boxes
    parts.append("</svg>")
    return "\n".join(parts)


def _box(x, y, w, h, label, fill, stroke, text_color, fs, ch_w, bold):
    lines = _wrap(label, ch_w, w)
    weight = "600" if bold else "400"
    out = [f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" '
           f'rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>']
    if len(lines) == 1:
        out.append(f'<text x="{x + w/2:.0f}" y="{y + h/2:.0f}" fill="{text_color}" '
                   f'font-size="{fs}" font-weight="{weight}" text-anchor="middle" '
                   f'dominant-baseline="central">{_esc(lines[0])}</text>')
    else:
        dy = fs * 1.15
        y0 = y + h / 2 - dy / 2
        for k, ln in enumerate(lines):
            out.append(f'<text x="{x + w/2:.0f}" y="{y0 + k*dy:.0f}" fill="{text_color}" '
                       f'font-size="{fs - 1}" font-weight="{weight}" text-anchor="middle" '
                       f'dominant-baseline="central">{_esc(ln)}</text>')
    return "".join(out)
