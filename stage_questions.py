# -*- coding: utf-8 -*-
"""Stage 5: Sinh câu hỏi trắc nghiệm.

Chiến thuật coverage: sinh câu hỏi BÁM THEO key_points (mỗi point 1-2 câu)
=> nội dung nhiều thì nhiều câu, ít thì ít câu, và không key point nào bị bỏ sót.

Pass validation: một request riêng đóng vai "người giải đề", giải từng câu
KHÔNG nhìn đáp án; câu nào giải ra khác correct_answer => loại (nghi ngờ mơ hồ/sai).
"""
import json

from render_markdown import content_markdown
from subjects import guide_block
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
6. difficulty: 1 = nhớ (nhận biết), 2 = hiểu, 3 = vận dụng. Trộn cả 3 mức.{subject_guide}"""

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
{questions}{subject_guide}"""


def _fmt_questions_for_validation(questions: list) -> str:
    lines = []
    for i, q in enumerate(questions):
        lines.append(f"Câu {i}: {q['question']}")
        for letter in "ABCD":
            lines.append(f"  {letter}. {q[letter]}")
    return "\n".join(lines)


def generate_questions_one(row: dict, content_entry: dict, client,
                           validate: bool = True, subject_profile=None):
    """Sinh câu hỏi cho MỘT topic. Trả về (questions, dropped_hoặc_None).
    subject_profile: SubjectProfile (subjects.py) — chèn hướng dẫn riêng theo môn."""
    slug = row["topic_slug"]
    kps = content_entry.get("key_points", [])
    log(f"   [question] {len(kps)} key points -> sinh câu hỏi...")
    content_md = content_markdown(content_entry)
    prompt = QUESTIONS_PROMPT.format(
        level=row["level"], topic_title=row["topic_title"],
        content=content_md,
        key_points="\n".join(f"- {k}" for k in kps),
        subject_guide=guide_block(subject_profile, "mcq"))
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
            questions=_fmt_questions_for_validation(questions),
            subject_guide=guide_block(subject_profile, "validate"))
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


# ---------------------------------------------------------------------------
# Pass "special": chọn câu hấp dẫn để làm video short marketing (bibeli.net)
# ---------------------------------------------------------------------------
# Pass RIÊNG (LLM-as-judge) chạy sau validate, không gộp vào prompt sinh câu hỏi:
# model tự chấm câu mình vừa viết hay thiên vị (đánh true tràn lan). Cùng 1 hàm
# dùng cho sách mới, sách đã xong (đọc lại cache) và sách dở dang.
SPECIAL_RATIO = 0.25          # tối đa ~25% số câu / topic được đánh dấu

SPECIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "picks": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["index", "reason"],
        }},
    },
    "required": ["picks"],
}

SPECIAL_PROMPT = """Bạn là biên tập viên nội dung video ngắn (TikTok / Reels / Shorts) cho
bibeli.net — nền tảng học tập. Từ bộ câu trắc nghiệm của bài "{topic_title}" (trình độ
"{level}"), hãy CHỌN những câu đủ hấp dẫn để làm video short marketing: người xem lướt qua
phải dừng lại, muốn tự trả lời và muốn xem đáp án.

TIÊU CHÍ CHỌN (câu được chọn nên thoả nhiều tiêu chí):
1. Gây tò mò / bất ngờ: đáp án trái trực giác, phá một hiểu lầm phổ biến, có khoảnh khắc "à ha".
2. Gắn đời sống thực tế: hiện tượng, đồ vật, tình huống người xem gặp hằng ngày.
3. Thông minh: cần suy luận một chút, không chỉ học vẹt; phương án nhiễu đủ "lừa" để gây tranh luận.
4. Đọc nhanh hiểu ngay: câu hỏi + 4 phương án ngắn, đọc kịp trong vài giây, không cần hình/bảng.

KHÔNG CHỌN:
- Câu học thuộc khô: đáp án chỉ nhắc lại nguyên văn sách, ai cũng đoán được (vd "Tế bào là gì?").
  LƯU Ý: câu định nghĩa KHÔNG bị loại vì là định nghĩa — nếu định nghĩa đó gây bất ngờ / phá hiểu
  lầm (vd "Về mặt sinh học, cà chua là rau hay quả?") thì VẪN chọn.
- Câu phải xem hình, bảng, sơ đồ mới hiểu.
- Câu dài, nhiều mệnh đề, phương án dài dòng.

QUY TẮC:
- Chọn TỐI ĐA {max_picks} câu, ưu tiên câu nổi bật nhất. Không có câu nào đạt thì trả về picks rỗng —
  KHÔNG chọn cho đủ số.
- index tính từ 0 theo danh sách dưới đây; reason: 1 câu ngắn bằng TIẾNG VIỆT vì sao câu đó hấp dẫn.

CÁC CÂU HỎI:
{questions}"""


def needs_special(questions: list) -> bool:
    """True nếu còn câu chưa được đánh giá is_special (cache cũ / sách dở dang)."""
    return any("is_special" not in q for q in questions)


def mark_special_one(row: dict, questions: list, client) -> int:
    """Đánh giá + ghi q["is_special"] (và q["special_reason"] nếu được chọn) TẠI CHỖ cho
    MỌI câu của một topic. Trả về số câu được chọn.

    Lỗi AI tạm thời -> warn, KHÔNG gán key để lần chạy sau thử lại. Lỗi hết quota
    (GeminiError / ClaudeError) để nổi lên cho main.py xử lý resume."""
    if not questions:
        return 0
    from claude_cli import ClaudeError
    from gemini import GeminiError
    max_picks = max(1, round(len(questions) * SPECIAL_RATIO))
    log(f"   [special ] chọn câu hấp dẫn cho video short (tối đa {max_picks}/"
        f"{len(questions)})...")
    prompt = SPECIAL_PROMPT.format(
        topic_title=row["topic_title"], level=row["level"], max_picks=max_picks,
        questions=_fmt_questions_for_validation(questions))
    try:
        res = client.generate_json([{"text": prompt}], SPECIAL_SCHEMA,
                                   tag="special", temperature=0.2)
    except (GeminiError, ClaudeError):
        raise
    except Exception as e:
        warn(f"{row['topic_slug']}: đánh giá is_special lỗi ({e}) — để lần chạy sau.")
        return 0
    picks = {}
    for p in res.get("picks", []):
        try:
            i = int(p.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(questions) and i not in picks and len(picks) < max_picks:
            picks[i] = str(p.get("reason", "")).strip()
    for i, q in enumerate(questions):
        q["is_special"] = i in picks
        if i in picks:
            q["special_reason"] = picks[i]
        else:
            q.pop("special_reason", None)
    log(f"   [special ] {len(picks)} câu is_special=true")
    return len(picks)
