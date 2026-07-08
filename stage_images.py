# -*- coding: utf-8 -*-
"""Stage 4: Hình minh hoạ.

Thứ tự ưu tiên (chính xác kiến thức là trên hết):
1. Trích ảnh gốc từ chính các trang PDF của topic (PyMuPDF) -> AI vision lọc bỏ
   logo/trang trí, giữ ảnh có giá trị minh hoạ, kèm caption.
2. Nếu topic không có ảnh dùng được -> AI sinh SVG diagram từ key_points (fallback).

Naming convention (deterministic, sinh bằng code): {topic_slug}_{nn}.{ext}
"""
import re
from typing import Optional

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

SVG_PROMPT = """Vẽ MỘT sơ đồ SVG minh hoạ trực quan cho bài học "{topic_title}" (trình độ {level}),
dựa trên các ý chính sau:
{key_points}

Yêu cầu:
- Trả về DUY NHẤT mã SVG hợp lệ (bắt đầu bằng <svg, kết thúc bằng </svg>), không giải thích, không markdown.
- Kích thước khoảng 640x400, chữ dùng font-family sans-serif, cỡ chữ >= 13 để dễ đọc.
- Nội dung chữ trong sơ đồ dùng ngôn ngữ của các ý chính ở trên.
- Ưu tiên dạng: sơ đồ khối, sơ đồ phân loại, chu trình, hoặc timeline — chọn dạng phù hợp nội dung.
- Màu sắc nhẹ nhàng, tương phản tốt, phù hợp tài liệu học tập."""


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


def _gen_svg(client, row: dict, key_points: list) -> Optional[str]:
    prompt = SVG_PROMPT.format(topic_title=row["topic_title"], level=row["level"],
                               key_points="\n".join(f"- {k}" for k in key_points[:8]))
    text = client.generate_text([{"text": prompt}], tag="svg_diagram", temperature=0.5)
    m = re.search(r"<svg[\s\S]*?</svg>", text)
    return m.group(0) if m else None


def generate_images_one(doc, row: dict, content_entry: dict, client, images_dir) -> list:
    """Sinh danh sách ảnh cho MỘT topic."""
    images_dir.mkdir(parents=True, exist_ok=True)
    slug = row["topic_slug"]
    if True:
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
        if not kept:
            kps = (content_entry or {}).get("key_points", [])
            if kps:
                log(f"   [images ] không có ảnh gốc dùng được, sinh SVG diagram...")
                try:
                    svg = _gen_svg(client, row, kps)
                    if svg:
                        fname = f"{slug}_01.svg"
                        (images_dir / fname).write_text(svg, encoding="utf-8")
                        kept.append({"file": fname,
                                     "caption": f"Sơ đồ tóm tắt: {row['topic_title']}",
                                     "source": "ai_svg"})
                except Exception as e:
                    warn(f"{slug}: sinh SVG lỗi ({e}), topic không có hình.")
        return kept
