# -*- coding: utf-8 -*-
"""Stage 3 (v2): Sinh nội dung bài học cho từng topic — dạng LEARNING OBJECT JSON.

Thay đổi cốt lõi so với v1:
- v1: AI trả về 1 blob "content_markdown" => format do AI quyết, khó kiểm soát,
  muốn đổi layout phải sinh lại (tốn token).
- v2: AI CHỈ trả về DỮ LIỆU CÓ CẤU TRÚC (objectives, key_terms, sections,
  mindmap, misconceptions...). Cú pháp Markdown/SVG do CODE sinh
  (render_markdown.py + mindmap_svg.py) => 0 token cho khâu format,
  đổi layout chỉ cần re-render từ cache, không gọi lại AI.

Kỹ thuật chống hallucination (giữ nguyên từ v1):
- Chỉ gửi đúng các trang của topic (cắt sub-PDF theo page range).
- Prompt tách rõ field nào phải bám tài liệu, field nào được bổ sung.
- key_points sinh ra ở đây sẽ được Stage 5 dùng để đảm bảo coverage câu hỏi.
"""
import fitz

from utils import log

# Learning Object schema — mọi field đều là DATA, không chứa cú pháp markdown.
CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "objectives": {"type": "array", "items": {"type": "string"}},
        "hook": {"type": "string"},
        "key_terms": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "term": {"type": "string"},
                "definition": {"type": "string"},
                "example": {"type": "string"},
            },
            "required": ["term", "definition"],
        }},
        "sections": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "heading": {"type": "string"},
                "icon_hint": {"type": "string"},
                "points": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["heading", "points"],
        }},
        "mindmap": {
            "type": "object",
            "properties": {
                "root": {"type": "string"},
                "branches": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "children": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["label", "children"],
                }},
            },
            "required": ["root", "branches"],
        },
        "real_life": {"type": "array", "items": {"type": "string"}},
        "memory_hooks": {"type": "array", "items": {"type": "string"}},
        "misconceptions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "wrong": {"type": "string"},
                "correct": {"type": "string"},
            },
            "required": ["wrong", "correct"],
        }},
        "key_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["objectives", "sections", "mindmap", "key_points"],
}

CONTENT_PROMPT = """Bạn là giáo viên giỏi, đang soạn bài học cho học sinh trình độ "{level}".
Tài liệu PDF đính kèm là các trang thuộc bài: "{topic_title}" (thuộc {module_title}).

Trả về DỮ LIỆU BÀI HỌC dạng JSON theo schema, bằng NGÔN NGỮ CỦA TÀI LIỆU GỐC.
Mỗi field là TEXT THUẦN (không markdown, không ký hiệu **, ##, -):

NHÓM PHẢI BÁM SÁT TÀI LIỆU (tuyệt đối không bịa thêm số liệu/định nghĩa):
- "sections": 2-5 mục nội dung chính. Mỗi mục: heading ngắn, icon_hint là
  MỘT emoji phù hợp nội dung mục, + 2-6 points,
  mỗi point là 1 câu hoàn chỉnh, chi tiết, dễ hiểu với trình độ "{level}".
  Giải thích thuật ngữ khó ngay trong point khi nó xuất hiện.
- "key_terms": 2-6 thuật ngữ quan trọng trong tài liệu. definition ngắn gọn;
  example là ví dụ minh hoạ (được phép lấy ví dụ đời thường).
- "mindmap": sơ đồ tư duy tóm tắt bài. root = tên khái niệm trung tâm (ngắn),
  3-5 branches, mỗi branch có label <= 5 từ và 2-4 children (mỗi child <= 8 từ).
- "key_points": 6-15 ý kiến thức QUAN TRỌNG NHẤT của bài (mỗi ý 1 câu hoàn chỉnh,
  độc lập, kiểm tra được — sẽ dùng sinh câu hỏi trắc nghiệm). Số lượng tỉ lệ
  với lượng kiến thức thật trong tài liệu: bài ngắn ít point, bài dài nhiều point.
- "objectives": 2-4 mục tiêu — học xong bài này người học làm được gì.

NHÓM ĐƯỢC PHÉP BỔ SUNG kiến thức ngoài tài liệu (phù hợp trình độ "{level}"):
- "hook": 1 câu hỏi khởi động gây tò mò, gắn với đời sống của người học.
- "real_life": 1-3 ví dụ ứng dụng thực tế sinh động.
- "memory_hooks": 1-3 mẹo ghi nhớ (viết tắt, liên tưởng, vần điệu).
- "misconceptions": 1-3 cặp hiểu-lầm-phổ-biến (wrong) và đính chính (correct)."""


def cut_pages(doc: fitz.Document, page_start: int, page_end: int,
              dpi: int = 0) -> bytes:
    """dpi=0: cắt nguyên bản. dpi>0: render lại từng trang thành ảnh JPEG
    grayscale ở độ phân giải đó — giảm mạnh token với PDF scan độ phân giải cao
    (ảnh lớn bị model cắt thành nhiều tile tính token). 100-120 dpi vẫn đủ
    để OCR chữ sách giáo khoa."""
    sub = fitz.open()
    if dpi <= 0:
        sub.insert_pdf(doc, from_page=page_start - 1, to_page=page_end - 1)
    else:
        for pno in range(page_start - 1, page_end):
            src_page = doc[pno]
            target_w = src_page.rect.width / 72 * dpi
            # Guard: nếu ảnh scan gốc đã NHỎ hơn bản render thì nén là phản
            # tác dụng (upscale) -> giữ nguyên trang gốc
            imgs = src_page.get_images(full=True)
            max_w = max((doc.extract_image(i[0])["width"] for i in imgs), default=10**9)
            if max_w <= target_w:
                sub.insert_pdf(doc, from_page=pno, to_page=pno)
                continue
            pix = src_page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
            jpg = pix.tobytes("jpeg", jpg_quality=72)
            page = sub.new_page(width=pix.width, height=pix.height)
            page.insert_image(page.rect, stream=jpg)
    data = sub.tobytes(garbage=3, deflate=True)
    sub.close()
    return data


def generate_content_one(doc: fitz.Document, row: dict, client, dpi: int = 0) -> dict:
    """Sinh Learning Object (JSON) cho MỘT topic."""
    slug = row["topic_slug"]
    log(f"   [content ] trang {row['page_start']}-{row['page_end']}...")
    sub_pdf = cut_pages(doc, row["page_start"], row["page_end"], dpi=dpi)
    prompt = CONTENT_PROMPT.format(level=row["level"],
                                   topic_title=row["topic_title"],
                                   module_title=row["module_title"])
    lo = client.generate_json(
        [client.pdf_part(sub_pdf, f"{slug}.pdf"), {"text": prompt}],
        CONTENT_SCHEMA, tag="content")
    # dọn field rỗng để render sạch
    for k in ("objectives", "key_terms", "sections", "real_life",
              "memory_hooks", "misconceptions", "key_points"):
        lo[k] = [x for x in (lo.get(k) or []) if x]
    return lo
