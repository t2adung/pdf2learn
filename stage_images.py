# -*- coding: utf-8 -*-
"""Stage 4 (v2): Hình minh hoạ.

Thứ tự ưu tiên (chính xác kiến thức là trên hết):
1. Trích ảnh gốc từ chính các trang PDF của topic (PyMuPDF) -> AI vision lọc bỏ
   logo/trang trí, giữ ảnh có giá trị minh hoạ, kèm caption.
2. Nếu topic không có ảnh dùng được -> vẽ SƠ ĐỒ TƯ DUY bằng CODE từ field
   `mindmap` trong Learning Object (mindmap_svg.to_svg — 0 token, không bao giờ
   lỗi cú pháp). v1 từng nhờ AI sinh SVG: -1 request/topic, và hết rủi ro SVG hỏng.

Naming convention (deterministic, sinh bằng code): {topic_slug}_{nn}.{ext}
"""
import fitz

from mindmap_svg import to_svg, _validate
from utils import log, warn

MIN_DIM = 160          # bỏ ảnh quá nhỏ (icon, bullet trang trí)
MIN_BYTES = 6 * 1024
MAX_CANDIDATES = 6     # tối đa gửi AI lọc mỗi topic

FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "keep": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "caption": {"type": "string"},
            },
            "required": ["index", "caption"],
        }},
    },
    "required": ["keep"],
}

FILTER_PROMPT = """Các ảnh đính kèm được trích từ trang sách của bài học: "{topic_title}".
Chọn những ảnh CÓ GIÁ TRỊ MINH HOẠ KIẾN THỨC (sơ đồ, biểu đồ, hình vẽ khoa học, ảnh chụp minh hoạ khái niệm).
LOẠI BỎ: logo, hoạ tiết trang trí, ảnh nền, icon, ảnh mờ/vô nghĩa.
Với mỗi ảnh giữ lại, viết caption ngắn gọn bằng ngôn ngữ của bài học (index tính từ 0 theo thứ tự ảnh đính kèm).
Nếu không ảnh nào đáng giữ, trả về keep = []."""


def _extract_candidates(doc: fitz.Document, page_start: int, page_end: int) -> list:
    """Trả về list {data, ext, mime, page}. Dedup theo xref."""
    seen, out = set(), []
    for pno in range(page_start - 1, page_end):
        for info in doc[pno].get_images(full=True):
            xref = info[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                img = doc.extract_image(xref)
            except Exception:
                continue
            ext, data = img["ext"], img["image"]
            if img["width"] < MIN_DIM or img["height"] < MIN_DIM or len(data) < MIN_BYTES:
                continue
            if ext not in ("png", "jpg", "jpeg"):
                # định dạng lạ (jpx, jb2, tiff...) -> convert sang PNG
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3:  # CMYK -> RGB
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    data, ext = pix.tobytes("png"), "png"
                except Exception:
                    continue
            mime = "image/png" if ext == "png" else "image/jpeg"
            out.append({"data": data, "ext": "png" if ext == "png" else "jpg",
                        "mime": mime, "page": pno + 1})
            if len(out) >= MAX_CANDIDATES:
                return out
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


def generate_images_one(doc, row: dict, content_entry: dict, client, images_dir) -> list:
    """Sinh danh sách ảnh cho MỘT topic."""
    images_dir.mkdir(parents=True, exist_ok=True)
    slug = row["topic_slug"]
    cands = _extract_candidates(doc, row["page_start"], row["page_end"])
    kept = []
    if cands:
        log(f"   [images ] {len(cands)} ảnh ứng viên, nhờ AI lọc...")
        parts = [{"text": FILTER_PROMPT.format(topic_title=row["topic_title"])}]
        for c in cands:
            parts.append(client.image_part(c["data"], c["mime"]))
        try:
            res = client.generate_json(parts, FILTER_SCHEMA, tag="img_filter")
            for k in res.get("keep", []):
                i = k["index"]
                if 0 <= i < len(cands):
                    c = cands[i]
                    fname = f"{slug}_{len(kept)+1:02d}.{c['ext']}"
                    (images_dir / fname).write_bytes(c["data"])
                    kept.append({"file": fname, "caption": k["caption"],
                                 "source": f"pdf_page_{c['page']}"})
        except Exception as e:
            warn(f"{slug}: lọc ảnh lỗi ({e}), bỏ qua ảnh PDF.")
    # Mindmap luôn được vẽ THÊM (0 token) — kể cả khi đã có ảnh gốc,
    # vì sơ đồ tư duy tóm tắt bài có giá trị ôn tập riêng.
    mm_entry = _mindmap_svg(row, content_entry, images_dir, seq=len(kept) + 1)
    if mm_entry:
        if not kept:
            log("   [images ] không có ảnh gốc dùng được, vẽ mindmap bằng code (0 token).")
        kept.append(mm_entry)
    return kept
