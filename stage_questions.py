# -*- coding: utf-8 -*-
"""Stage 5: Sinh câu hỏi trắc nghiệm.

Chiến thuật số lượng (SỐ CÂU THEO SỐ TRANG): chỉ tiêu số câu tỉ lệ với độ dài
topic — trung bình QUESTIONS_PER_PAGE câu/trang, trang trọng yếu (kiến thức quan
trọng) tới KEY_PAGE_MAX câu. => topic dài nhiều câu, topic ngắn ít câu.

Chiến thuật coverage: song song, câu hỏi vẫn BÁM THEO key_points (mỗi point >= 1
câu) để không ý kiến thức quan trọng nào bị bỏ sót.

Pass validation: một request riêng đóng vai "người giải đề", giải từng câu
KHÔNG nhìn đáp án; câu nào giải ra khác correct_answer => loại (nghi ngờ mơ hồ/sai).
"""
import math

from render_markdown import content_markdown
from utils import log, warn

# ── Chỉ tiêu số câu theo số trang (tinh chỉnh tại đây) ──────────────────
QUESTIONS_PER_PAGE = 4      # trung bình mỗi trang thường
KEY_PAGE_MIN = 6            # sàn cho MỘT trang trọng yếu (6-8 câu)
KEY_PAGE_MAX = 8            # trần cho MỘT trang trọng yếu (6-8 câu)
KEY_PAGE_FRACTION = 1 / 3   # ước lượng tỉ lệ trang trọng yếu trong topic


def _target_question_count(n_pages: int) -> tuple:
    """Trả (target_min, target_max) số câu cho topic dựa trên SỐ TRANG.

    - target_min = QUESTIONS_PER_PAGE * số_trang  (trung bình 4 câu/trang).
    - target_max: cộng thêm phần dôi cho các trang trọng yếu — ước lượng
      ~KEY_PAGE_FRACTION số trang là trọng yếu, mỗi trang trọng yếu thêm tối đa
      (KEY_PAGE_MAX - QUESTIONS_PER_PAGE) câu so với trang thường.

    Ví dụ (mặc định 4/trang, trọng yếu tối đa 8):
      1 trang  -> (4, 8)      3 trang  -> (12, 16)     5 trang  -> (20, 28)
    """
    n_pages = max(1, int(n_pages))
    key_pages = max(1, math.ceil(n_pages * KEY_PAGE_FRACTION))
    target_min = QUESTIONS_PER_PAGE * n_pages
    target_max = target_min + (KEY_PAGE_MAX - QUESTIONS_PER_PAGE) * key_pages
    return target_min, target_max

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "A": {"type": "string"},
                "B": {"type": "string"},
                "C": {"type": "string"},
                "D": {"type": "string"},
                "correct_answer": {"type": "string", "enum": ["A", "B", "C", "D"]},
                "explanation_vi": {"type": "string"},
                "difficulty": {"type": "integer"},
            },
            "required": ["question", "A", "B", "C", "D",
                         "correct_answer", "explanation_vi", "difficulty"],
        }},
    },
    "required": ["questions"],
}

QUESTIONS_PROMPT = """Bạn là chuyên gia ra đề trắc nghiệm cho trình độ "{level}".
Bài học: "{topic_title}" (dài {n_pages} trang tài liệu).

NỘI DUNG BÀI HỌC:
{content}

CÁC Ý KIẾN THỨC PHẢI KIỂM TRA (key points):
{key_points}

Nhiệm vụ: sinh câu hỏi trắc nghiệm 4 phương án A/B/C/D sao cho:
1. SỐ LƯỢNG CÂU HỎI theo độ dài bài: sinh TỔNG khoảng {target_min}-{target_max} câu.
   - Trung bình {per_page} câu cho mỗi trang tài liệu.
   - Trang/phần TRỌNG YẾU (kiến thức quan trọng, nhiều khái niệm) thì ra {key_min}-{key_max}
     câu cho phần đó; trang phụ/ít nội dung thì ít câu hơn.
   - Bài dài ({n_pages} trang) => NHIỀU câu; bài ngắn => ít câu. Đừng ra quá ít.
2. COVERAGE: MỖI key point phải có ÍT NHẤT 1 câu hỏi (point quan trọng/phức tạp thì
   2-3 câu). => người học làm hết bộ câu hỏi là nhớ được TOÀN BỘ ý quan trọng của bài.
   Nếu số câu theo mục 1 còn dư so với số key point, đào SÂU thêm ở các ý trọng yếu
   (thêm câu vận dụng, so sánh, tình huống) thay vì lặp lại câu đã hỏi.
3. Câu hỏi và phương án bằng ngôn ngữ của nội dung bài học.
4. 3 phương án nhiễu phải HỢP LÝ — là lỗi sai người học hay mắc, cùng độ dài/độ chi tiết
   với đáp án đúng, KHÔNG vô lý lộ liễu, không dùng "Tất cả các ý trên".
5. Vị trí đáp án đúng phân bố đều giữa A, B, C, D (không dồn vào 1 chữ cái).
6. explanation_vi: giải thích NGẮN GỌN bằng TIẾNG VIỆT vì sao đáp án đúng.
7. difficulty: 1 = nhớ (nhận biết), 2 = hiểu, 3 = vận dụng. Trộn cả 3 mức."""

VALIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "answer": {"type": "string", "enum": ["A", "B", "C", "D"]},
            },
            "required": ["index", "answer"],
        }},
    },
    "required": ["answers"],
}

VALIDATE_PROMPT = """Bạn là người giải đề cẩn thận. Dựa vào NỘI DUNG BÀI HỌC dưới đây,
hãy giải từng câu trắc nghiệm một cách độc lập và trả về đáp án bạn chọn cho từng câu
(index tính từ 0). Không đoán theo pattern vị trí, chỉ dựa vào kiến thức trong bài.

NỘI DUNG BÀI HỌC:
{content}

CÁC CÂU HỎI:
{questions}"""


def _fmt_questions_for_validation(questions: list) -> str:
    lines = []
    for i, q in enumerate(questions):
        lines.append(f"Câu {i}: {q['question']}")
        for letter in "ABCD":
            lines.append(f"  {letter}. {q[letter]}")
    return "\n".join(lines)


def generate_questions_one(row: dict, content_entry: dict, client,
                           validate: bool = True):
    """Sinh câu hỏi cho MỘT topic. Trả về (questions, dropped_hoặc_None)."""
    slug = row["topic_slug"]
    kps = content_entry.get("key_points", [])
    n_pages = max(1, int(row["page_end"]) - int(row["page_start"]) + 1)
    target_min, target_max = _target_question_count(n_pages)
    log(f"   [question] {n_pages} trang, {len(kps)} key points "
        f"-> chỉ tiêu {target_min}-{target_max} câu...")
    content_md = content_markdown(content_entry)
    prompt = QUESTIONS_PROMPT.format(
        level=row["level"], topic_title=row["topic_title"],
        n_pages=n_pages, target_min=target_min, target_max=target_max,
        per_page=QUESTIONS_PER_PAGE, key_min=KEY_PAGE_MIN, key_max=KEY_PAGE_MAX,
        content=content_md,
        key_points="\n".join(f"- {k}" for k in kps))
    res = client.generate_json([{"text": prompt}], QUESTIONS_SCHEMA,
                               tag="questions", temperature=0.5)
    questions = res.get("questions", [])
    for q in questions:
        q["difficulty"] = min(3, max(1, int(q.get("difficulty", 1))))

    dropped = None
    if validate and questions:
        log(f"   [validate] giải lại {len(questions)} câu để kiểm tra đáp án...")
        vp = VALIDATE_PROMPT.format(
            content=content_md,
            questions=_fmt_questions_for_validation(questions))
        try:
            vres = client.generate_json([{"text": vp}], VALIDATE_SCHEMA,
                                        tag="validate", temperature=0.1)
            solved = {a["index"]: a["answer"] for a in vres.get("answers", [])}
            passed, dropped_list = [], []
            for i, q in enumerate(questions):
                if solved.get(i, q["correct_answer"]) == q["correct_answer"]:
                    passed.append(q)
                else:
                    dropped_list.append({"question": q["question"],
                                         "claimed": q["correct_answer"],
                                         "solved": solved.get(i)})
            if dropped_list:
                warn(f"{slug}: loại {len(dropped_list)} câu nghi vấn "
                     f"(đáp án tự giải khác đáp án khai báo).")
                dropped = dropped_list
            questions = passed
        except Exception as e:
            warn(f"{slug}: validation lỗi ({e}), giữ nguyên câu hỏi chưa kiểm chứng.")
    return questions, dropped
