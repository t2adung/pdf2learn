# -*- coding: utf-8 -*-
"""Stage 4 (v2): Hình minh hoạ.

Chiến lược: ĐÍNH KÈM NGUYÊN TRANG SÁCH (không cắt hình), 0 token.
- Với mỗi topic, render TỪNG TRANG trong page range ra ảnh PNG (nguyên trạng
  trang sách — hợp cho cả sách scan lẫn sách chữ).
- Gắn mỗi trang vào ĐÚNG MỤC nội dung: khớp text của trang với heading/points
  của từng section (`_match_section`, 0 token). Trang không có text layer
  (sách scan) -> rơi về ánh xạ THEO THỨ TỰ (trang đầu ~ mục đầu...).
- render_markdown chèn ảnh trang vào đúng mục "Nội dung chính" theo
  `section_index`; mục "🖼️ Hình minh hoạ" cuối bài chỉ còn ảnh mindmap.
- Nếu topic không có mindmap -> chỉ có ảnh trang.

Naming convention (deterministic, sinh bằng code): {topic_slug}_{nn}.{ext}
"""
import re

import fitz

from mindmap_svg import to_svg, _validate
from utils import log, warn

PAGE_DPI = 130           # độ phân giải render nguyên trang (khi --dpi = 0)
MAX_PAGE_IMAGES = 16     # trần an toàn nếu page range bị đặt quá rộng

# Từ dừng: bỏ khi so khớp trang <-> mục để tránh khớp giả theo từ vô nghĩa.
_STOP = {
    "và", "là", "của", "các", "một", "những", "cho", "với", "trong", "khi",
    "được", "có", "này", "đó", "đây", "như", "về", "đến", "hay", "hoặc", "thì",
    "mà", "ở", "ra", "vào", "theo", "trên", "dưới", "cũng", "nên", "rất", "hơn",
    "hình", "ảnh", "sơ", "đồ", "bảng", "biểu", "vẽ", "minh", "hoạ", "lược",
    "trang", "the", "and", "for", "of", "to", "a", "in", "is", "on",
}


def _content_words(text: str) -> set:
    """Tập từ nội dung (đã bỏ từ dừng/số) để so khớp trang <-> mục."""
    toks = re.findall(r"[^\W\d_]+", (text or "").lower(), re.UNICODE)
    return {t for t in toks if len(t) >= 2 and t not in _STOP}


def _match_section(text: str, sections: list) -> int:
    """Gán trang vào mục khớp nhất theo text. Trả index mục, hoặc -1 nếu không
    khớp (vd trang scan không có text layer). 0 token."""
    if not sections:
        return -1
    tw = _content_words(text)
    if not tw:
        return -1
    best_i, best = -1, 0
    for i, s in enumerate(sections):
        sw = _content_words((s.get("heading", "") + " "
                             + " ".join(s.get("points") or [])))
        if not sw:
            continue
        score = len(tw & sw)
        if score > best:
            best, best_i = score, i
    return best_i if best >= 1 else -1


def _render_pages(doc: fitz.Document, page_start: int, page_end: int,
                  sections: list, dpi: int = 0) -> list:
    """Render nguyên từng trang [page_start..page_end] -> list
    {data, page, section_index}. Gán mục theo text, fallback theo thứ tự trang."""
    last = len(doc)
    ps = max(1, min(page_start, last))
    pe = max(ps, min(page_end, last))
    pages = list(range(ps, pe + 1))[:MAX_PAGE_IMAGES]
    n_sec = len(sections)
    out = []
    for idx, pno in enumerate(pages):
        page = doc[pno - 1]
        try:
            if dpi and dpi > 0:
                pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
            else:
                pix = page.get_pixmap(dpi=PAGE_DPI)
            data = pix.tobytes("png")
        except Exception as e:
            warn(f"render trang {pno} lỗi ({e}), bỏ qua.")
            continue
        si = _match_section(page.get_text() or "", sections)
        if si < 0 and n_sec > 0:
            # không có text (scan) hoặc không khớp -> ánh xạ theo thứ tự trang
            si = min(n_sec - 1, (idx * n_sec) // max(1, len(pages)))
        out.append({"data": data, "page": pno, "section_index": si})
    return out


def _mindmap_svg(row: dict, content_entry: dict, images_dir, seq: int):
    """Vẽ mindmap từ Learning Object bằng code. Trả về entry ảnh hoặc None. 0 token."""
    mm = (content_entry or {}).get("mindmap")
    if not mm:
        return None
    warns = _validate(mm)
    for w in warns:
        warn(f"{row['topic_slug']}: {w}")
    if any(w.startswith("mindmap: thiếu") for w in warns):
        return None
    try:
        svg = to_svg(mm, row["topic_title"])
    except Exception as e:
        warn(f"{row['topic_slug']}: vẽ mindmap lỗi ({e}), topic không có hình.")
        return None
    fname = f"{row['topic_slug']}_{seq:02d}.svg"
    (images_dir / fname).write_text(svg, encoding="utf-8")
    return {"file": fname, "caption": f"Sơ đồ tư duy: {row['topic_title']}",
            "source": "code_mindmap"}


def generate_images_one(doc, row: dict, content_entry: dict, client, images_dir,
                        book_images: bool = False, page_dpi: int = 0) -> list:
    """Sinh danh sách ảnh cho MỘT topic.

    book_images=False (MẶC ĐỊNH): chỉ vẽ mindmap SVG bằng code (0 token).
    book_images=True: đính kèm NGUYÊN TRANG sách (render từng trang) + gán mỗi
      trang vào đúng mục nội dung bằng code (0 token — KHÔNG gọi AI).
    page_dpi>0: render grayscale ở dpi đó (gọn cho sách scan); 0 = màu PAGE_DPI."""
    images_dir.mkdir(parents=True, exist_ok=True)
    slug = row["topic_slug"]
    kept = []
    if book_images:
        secs = (content_entry or {}).get("sections") or []
        pages = _render_pages(doc, row["page_start"], row["page_end"],
                              secs, dpi=page_dpi)
        for pg in pages:
            si = pg["section_index"]
            if 0 <= si < len(secs) and (secs[si].get("heading") or "").strip():
                cap = f"Trang {pg['page']} — {secs[si]['heading'].strip()}"
            else:
                cap = f"Trang {pg['page']} trong sách"
            fname = f"{slug}_{len(kept) + 1:02d}.png"
            (images_dir / fname).write_bytes(pg["data"])
            kept.append({"file": fname, "caption": cap,
                         "source": f"pdf_page_{pg['page']}", "section_index": si})
        if pages:
            placed = sum(1 for k in kept if k["section_index"] >= 0)
            log(f"   [images ] đính {len(pages)} trang sách (nguyên trang, "
                f"{placed} gắn đúng mục) — 0 token.")
    # Mindmap luôn được vẽ THÊM (0 token) — kể cả khi đã có ảnh trang,
    # vì sơ đồ tư duy tóm tắt bài có giá trị ôn tập riêng.
    mm_entry = _mindmap_svg(row, content_entry, images_dir, seq=len(kept) + 1)
    if mm_entry:
        if not kept:
            reason = ("chỉ dùng mindmap SVG (mặc định)" if not book_images
                      else "không render được trang sách, vẽ mindmap")
            log(f"   [images ] {reason} bằng code (0 token).")
        kept.append(mm_entry)
    return kept
