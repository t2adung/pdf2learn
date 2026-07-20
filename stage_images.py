# -*- coding: utf-8 -*-
"""Stage 4 (v3): Hình minh hoạ.

Trích ảnh gốc từ chính các trang PDF của topic (PyMuPDF) -> AI vision lọc bỏ
logo/trang trí, giữ ảnh có giá trị minh hoạ, kèm caption. Chỉ chạy khi bật
--book-images; mặc định TẮT (xem generate_images_one).

v3 bỏ fallback vẽ sơ đồ tư duy (mindmap) bằng code — nội dung sinh động hơn
giờ nằm trong chính Learning Object (concept_overview/formula/quick_review,
xem stage_content.py), không cần ảnh thay thế nữa.

Naming convention (deterministic, sinh bằng code): {topic_slug}_{nn}.{ext}
"""
import fitz

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


def generate_images_one(doc, row: dict, client, images_dir,
                        book_images: bool = False) -> list:
    """Sinh danh sách ảnh cho MỘT topic.

    book_images=False (MẶC ĐỊNH): không trích + không gọi AI lọc ảnh trang
      sách -> topic không có ảnh, tiết kiệm 1 request img_filter/topic.
    book_images=True: bật trích ảnh gốc + AI lọc."""
    images_dir.mkdir(parents=True, exist_ok=True)
    slug = row["topic_slug"]
    kept = []
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
