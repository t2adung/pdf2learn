# -*- coding: utf-8 -*-
"""Stage 5b: Sinh câu hỏi TỰ LUẬN (essay) cho từng topic.

Khác MCQ (stage 5 — sinh từ key_points), câu tự luận ưu tiên LẤY TỪ SÁCH:
- Gửi lại đúng các trang của topic (sub-PDF, giống stage 3) để AI thấy các
  BOX IN MÀU (Câu hỏi, Luyện tập, Vận dụng, Em có biết, Hoạt động...) và các
  câu hỏi có sẵn trong bài — đây là nguồn câu hỏi chuẩn nhất của giáo viên.
- Kèm nội dung bài học đã soạn (content markdown) làm ngữ cảnh soạn đáp án.
- Mỗi bài 10-12 câu, độ khó theo ma trận đề kiểm tra trên lớp / học kỳ 4 mức
  (Nhận biết / Thông hiểu / Vận dụng / Vận dụng cao), tỉ lệ cố định LEVEL_QUOTA.
- Đáp án mẫu kèm THANG ĐIỂM THEO Ý ngay trong correct_answer — app phía sau
  chấm bằng AI chỉ đọc question + correct_answer.

Output khớp phần "exercises" của import payload (xem stage_export.py):
  {type: "essay", topic_slug, question, correct_answer, explanation_vi, difficulty}
difficulty của template import chỉ có 1-3 -> mức 4 (Vận dụng cao) ghi là 3;
mức gốc 1-4 giữ ở field "level" trong cache work/05_essay.json.
"""
import re

from render_markdown import content_markdown
from stage_content import cut_pages
from utils import log, warn

ESSAY_MIN, ESSAY_MAX = 10, 12
# Ma trận 12 câu: Nhận biết / Thông hiểu / Vận dụng / Vận dụng cao (~35/35/20/10%)
LEVEL_QUOTA = {1: 4, 2: 4, 3: 3, 4: 1}
# "(1) [0,5đ] ..." — mỗi ý chấm có điểm trong ngoặc vuông
RUBRIC_RE = re.compile(r"\[\s*\d+(?:[.,]\d+)?\s*đ\s*\]")

ESSAY_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "level": {"type": "integer"},
                "question": {"type": "string"},
                "correct_answer": {"type": "string"},
                "explanation_vi": {"type": "string"},
            },
            "required": ["level", "question", "correct_answer", "explanation_vi"],
        }},
    },
    "required": ["questions"],
}

ESSAY_PROMPT = """Bạn là giáo viên ra đề TỰ LUẬN cho trình độ "{level}", dùng cho bài
KIỂM TRA TRÊN LỚP và KIỂM TRA HỌC KỲ.
Tài liệu PDF đính kèm là các trang thuộc bài: "{topic_title}" (thuộc {module_title}).

NỘI DUNG BÀI HỌC ĐÃ TÓM TẮT (tham khảo để soạn đáp án):
{content}

Nhiệm vụ: soạn {n_max} câu hỏi tự luận cho bài này theo MA TRẬN 4 MỨC độ sau
(field "level"):
- level 1 — NHẬN BIẾT ({q1} câu): nêu định nghĩa, khái niệm, kể tên, liệt kê.
- level 2 — THÔNG HIỂU ({q2} câu): giải thích vì sao, phân biệt, so sánh, lấy ví dụ.
- level 3 — VẬN DỤNG ({q3} câu): áp dụng kiến thức vào một TÌNH HUỐNG CỤ THỂ (bài
  tập, ví dụ thực tế, dữ kiện cho sẵn) để giải quyết / tính toán / phân tích.
- level 4 — VẬN DỤNG CAO ({q4} câu): tình huống mới, gần đời sống, cần phối hợp
  nhiều ý trong bài để lập luận, đánh giá hoặc đề xuất giải pháp có giải thích.
Bài quá ngắn không đủ ý thì được ít hơn (tối thiểu {n_min} nếu đủ kiến thức) nhưng
giữ tỉ lệ gần đúng và LUÔN có ít nhất 2 câu level 3-4. KHÔNG lặp ý hay hỏi vụn vặt.

NGUỒN CÂU HỎI — ưu tiên theo thứ tự:
1. Câu hỏi CÓ SẴN TRONG SÁCH: thường nằm trong các BOX/KHUNG IN MÀU (nền màu,
   viền màu) hoặc có nhãn như "Câu hỏi", "Luyện tập", "Vận dụng", "Hoạt động",
   "Thảo luận", "Em hãy...", biểu tượng dấu "?" — hoặc các câu hỏi cuối bài.
   Giữ sát ý câu gốc, chỉ sửa cho tự đứng được (không cần nhìn sách).
   Câu cần hình/bảng/số liệu trong sách: CHUYỂN THỂ — mô tả bằng lời đủ dữ kiện
   cần thiết ngay trong câu hỏi, KHÔNG bỏ (đây thường là câu Vận dụng tốt).
   Chỉ BỎ QUA câu bắt buộc phải vẽ, làm thí nghiệm, đi thực tế, hoặc câu hỏi ý kiến
   cá nhân không có tiêu chí chấm.
2. Nếu sách không đủ câu phù hợp: TỰ SOẠN thêm. Với level 3-4 ĐƯỢC tạo bối cảnh /
   tình huống / số liệu giả định MỚI, nhưng kiến thức cần để giải PHẢI nằm trong
   các trang đính kèm (không bịa định nghĩa, công thức, sự kiện ngoài tài liệu).

YÊU CẦU TỪNG FIELD (TEXT THUẦN, không markdown, không xuống dòng, bằng NGÔN NGỮ
CỦA TÀI LIỆU GỐC — trừ explanation_vi):
- "level": 1 | 2 | 3 | 4 như ma trận trên.
- "question": rõ ràng, tự đủ dữ kiện. Level 1-2: 1 yêu cầu chính. Level 3-4: được
  chia ý a), b) (tối đa 3 ý).
- "correct_answer": ĐÁP ÁN MẪU KÈM THANG ĐIỂM THEO Ý — đây là thứ duy nhất AI chấm
  bài nhìn thấy, nên phải đủ để chấm. Định dạng:
  "(1) [0,5đ] <ý chấm 1>; (2) [0,5đ] <ý chấm 2>; ..."
  Tổng điểm mỗi câu: level 1-2 = 1đ, level 3 = 2đ, level 4 = 3đ (bước 0,25đ).
  Mỗi ý chấm là 1 ý cụ thể kiểm tra được (kết quả, lập luận, ví dụ đúng), câu
  chia a)/b) thì ghi "a) (1) [..] ...". Độ dài: level 1-2 <= 60 từ, level 3-4
  <= 150 từ.
- "explanation_vi": BẰNG TIẾNG VIỆT — lưu ý khi chấm (<= 50 từ): ý nào bắt buộc,
  chấp nhận cách diễn đạt / ví dụ / cách giải khác tương đương, lỗi thường gặp.
- Không trùng ý giữa các câu."""


def _level(q: dict) -> int:
    try:
        return min(4, max(1, int(q.get("level", 1))))
    except (TypeError, ValueError):
        return 1


def generate_essay_one(doc, row: dict, content_entry: dict, client,
                       dpi: int = 0) -> list:
    """Sinh câu hỏi tự luận cho MỘT topic. Trả về list
    [{question, correct_answer, explanation_vi, difficulty, level}] (tối đa ESSAY_MAX).
    level = mức 1-4 của ma trận; difficulty = level kẹp về 1-3 cho template import."""
    slug = row["topic_slug"]
    log(f"   [essay   ] trang {row['page_start']}-{row['page_end']} -> "
        f"sinh {ESSAY_MIN}-{ESSAY_MAX} câu tự luận...")
    sub_pdf = cut_pages(doc, row["page_start"], row["page_end"], dpi=dpi)
    prompt = ESSAY_PROMPT.format(
        level=row["level"], topic_title=row["topic_title"],
        module_title=row["module_title"],
        content=content_markdown(content_entry or {}),
        n_min=ESSAY_MIN, n_max=ESSAY_MAX,
        q1=LEVEL_QUOTA[1], q2=LEVEL_QUOTA[2], q3=LEVEL_QUOTA[3], q4=LEVEL_QUOTA[4])
    res = client.generate_json(
        [client.pdf_part(sub_pdf, f"{slug}_essay.pdf"), {"text": prompt}],
        ESSAY_SCHEMA, tag="essay", temperature=0.4)

    out = []
    for q in res.get("questions", []):
        question = str(q.get("question", "")).strip()
        answer = str(q.get("correct_answer", "")).strip()
        if not question or not answer:
            continue
        lv = _level(q)
        out.append({"question": question, "correct_answer": answer,
                    "explanation_vi": str(q.get("explanation_vi", "")).strip(),
                    "difficulty": min(3, lv), "level": lv})
    if len(out) > ESSAY_MAX:
        out = out[:ESSAY_MAX]
    if len(out) < ESSAY_MIN:
        warn(f"{slug}: chỉ sinh được {len(out)} câu tự luận (< {ESSAY_MIN}).")
    counts = {lv: sum(q["level"] == lv for q in out) for lv in LEVEL_QUOTA}
    if out and counts[3] + counts[4] < 2:
        warn(f"{slug}: thiếu câu Vận dụng — mức 1/2/3/4 = "
             f"{counts[1]}/{counts[2]}/{counts[3]}/{counts[4]} (cần >= 2 câu mức 3-4).")
    no_rubric = sum(not RUBRIC_RE.search(q["correct_answer"]) for q in out)
    if no_rubric:
        warn(f"{slug}: {no_rubric} câu tự luận thiếu thang điểm theo ý trong đáp án.")
    return out
