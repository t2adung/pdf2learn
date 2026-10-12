# -*- coding: utf-8 -*-
"""Stage 5b: Sinh câu hỏi TỰ LUẬN (essay) cho từng topic.

Khác MCQ (stage 5 — sinh từ key_points), câu tự luận ưu tiên LẤY TỪ SÁCH:
- Gửi lại đúng các trang của topic (sub-PDF, giống stage 3) để AI thấy các
  BOX IN MÀU (Câu hỏi, Luyện tập, Vận dụng, Em có biết, Hoạt động...) và các
  câu hỏi có sẵn trong bài — đây là nguồn câu hỏi chuẩn nhất của giáo viên.
- Kèm nội dung bài học đã soạn (content markdown) làm ngữ cảnh soạn đáp án.
- Mỗi bài 4-6 câu, ưu tiên dạng ĐỊNH NGHĨA / LIỆT KÊ / GIẢI THÍCH — dạng
  chấm được bằng đáp án mẫu.

Output khớp phần "exercises" của import payload (xem stage_export.py):
  {type: "essay", topic_slug, question, correct_answer, explanation_vi, difficulty}
"""
from render_markdown import content_markdown
from stage_content import cut_pages
from utils import log, warn

ESSAY_MIN, ESSAY_MAX = 4, 6

ESSAY_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "correct_answer": {"type": "string"},
                "explanation_vi": {"type": "string"},
                "difficulty": {"type": "integer"},
            },
            "required": ["question", "correct_answer", "explanation_vi", "difficulty"],
        }},
    },
    "required": ["questions"],
}

ESSAY_PROMPT = """Bạn là giáo viên ra đề TỰ LUẬN cho trình độ "{level}".
Tài liệu PDF đính kèm là các trang thuộc bài: "{topic_title}" (thuộc {module_title}).

NỘI DUNG BÀI HỌC ĐÃ TÓM TẮT (tham khảo để soạn đáp án):
{content}

Nhiệm vụ: soạn {n_min}-{n_max} câu hỏi tự luận NGẮN cho bài này.

NGUỒN CÂU HỎI — ưu tiên theo thứ tự:
1. Câu hỏi CÓ SẴN TRONG SÁCH: thường nằm trong các BOX/KHUNG IN MÀU (nền màu,
   viền màu) hoặc có nhãn như "Câu hỏi", "Luyện tập", "Vận dụng", "Hoạt động",
   "Thảo luận", "Em hãy...", biểu tượng dấu "?" — hoặc các câu hỏi cuối bài.
   Giữ sát ý câu gốc, chỉ sửa cho tự đứng được (không cần nhìn hình/bảng trong sách).
   BỎ QUA câu yêu cầu vẽ, làm thí nghiệm, quan sát hình, đi thực tế, hoặc câu mở
   không có đáp án xác định.
2. Nếu sách không đủ câu phù hợp: TỰ SOẠN thêm, bám sát kiến thức trong các trang
   đính kèm (không bịa số liệu/định nghĩa ngoài tài liệu).

DẠNG CÂU HỎI — ưu tiên:
- ĐỊNH NGHĨA: "... là gì?", "Nêu khái niệm ..."
- LIỆT KÊ: "Kể tên ...", "Nêu các ... "
- GIẢI THÍCH: "Vì sao ...?", "Giải thích ...", "Phân biệt ... và ..."

YÊU CẦU TỪNG FIELD (TEXT THUẦN, không markdown, bằng NGÔN NGỮ CỦA TÀI LIỆU GỐC):
- "question": rõ ràng, 1 yêu cầu chính, trả lời được trong 1-4 câu.
- "correct_answer": ĐÁP ÁN MẪU đầy đủ, ngắn gọn (<= 60 từ); câu liệt kê thì nêu đủ
  các ý; nên kèm ví dụ ngắn nếu phù hợp.
- "explanation_vi": BẰNG TIẾNG VIỆT — hướng dẫn chấm / giải thích vì sao đúng
  (vd "chỉ cần nêu đúng 3 ý bất kỳ", "ý chính cần có là ...") (<= 40 từ).
- "difficulty": 1 = nhớ (định nghĩa, liệt kê), 2 = hiểu (giải thích, phân biệt),
  3 = vận dụng. Trộn các mức, phần lớn là 1-2.
- Không trùng ý giữa các câu."""


def generate_essay_one(doc, row: dict, content_entry: dict, client,
                       dpi: int = 0) -> list:
    """Sinh câu hỏi tự luận cho MỘT topic. Trả về list
    [{question, correct_answer, explanation_vi, difficulty}] (tối đa ESSAY_MAX)."""
    slug = row["topic_slug"]
    log(f"   [essay   ] trang {row['page_start']}-{row['page_end']} -> "
        f"sinh {ESSAY_MIN}-{ESSAY_MAX} câu tự luận...")
    sub_pdf = cut_pages(doc, row["page_start"], row["page_end"], dpi=dpi)
    prompt = ESSAY_PROMPT.format(
        level=row["level"], topic_title=row["topic_title"],
        module_title=row["module_title"],
        content=content_markdown(content_entry or {}),
        n_min=ESSAY_MIN, n_max=ESSAY_MAX)
    res = client.generate_json(
        [client.pdf_part(sub_pdf, f"{slug}_essay.pdf"), {"text": prompt}],
        ESSAY_SCHEMA, tag="essay", temperature=0.4)

    out = []
    for q in res.get("questions", []):
        question = str(q.get("question", "")).strip()
        answer = str(q.get("correct_answer", "")).strip()
        if not question or not answer:
            continue
        try:
            d = int(q.get("difficulty", 1))
        except (TypeError, ValueError):
            d = 1
        out.append({"question": question, "correct_answer": answer,
                    "explanation_vi": str(q.get("explanation_vi", "")).strip(),
                    "difficulty": min(3, max(1, d))})
    if len(out) > ESSAY_MAX:
        out = out[:ESSAY_MAX]
    if len(out) < ESSAY_MIN:
        warn(f"{slug}: chỉ sinh được {len(out)} câu tự luận (< {ESSAY_MIN}).")
    return out
