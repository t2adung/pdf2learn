# -*- coding: utf-8 -*-
"""Stage 4 (v3): Hình minh hoạ.

Hai nguồn ảnh ĐỘC LẬP, có thể bật/tắt riêng:
1. Infographic "tổng hợp kiến thức" — vẽ THUẦN CODE (SVG) từ chính Learning
   Object (concept_overview/sections+formula/quick_review, xem
   infographic_svg.py). 0 token, mặc định BẬT — đây là ảnh chính của topic.
2. Ảnh gốc trích từ trang PDF (PyMuPDF) -> AI vision lọc bỏ logo/trang trí,
   giữ ảnh có giá trị minh hoạ. Chỉ chạy khi bật --book-images (mặc định TẮT,
   tốn thêm 1 request img_filter/topic).

Naming convention (deterministic, sinh bằng code): {topic_slug}_{nn}.{ext}
"""
import fitz

from infographic_svg import render as render_infographic
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


def _infographic(row: dict, content_entry: dict, images_dir, seq: int):
    """Vẽ infographic tổng hợp kiến thức bằng code. Trả về entry ảnh hoặc None.
    0 token, không bao giờ lỗi cú pháp (SVG do code sinh, không phải AI)."""
    try:
        svg = render_infographic(content_entry or {}, row["topic_title"])
    except ValueError:
        return None  # Learning Object rỗng (vd cache v1 cũ) -> không có gì để vẽ
    fname = f"{row['topic_slug']}_{seq:02d}.svg"
    (images_dir / fname).write_text(svg, encoding="utf-8")
    return {"file": fname, "caption": f"Tổng hợp kiến thức: {row['topic_title']}",
            "source": "code_infographic"}


def generate_images_one(doc, row: dict, content_entry: dict, client, images_dir,
                        book_images: bool = False, infographic: bool = True) -> list:
    """Sinh danh sách ảnh cho MỘT topic.

    infographic=True (MẶC ĐỊNH): vẽ ảnh tổng hợp kiến thức bằng code (0 token).
    book_images=False (MẶC ĐỊNH): không trích + không gọi AI lọc ảnh trang
      sách -> tiết kiệm 1 request img_filter/topic.
    book_images=True: bật thêm trích ảnh gốc + AI lọc."""
    images_dir.mkdir(parents=True, exist_ok=True)
    slug = row["topic_slug"]
    kept = []
    if infographic:
        info_entry = _infographic(row, content_entry, images_dir, seq=1)
        if info_entry:
            kept.append(info_entry)
    if not book_images:
        return kept
    cands = _extract_candidates(doc, row["page_start"], row["page_end"])
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
    return kept
