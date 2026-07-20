# -*- coding: utf-8 -*-
"""Stage 4 (v5): Hình minh hoạ.

Hai nguồn ảnh ĐỘC LẬP, có thể bật/tắt riêng:
1. Infographic "tổng hợp kiến thức" — dựng HTML/CSS THUẦN CODE từ Learning
   Object (xem infographic_html.py), rồi chụp thành PNG bằng headless
   Chromium (xem html_render.py). 0 token AI, deterministic, KHÔNG BAO GIỜ
   sai chính tả (chữ là text HTML thật). Mặc định BẬT — đây là ảnh chính
   của topic. Dependency Playwright là TUỲ CHỌN: chưa cài thì tự bỏ qua ảnh
   này (cảnh báo 1 lần), không sập pipeline.
   (v4 từng gọi model sinh ảnh — bị lỗi chính tả tiếng Việt trong ảnh, đã
   revert. Trước nữa là vẽ SVG tay — bố cục đúng nhưng phải tự tính word-
   wrap; HTML/CSS để trình duyệt lo việc đó, đỡ code hơn hẳn.)
2. Ảnh gốc trích từ trang PDF (PyMuPDF) -> AI vision lọc bỏ logo/trang trí,
   giữ ảnh có giá trị minh hoạ. Chỉ chạy khi bật --book-images (mặc định TẮT,
   tốn thêm 1 request img_filter/topic).

Naming convention (deterministic, sinh bằng code): {topic_slug}_{nn}.{ext}
"""
import fitz

from infographic_html import render as render_infographic_html
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
    lấy vào sẽ chiếm hết chỗ và không có giá trị trên infographic."""
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


def _infographic(row: dict, content_entry: dict, renderer, images_dir):
    """Dựng HTML (THUẦN CODE, 0 dependency) rồi chụp PNG bằng headless
    Chromium NẾU renderer khả dụng. Trả về entry ảnh (PNG) hoặc None.

    File .html LUÔN được ghi ra đĩa nếu có nội dung — kể cả khi chưa cài
    Playwright (renderer=None) hoặc chụp PNG lỗi — để dùng thủ công/làm tư
    liệu cho frontend nhúng HTML trực tiếp sau này. Chỉ phần PNG (dùng làm
    "ảnh" cho topics.csv/manifest.json) mới cần renderer."""
    try:
        html = render_infographic_html(content_entry or {}, row["topic_title"])
    except ValueError:
        return None  # Learning Object rỗng (vd cache v1 cũ) -> không có gì để vẽ
    slug = row["topic_slug"]
    (images_dir / f"{slug}_infographic.html").write_text(html, encoding="utf-8")
    if renderer is None:
        return None
    try:
        png = renderer.render_png(html)
    except Exception as e:
        warn(f"{slug}: render PNG infographic lỗi ({e}) — vẫn giữ file .html.")
        return None
    fname = f"{slug}_infographic.png"
    (images_dir / fname).write_bytes(png)
    return {"file": fname, "caption": f"Tổng hợp kiến thức: {row['topic_title']}",
            "source": "code_infographic_html"}


def generate_images_one(doc, row: dict, content_entry: dict, client, images_dir,
                        book_images: bool = False, infographic: bool = True,
                        renderer=None) -> list:
    """Sinh danh sách ảnh cho MỘT topic.

    infographic=True (MẶC ĐỊNH): dựng + chụp 1 poster tổng hợp kiến thức từ
      Learning Object bằng HTML/CSS (0 token, deterministic). renderer:
      HtmlRenderer dùng chung cho cả lần chạy (xem main.py) — None (vd chưa
      cài Playwright) thì tự bỏ qua ảnh này, không lỗi.
    book_images=False (MẶC ĐỊNH): không trích + không gọi AI lọc ảnh trang
      sách -> tiết kiệm 1 request img_filter/topic.
    book_images=True: trích thêm ảnh gốc từ PDF + AI lọc, LIỆT KÊ RIÊNG."""
    images_dir.mkdir(parents=True, exist_ok=True)
    slug = row["topic_slug"]
    kept = []
    if infographic:
        info_entry = _infographic(row, content_entry, renderer, images_dir)
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
