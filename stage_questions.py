# -*- coding: utf-8 -*-
"""Stage 5: Sinh câu hỏi trắc nghiệm.

Chiến thuật coverage: sinh câu hỏi BÁM THEO key_points (mỗi point 1-2 câu)
=> nội dung nhiều thì nhiều câu, ít thì ít câu, và không key point nào bị bỏ sót.

Pass validation: một request riêng đóng vai "người giải đề", giải từng câu
KHÔNG nhìn đáp án; câu nào giải ra khác correct_answer => loại (nghi ngờ mơ hồ/sai).
"""
import json

from utils import log, warn

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
Bài học: "{topic_title}".

NỘI DUNG BÀI HỌC:
{content}

CÁC Ý KIẾN THỨC PHẢI KIỂM TRA (key points):
{key_points}

Nhiệm vụ: sinh câu hỏi trắc nghiệm 4 phương án A/B/C/D sao cho:
1. MỖI key point có 1-2 câu hỏi (point quan trọng/phức tạp thì 2 câu, đơn giản thì 1 câu).
   => người học làm hết bộ câu hỏi là nhớ được TOÀN BỘ ý quan trọng của bài.
2. Câu hỏi và phương án bằng ngôn ngữ của nội dung bài học.
3. 3 phương án nhiễu phải HỢP LÝ — là lỗi sai người học hay mắc, cùng độ dài/độ chi tiết
   với đáp án đúng, KHÔNG vô lý lộ liễu, không dùng "Tất cả các ý trên".
4. Vị trí đáp án đúng phân bố đều giữa A, B, C, D (không dồn vào 1 chữ cái).
5. explanation_vi: giải thích NGẮN GỌN bằng TIẾNG VIỆT vì sao đáp án đúng.
6. difficulty: 1 = nhớ (nhận biết), 2 = hiểu, 3 = vận dụng. Trộn cả 3 mức."""

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
    log(f"   [question] {len(kps)} key points -> sinh câu hỏi...")
    prompt = QUESTIONS_PROMPT.format(
        level=row["level"], topic_title=row["topic_title"],
        content=content_entry["content_markdown"],
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
            content=content_entry["content_markdown"],
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
