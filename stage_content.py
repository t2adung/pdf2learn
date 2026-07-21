# -*- coding: utf-8 -*-
"""Stage 3 (v3): Sinh nội dung bài học cho từng topic — dạng LEARNING OBJECT JSON.

Thay đổi cốt lõi so với v1:
- v1: AI trả về 1 blob "content_markdown" => format do AI quyết, khó kiểm soát,
  muốn đổi layout phải sinh lại (tốn token).
- v2: AI CHỈ trả về DỮ LIỆU CÓ CẤU TRÚC (objectives, key_terms, sections,
  misconceptions...). Cú pháp Markdown do CODE sinh (render_markdown.py)
  => 0 token cho khâu format, đổi layout chỉ cần re-render từ cache, không
  gọi lại AI.
- v3: bỏ "mindmap" (khó đọc trên giao diện text/markdown, sinh động không
  bằng infographic thật). Thay bằng "concept_overview" (khối mở đầu kiểu
  "Khái niệm trọng tâm" của tờ tóm tắt bài học) + "quick_review" (khối chốt
  cuối bài kiểu "Ghi nhớ nhanh") + "formula" trong section (công thức tách
  riêng biến số, không nhét vào point) — bám sát bố cục các tờ tổng hợp kiến
  thức dạng infographic mà giáo viên hay tự làm tay.

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
        "concept_overview": {"type": "string"},
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
                "formula": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"},
                        "variables": {"type": "array", "items": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string"},
                                "meaning": {"type": "string"},
                            },
                            "required": ["symbol", "meaning"],
                        }},
                    },
                    "required": ["expression", "variables"],
                },
                "points": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["heading", "points"],
        }},
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
        "quick_review": {"type": "array", "items": {"type": "string"}},
        "key_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["concept_overview", "objectives", "sections", "quick_review", "key_points"],
}

CONTENT_PROMPT = """Bạn là giáo viên giỏi VÀ giỏi trình bày, đang soạn một tờ tóm tắt bài học
kiểu infographic (dạng "Tổng hợp kiến thức" học sinh dán vào vở) cho học sinh
trình độ "{level}". Tài liệu PDF đính kèm là các trang thuộc bài: "{topic_title}"
(thuộc {module_title}).

Trả về DỮ LIỆU BÀI HỌC dạng JSON theo schema, bằng NGÔN NGỮ CỦA TÀI LIỆU GỐC.
Mỗi field là TEXT THUẦN (không markdown, không ký hiệu **, ##, -).

VĂN PHONG (BẮT BUỘC — dễ hiểu và sinh động, không viết như sách giáo khoa khô khan):
- Câu chủ động, từ ngữ quen thuộc với {level}, đọc lướt hiểu ngay, không hàn lâm.
- Ưu tiên hình ảnh/so sánh/ví dụ CỤ THỂ gắn với đồ vật, hoạt động học sinh gặp
  hằng ngày thay vì định nghĩa trừu tượng suông (vd thay vì chỉ nêu định nghĩa,
  gắn kèm 1 vật/hiện tượng quen thuộc minh hoạ ngay).
- Mỗi point là MỘT ý, MỘT câu ngắn gọn, TỐI ĐA 20 TỪ — không nhồi nhiều ý bằng
  dấu phẩy nối dài.
- Tổng "sections" không vượt quá ~350 từ. Thà ít point mà cô đọng, sinh động
  còn hơn nhiều point dài dòng — chỉ giữ ý CỐT LÕI, bỏ chi tiết phụ.

NHÓM PHẢI BÁM SÁT TÀI LIỆU (tuyệt đối không bịa thêm số liệu/định nghĩa):
- "concept_overview": 1-2 câu súc tích nêu ĐÚNG bản chất/trọng tâm cả bài — đây
  là khối mở đầu học sinh đọc để nắm ý chính trước khi đi vào chi tiết.
- "sections": 2-4 mục nội dung chính, MỖI MỤC LÀ MỘT NHÓM Ý rõ ràng (không
  trộn nhiều chủ đề vào 1 mục). Mỗi mục gồm:
  - heading ngắn, icon_hint là MỘT emoji phù hợp nội dung mục đó.
  - "formula" (CHỈ thêm khi mục có công thức/định luật rõ ràng trong tài
    liệu — vd Vật lí, Hoá học, Toán): expression là công thức viết gọn (vd
    "Wd = 1/2 m v^2"), variables liệt kê ĐẦY ĐỦ từng kí hiệu + ý nghĩa + đơn vị
    nếu có (vd {{"symbol": "m", "meaning": "khối lượng (kg)"}}). Mục không có
    công thức thì BỎ QUA field này, đừng ép công thức vào.
  - 2-4 points (mỗi point <= 20 từ), giải thích thuật ngữ khó gọn trong 1 point.
- "key_terms": 2-5 thuật ngữ quan trọng. definition <= 20 từ; example ngắn,
  cụ thể, gắn đời sống học sinh.
- "key_points": 6-15 ý kiến thức QUAN TRỌNG NHẤT (mỗi ý 1 câu hoàn chỉnh, độc
  lập, kiểm tra được — dùng sinh câu hỏi trắc nghiệm). Số lượng tỉ lệ lượng
  kiến thức thật: bài ngắn ít point, bài dài nhiều point. key_points KHÔNG bị
  giới hạn 20 từ (đây là dữ liệu nội bộ, không hiển thị cho người học).
- "objectives": 2-3 mục tiêu — học xong làm được gì (mỗi mục <= 15 từ).

NHÓM ĐƯỢC PHÉP BỔ SUNG kiến thức ngoài tài liệu (phù hợp trình độ "{level}"):
- "hook": 1 câu hỏi khởi động gây tò mò, gắn đời sống (<= 30 từ).
- "real_life": 1-2 ví dụ ứng dụng thực tế, càng cụ thể càng tốt (mỗi ví dụ <= 20 từ).
- "memory_hooks": 1-2 mẹo ghi nhớ ngắn, dễ hình dung (vd viết tắt, liên tưởng vui).
- "misconceptions": 1-2 cặp hiểu-lầm (wrong) và đính chính (correct), mỗi vế <= 20 từ.
- "quick_review": 2-4 câu "chốt" NGẮN VÀ ĐANH THÉP nhất bài (mỗi câu <= 15 từ,
  không lặp nguyên văn point ở trên) — đây là khối "Ghi nhớ nhanh" cuối bài,
  đọc xong là nhớ được cốt lõi cả bài dù không đọc lại phần trên."""


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
              "memory_hooks", "misconceptions", "quick_review", "key_points"):
        lo[k] = [x for x in (lo.get(k) or []) if x]
    return lo
