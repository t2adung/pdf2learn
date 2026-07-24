# -*- coding: utf-8 -*-
"""Stage 4 (v4): Hình minh hoạ.

Hai nguồn ảnh ĐỘC LẬP, có thể bật/tắt riêng:
1. Sơ đồ tư duy ("mindmap") — dựng SVG THUẦN CODE từ field `mindmap` của
   Learning Object (xem mindmap_svg.py). 0 token AI, 0 dependency ngoài,
   deterministic, KHÔNG BAO GIỜ lỗi cú pháp (SVG do code sinh, không phải AI).
   Mặc định BẬT — đây là ảnh chính của topic. Ghi ra file .svg trong images/.
   (v4 quay lại mindmap SVG. v3 từng dựng infographic HTML/CSS rồi chụp PNG
   bằng headless Chromium — nay bibeli tự lo phần hiển thị sinh động bằng HTML
   nên pipeline không cần dựng HTML/PNG nữa, bỏ luôn dependency Playwright.)
2. Ảnh gốc trích từ trang PDF (PyMuPDF) -> AI vision lọc bỏ logo/trang trí,
   giữ ảnh có giá trị minh hoạ. Chỉ chạy khi bật --book-images (mặc định TẮT,
   tốn thêm 1 request img_filter/topic).

Naming convention (deterministic, sinh bằng code): {topic_slug}_{nn}.{ext}
"""
import fitz

from mindmap_svg import to_svg, _validate
from utils import log, warn

MIN_DIM = 160          # bỏ ảnh quá nhỏ (icon, bullet trang trí)
MIN_BYTES = 6 * 1024
MAX_CANDIDATES = 6     # tối đa gửi AI lọc mỗi topic
MAX_PAGE_COVERAGE = 0.85   # bỏ ảnh chiếm > 85% diện tích trang (scan cả trang, không phải minh hoạ)

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
    """Trả về list {data, ext, mime, page, w, h}. Dedup theo xref.

    Bỏ ảnh chiếm gần trọn trang (MAX_PAGE_COVERAGE): sách scan thường nhúng
    CẢ TRANG như 1 ảnh duy nhất -> đó là ảnh nền/scan, không phải minh hoạ,
    lấy vào sẽ chiếm hết chỗ và không có giá trị."""
    seen, out = set(), []
    for pno in range(page_start - 1, page_end):
        page = doc[pno]
        page_area = page.rect.width * page.rect.height
        for info in page.get_images(full=True):
            xref = info[0]
            if xref in seen:
                continue
            seen.add(xref)
            rects = page.get_image_rects(xref)
            if rects and page_area > 0:
                coverage = max(r.width * r.height for r in rects) / page_area
                if coverage > MAX_PAGE_COVERAGE:
                    continue
            try:
                img = doc.extract_image(xref)
            except Exception:
                continue
            ext, data = img["ext"], img["image"]
            w, h = img["width"], img["height"]
            if w < MIN_DIM or h < MIN_DIM or len(data) < MIN_BYTES:
                continue
            if ext not in ("png", "jpg", "jpeg"):
                # định dạng lạ (jpx, jb2, tiff...) -> convert sang PNG
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3:  # CMYK -> RGB
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    data, ext, w, h = pix.tobytes("png"), "png", pix.width, pix.height
                except Exception:
                    continue
            mime = "image/png" if ext == "png" else "image/jpeg"
            out.append({"data": data, "ext": "png" if ext == "png" else "jpg",
                        "mime": mime, "page": pno + 1, "w": w, "h": h})
            if len(out) >= MAX_CANDIDATES:
                return out
    return out


def _mindmap_svg(row: dict, content_entry: dict, images_dir):
    """Vẽ sơ đồ tư duy từ field `mindmap` của Learning Object bằng code.
    Trả về entry ảnh (.svg) hoặc None. 0 token, 0 dependency ngoài."""
    mm = (content_entry or {}).get("mindmap")
    if not mm:
        return None
    slug = row["topic_slug"]
    for w in _validate(mm):
        warn(f"{slug}: {w}")
        if w.startswith("mindmap: thiếu"):
            return None
    try:
        svg = to_svg(mm, row["topic_title"])
    except Exception as e:
        warn(f"{slug}: vẽ mindmap lỗi ({e}), topic không có ảnh mindmap.")
        return None
    fname = f"{slug}_mindmap.svg"
    (images_dir / fname).write_text(svg, encoding="utf-8")
    return {"file": fname, "caption": f"Sơ đồ tư duy: {row['topic_title']}",
            "source": "code_mindmap"}


def generate_images_one(doc, row: dict, content_entry: dict, client, images_dir,
                        book_images: bool = False, mindmap: bool = True) -> list:
    """Sinh danh sách ảnh cho MỘT topic.

    mindmap=True (MẶC ĐỊNH): vẽ 1 sơ đồ tư duy SVG từ Learning Object bằng code
      (0 token, deterministic, 0 dependency). Đây là ảnh chính của topic.
    book_images=False (MẶC ĐỊNH): không trích + không gọi AI lọc ảnh trang
      sách -> tiết kiệm 1 request img_filter/topic.
    book_images=True: trích thêm ảnh gốc từ PDF + AI lọc, LIỆT KÊ RIÊNG."""
    images_dir.mkdir(parents=True, exist_ok=True)
    slug = row["topic_slug"]
    kept = []
    if mindmap:
        mm_entry = _mindmap_svg(row, content_entry, images_dir)
        if mm_entry:
            kept.append(mm_entry)
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
