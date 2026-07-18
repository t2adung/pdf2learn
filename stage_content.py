# -*- coding: utf-8 -*-
"""Stage 3: Sinh nội dung bài học cho từng topic.

Kỹ thuật chống hallucination:
- Chỉ gửi đúng các trang của topic (cắt sub-PDF theo page range).
- Prompt tách rõ phần nào phải bám tài liệu, phần nào được bổ sung.
- key_points sinh ra ở đây sẽ được Stage 5 dùng để đảm bảo coverage câu hỏi.
"""
import fitz

from utils import log

CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "content_markdown": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["content_markdown", "key_points"],
}

CONTENT_PROMPT = """Bạn là giáo viên giỏi, đang soạn bài học cho học sinh trình độ "{level}".
Tài liệu PDF đính kèm là các trang thuộc bài: "{topic_title}" (thuộc {module_title}).

Soạn bài học bằng NGÔN NGỮ CỦA TÀI LIỆU GỐC, định dạng Markdown, đúng cấu trúc:

## Mục tiêu
(2-4 gạch đầu dòng: học xong bài này người học làm được gì)

## Nội dung chính
(Tóm tắt ĐẦY ĐỦ Ý nhưng NGẮN GỌN, DỄ QUÉT MẮT — bài học này luôn đi kèm 1 hình
infographic tóm tắt ở đầu bài, nên phần chữ KHÔNG cần viết thành đoạn văn dài
lặp lại. CHỈ dùng thông tin có trong tài liệu đính kèm — tuyệt đối không bịa
thêm số liệu/định nghĩa. Giải thích thuật ngữ khó ngay khi xuất hiện, **in đậm**
từ khoá quan trọng. Ưu tiên heading phụ ###, gạch đầu dòng ngắn, bảng so sánh;
mỗi đoạn văn tối đa 3-4 câu.)

## Liên hệ thực tế
(Phần NÀY được phép bổ sung kiến thức ngoài tài liệu: ví dụ đời sống, ứng dụng thực tế phù hợp trình độ "{level}". Ghi rõ ràng, sinh động.)

## Ghi nhớ
(3-6 gạch đầu dòng, mỗi dòng 1 ý cốt lõi phải nhớ)

Đồng thời trả về "key_points": danh sách 6-15 ý kiến thức QUAN TRỌNG NHẤT của bài
(mỗi ý là 1 câu hoàn chỉnh, độc lập, kiểm tra được — sẽ dùng để sinh câu hỏi trắc nghiệm).
Số lượng key_points tỉ lệ với lượng kiến thức thật trong tài liệu: bài ngắn ít point, bài dài nhiều point."""


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
    """Sinh content + key_points cho MỘT topic."""
    slug = row["topic_slug"]
    log(f"   [content ] trang {row['page_start']}-{row['page_end']}...")
    sub_pdf = cut_pages(doc, row["page_start"], row["page_end"], dpi=dpi)
    prompt = CONTENT_PROMPT.format(level=row["level"],
                                   topic_title=row["topic_title"],
                                   module_title=row["module_title"])
    return client.generate_json(
        [client.pdf_part(sub_pdf, f"{slug}.pdf"), {"text": prompt}],
        CONTENT_SCHEMA, tag="content")
