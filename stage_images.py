# -*- coding: utf-8 -*-
"""Stage 4 (v2): Hình minh hoạ.

Chiến lược "phần A" — trích hình CHÍNH XÁC theo vị trí + caption thật, 0 token:
1. Với PDF chữ (digital), mỗi hình trong trang được định vị bằng
   `page.get_image_rects(xref)` -> render ĐÚNG VÙNG đó ra PNG
   (`get_pixmap(clip=...)`) nên bắt được cả nhãn/nét vẽ chồng lên ảnh, giống
   hệt như in trên sách.
2. Lấy CAPTION THẬT của sách (dòng "Hình 1.2: ..." ngay dưới/hoặc trên hình)
   thay vì để AI bịa.
3. GÁN MỤC bằng CODE: so khớp caption + đoạn văn quanh hình với heading/points
   của từng section -> `section_index` (render_markdown chèn hình vào đúng mục).
   Toàn bộ khâu này 0 token (không gọi AI).
4. Nếu topic không có hình dùng được -> vẽ SƠ ĐỒ TƯ DUY bằng CODE từ field
   `mindmap` (mindmap_svg.to_svg — 0 token).

Naming convention (deterministic, sinh bằng code): {topic_slug}_{nn}.{ext}
"""
import re

import fitz

from mindmap_svg import to_svg, _validate
from utils import log, warn

MIN_DIM = 160          # bỏ ảnh nguồn quá nhỏ (icon, bullet trang trí)
MIN_BYTES = 6 * 1024
MIN_RECT = 48          # bỏ vùng đặt ảnh quá nhỏ trên trang (pt)
FULLPAGE_RATIO = 0.9   # vùng >= 90% diện tích trang -> coi là nền/scan cả trang, bỏ
MAX_FIGURES = 6        # tối đa mỗi topic
CLIP_DPI = 150         # độ phân giải render vùng hình
CAP_GAP = 40           # khoảng cách tối đa (pt) từ mép hình tới dòng caption
CAP_TIGHT = 14         # dòng ngay sát mép hình -> coi là caption dù không có tiền tố

# Tiền tố caption phổ biến trong SGK tiếng Việt (và tiếng Anh).
CAP_PREFIXES = ("hình", "ảnh", "sơ đồ", "biểu đồ", "bảng", "lược đồ",
                "hình vẽ", "figure", "fig.", "h.")

# Từ dừng: bỏ khi so khớp hình <-> mục để tránh khớp giả theo từ vô nghĩa.
_STOP = {
    "và", "là", "của", "các", "một", "những", "cho", "với", "trong", "khi",
    "được", "có", "này", "đó", "đây", "như", "về", "đến", "hay", "hoặc", "thì",
    "mà", "ở", "ra", "vào", "theo", "trên", "dưới", "cũng", "nên", "rất", "hơn",
    "hình", "ảnh", "sơ", "đồ", "bảng", "biểu", "vẽ", "minh", "hoạ", "lược",
    "the", "and", "for", "of", "to", "a", "in", "is", "on",
}


def _content_words(text: str) -> set:
    """Tập từ nội dung (đã bỏ từ dừng/số) để so khớp hình <-> mục."""
    toks = re.findall(r"[^\W\d_]+", (text or "").lower(), re.UNICODE)
    return {t for t in toks if len(t) >= 2 and t not in _STOP}


def _text_lines(page: fitz.Page) -> list:
    """Danh sách dòng text {x0,y0,x1,y1,text} — dùng dò caption + ngữ cảnh."""
    out = []
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0:            # 0 = text, 1 = image
            continue
        for ln in b.get("lines", []):
            txt = "".join(sp.get("text", "") for sp in ln.get("spans", [])).strip()
            if not txt:
                continue
            x0, y0, x1, y1 = ln["bbox"]
            out.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": txt})
    return out


def _xov(line: dict, rect: fitz.Rect) -> float:
    """Tỉ lệ dòng text phủ ngang lên vùng hình (0..1)."""
    inter = max(0.0, min(line["x1"], rect.x1) - max(line["x0"], rect.x0))
    lw = (line["x1"] - line["x0"]) or 1.0
    return inter / lw


def _clip_caption(txt: str, limit: int = 200) -> str:
    txt = " ".join((txt or "").split()).strip()
    return txt[:limit].rstrip() if len(txt) > limit else txt


def _caption_near(rect: fitz.Rect, lines: list) -> str:
    """Tìm caption THẬT của hình: ưu tiên dòng dưới bắt đầu bằng 'Hình/Ảnh/...'.

    Thứ tự thử: (1) dòng dưới có tiền tố caption; (2) dòng dưới sát mép; (3)
    dòng trên có tiền tố. Không thấy -> trả "" (để code tự đặt caption sau)."""
    below = sorted([l for l in lines
                    if l["y0"] >= rect.y1 - 2 and (l["y0"] - rect.y1) <= CAP_GAP
                    and _xov(l, rect) > 0.15],
                   key=lambda l: l["y0"])
    for i, l in enumerate(below):
        if l["text"].lower().startswith(CAP_PREFIXES):
            txt = l["text"]
            # caption có thể tràn sang dòng kế -> nối nếu sát nhau
            if i + 1 < len(below) and (below[i + 1]["y0"] - l["y1"]) <= 4:
                txt += " " + below[i + 1]["text"]
            return _clip_caption(txt)
    if below and (below[0]["y0"] - rect.y1) <= CAP_TIGHT:
        return _clip_caption(below[0]["text"])
    above = sorted([l for l in lines
                    if l["y1"] <= rect.y0 + 2 and (rect.y0 - l["y1"]) <= CAP_GAP
                    and _xov(l, rect) > 0.15],
                   key=lambda l: rect.y0 - l["y1"])
    for l in above:
        if l["text"].lower().startswith(CAP_PREFIXES):
            return _clip_caption(l["text"])
    return ""


def _context_near(rect: fitz.Rect, lines: list, band: float = 180.0) -> str:
    """Text trong dải quanh hình — làm ngữ cảnh phụ khi gán mục (nếu caption yếu)."""
    near = [l["text"] for l in lines
            if (l["y0"] >= rect.y1 and l["y0"] - rect.y1 <= band)
            or (l["y1"] <= rect.y0 and rect.y0 - l["y1"] <= band)]
    return " ".join(near)


def _match_section(caption: str, context: str, sections: list) -> int:
    """Gán hình vào mục khớp nhất (caption có trọng số cao hơn ngữ cảnh).
    Trả về index mục, hoặc -1 nếu không khớp mục nào. 0 token."""
    if not sections:
        return -1
    cap_w = _content_words(caption)
    ctx_w = _content_words(context)
    best_i, best = -1, 0.0
    for i, s in enumerate(sections):
        sw = _content_words((s.get("heading", "") + " "
                             + " ".join(s.get("points") or [])))
        if not sw:
            continue
        score = 2.0 * len(cap_w & sw) + 1.0 * len(ctx_w & sw)
        if score > best:
            best, best_i = score, i
    return best_i if best >= 1 else -1


def _norm_raster(doc: fitz.Document, xref: int, ex: dict):
    """Chuẩn hoá ảnh trích -> (data, ext, mime). Định dạng lạ -> PNG."""
    ext, data = ex["ext"], ex["image"]
    if ext in ("png", "jpg", "jpeg"):
        e = "png" if ext == "png" else "jpg"
        return data, e, ("image/png" if e == "png" else "image/jpeg")
    try:
        pix = fitz.Pixmap(doc, xref)
        if pix.n - pix.alpha > 3:          # CMYK -> RGB
            pix = fitz.Pixmap(fitz.csRGB, pix)
        return pix.tobytes("png"), "png", "image/png"
    except Exception:
        return None, None, None


def _extract_figures(doc: fitz.Document, page_start: int, page_end: int,
                     dpi: int = CLIP_DPI) -> list:
    """Trích hình theo VÙNG + caption thật. Trả list
    {data, ext, mime, page, caption, context}. Dedup theo xref/trang."""
    figs = []
    for pno in range(page_start - 1, page_end):
        page = doc[pno]
        parea = page.rect.width * page.rect.height or 1.0
        lines = _text_lines(page)
        seen = set()
        for info in page.get_images(full=True):
            xref = info[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                ex = doc.extract_image(xref)
            except Exception:
                continue
            if (ex["width"] < MIN_DIM or ex["height"] < MIN_DIM
                    or len(ex["image"]) < MIN_BYTES):
                continue
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            if not rects:
                # Không lấy được vị trí -> fallback ảnh trích, không caption/mục.
                data, ext, mime = _norm_raster(doc, xref, ex)
                if data:
                    figs.append({"data": data, "ext": ext, "mime": mime,
                                 "page": pno + 1, "caption": "",
                                 "context": page.get_text()})
                    if len(figs) >= MAX_FIGURES:
                        return figs
                continue
            for rect in rects:
                if rect.width < MIN_RECT or rect.height < MIN_RECT:
                    continue
                if (rect.width * rect.height) >= FULLPAGE_RATIO * parea:
                    continue                # gần cả trang -> nền/scan, bỏ
                try:
                    pix = page.get_pixmap(clip=rect, dpi=dpi)
                    data = pix.tobytes("png")
                except Exception:
                    continue
                figs.append({"data": data, "ext": "png", "mime": "image/png",
                             "page": pno + 1,
                             "caption": _caption_near(rect, lines),
                             "context": _context_near(rect, lines)})
                if len(figs) >= MAX_FIGURES:
                    return figs
    return figs


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
                        book_images: bool = False) -> list:
    """Sinh danh sách ảnh cho MỘT topic.

    book_images=False (MẶC ĐỊNH): chỉ vẽ mindmap SVG bằng code (0 token).
    book_images=True: trích hình sách theo VÙNG + caption thật + gán mục bằng
      code (0 token — KHÔNG gọi AI). Ảnh sách được render_markdown chèn vào
      đúng mục nội dung theo section_index; mindmap vẫn được vẽ thêm."""
    images_dir.mkdir(parents=True, exist_ok=True)
    slug = row["topic_slug"]
    kept = []
    if book_images:
        secs = (content_entry or {}).get("sections") or []
        figs = _extract_figures(doc, row["page_start"], row["page_end"])
        for f in figs:
            si = _match_section(f["caption"], f["context"], secs)
            if f["caption"]:
                cap = f["caption"]
            elif 0 <= si < len(secs) and (secs[si].get("heading") or "").strip():
                cap = f"Hình minh hoạ: {secs[si]['heading'].strip()}"
            else:
                cap = f"Hình minh hoạ trong bài (trang {f['page']})"
            fname = f"{slug}_{len(kept) + 1:02d}.{f['ext']}"
            (images_dir / fname).write_bytes(f["data"])
            kept.append({"file": fname, "caption": cap,
                         "source": f"pdf_page_{f['page']}", "section_index": si})
        if figs:
            placed = sum(1 for k in kept if k["section_index"] >= 0)
            log(f"   [images ] {len(figs)} hình trích theo vùng+caption "
                f"({placed} gắn đúng mục) — 0 token.")
    # Mindmap luôn được vẽ THÊM (0 token) — kể cả khi đã có ảnh sách,
    # vì sơ đồ tư duy tóm tắt bài có giá trị ôn tập riêng.
    mm_entry = _mindmap_svg(row, content_entry, images_dir, seq=len(kept) + 1)
    if mm_entry:
        if not kept:
            reason = ("chỉ dùng mindmap SVG (mặc định)" if not book_images
                      else "không có hình sách dùng được, vẽ mindmap")
            log(f"   [images ] {reason} bằng code (0 token).")
        kept.append(mm_entry)
    return kept
