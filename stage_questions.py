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
# model tự chấm câu mình vừa viết hay thiên vị. Cùng 1 hàm dùng cho sách mới,
# sách đã xong (đọc lại cache) và sách dở dang.
#
# v2: model KHÔNG chọn câu (v1 "chọn tối đa N câu" -> bài nào cũng chọn đủ số, kể
# cả câu hiển nhiên). Model chấm TỪNG câu theo thang tuyệt đối + phép thử "người
# lớn trả lời theo trực giác"; CODE quyết định theo ngưỡng cố định bên dưới.
SPECIAL_VERSION = 2           # đổi tiêu chí -> tăng số này, cache cũ tự chấm lại
SPECIAL_MAX_PER_TOPIC = 2     # trần / bài; KHÔNG có sàn (bài toàn câu dễ -> 0 câu)
MIN_HOOK = 4                  # độ hấp dẫn khi làm video (1-5)
MIN_HESITATION = 4            # mức người lớn phân vân / dễ sai (1-5)

SPECIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "evals": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "trap": {"type": "string"},
                "adult_gut_answer": {"type": "string", "enum": ["A", "B", "C", "D"]},
                "adult_hesitation": {"type": "integer"},
                "hook": {"type": "integer"},
            },
            "required": ["index", "trap", "adult_gut_answer",
                         "adult_hesitation", "hook"],
        }},
    },
    "required": ["evals"],
}

SPECIAL_PROMPT = """Bạn là biên tập viên video ngắn (TikTok / Reels / Shorts) cho bibeli.net —
nền tảng học tập. Dạng video: đưa ra 1 câu trắc nghiệm, người xem tự trả lời rồi xem đáp án.
Video chỉ viral khi NGƯỜI LỚN xem cũng PHÂN VÂN hoặc TRẢ LỜI SAI — câu ai cũng đúng ngay thì
người xem lướt qua.

Bài "{topic_title}" (trình độ "{level}"). Hãy CHẤM TỪNG CÂU dưới đây (có kèm đáp án đúng),
độc lập với nhau, theo thang tuyệt đối — KHÔNG so sánh để chọn câu "hay nhất bài". Bài toàn câu
dễ thì mọi câu đều điểm thấp, như vậy là đúng.

Với mỗi câu, lần lượt:
1. trap: hiểu lầm phổ biến CỤ THỂ nào khiến người lớn chọn sai (1 câu, tiếng Việt). Không có
   hiểu lầm thật sự -> để chuỗi rỗng "". KHÔNG viết lời khen chung chung ("gắn đời sống",
   "câu phủ định khiến người xem suy nghĩ").
2. adult_gut_answer: phương án (A/B/C/D) mà ĐA SỐ người lớn bình thường (không học lại sách,
   chỉ có 3 giây, trả lời theo lẽ thường) sẽ chọn. Trung thực: nếu lẽ thường dẫn tới đáp án
   đúng thì ghi đúng đáp án đúng.
3. adult_hesitation (1-5): 1 = ai cũng đúng ngay; 2 = hơi nghĩ nhưng vẫn đúng; 3 = phải dừng
   lại suy nghĩ; 4 = nhiều người lớn chọn sai / tranh cãi; 5 = đa số người lớn sai.
4. hook (1-5): độ hấp dẫn khi làm video — đáp án bất ngờ, gắn đời sống, câu + phương án ngắn
   đọc kịp vài giây, không cần hình/bảng. 5 = người xem muốn bình luận tranh luận ngay.

VÍ DỤ CHẤM THẤP (hiển nhiên — lẽ thường là ra đáp án, adult_hesitation 1-2, trap ""):
- "Thay vì dùng túi nylon và chai nhựa một lần, chúng ta nên ưu tiên vật dụng nào?"
- "Để tiết kiệm điện khi dùng tủ lạnh hoặc máy điều hoà, bạn nên làm gì?"
- "Hành động nào thể hiện việc tiết kiệm điện khi không sử dụng thiết bị điện?"
- "Thiết bị nào có thể chuyển ánh sáng mặt trời thành điện năng?"
- "Trong các nguồn năng lượng tái tạo, loại nào được coi là vô hạn?"
- "Đặc điểm nào sau đây KHÔNG phải là của vật không sống?"
- "Việc ứng dụng Khoa học tự nhiên không đúng cách có thể dẫn đến hậu quả gì?"
LƯU Ý: câu phủ định "KHÔNG phải", câu về an toàn / đạo đức / bảo vệ môi trường, câu có phương
án đúng "nghe hợp lý nhất" KHÔNG tự động là câu khó — chấm theo việc người lớn có thật sự sai
hay không.

VÍ DỤ CHẤM CAO (trực giác dễ sai, adult_hesitation 4-5, hook 4-5):
- "Về mặt sinh học, cà chua là rau hay quả?" — trap: đa số nghĩ là rau vì dùng nấu canh, xào.
- "Vì sao từ Trái Đất ta chỉ thấy Ngân Hà là một dải sáng mờ?" — trap: tưởng Ngân Hà ở xa
  bên ngoài, thực ra Trái Đất nằm bên trong nó.

Trả về evals cho MỌI câu (index tính từ 0).

CÁC CÂU HỎI:
{questions}"""


def _fmt_questions_with_answer(questions: list) -> str:
    """Như _fmt_questions_for_validation nhưng kèm đáp án đúng (pass special cần biết)."""
    lines = []
    for i, q in enumerate(questions):
        lines.append(f"Câu {i}: {q['question']}")
        for letter in "ABCD":
            lines.append(f"  {letter}. {q[letter]}")
        lines.append(f"  Đáp án đúng: {q['correct_answer']}")
    return "\n".join(lines)


def needs_special(questions: list) -> bool:
    """True nếu còn câu chưa được chấm theo tiêu chí hiện hành (SPECIAL_VERSION):
    cache cũ chưa chấm, chấm theo tiêu chí cũ (v1), hoặc sách dở dang."""
    return any(q.get("special_v") != SPECIAL_VERSION for q in questions)


def _score(v, lo=1, hi=5) -> int:
    try:
        return min(hi, max(lo, int(v)))
    except (TypeError, ValueError):
        return lo


def _passes(q: dict, ev: dict) -> bool:
    """Luật quyết định is_special (thuần code, ngưỡng cố định)."""
    return (ev["hook"] >= MIN_HOOK and bool(ev["trap"])
            and (ev["hesitation"] >= MIN_HESITATION
                 or ev["gut"] != q["correct_answer"]))


def mark_special_one(row: dict, questions: list, client) -> int:
    """Chấm + ghi TẠI CHỖ cho MỌI câu của một topic: is_special, special_eval
    {gut, trap, hesitation, hook}, special_v (+ special_reason = trap nếu được chọn).
    Trả về số câu được chọn.

    Lỗi AI tạm thời -> warn, KHÔNG gán key để lần chạy sau thử lại. Lỗi hết quota
    (GeminiError / ClaudeError) để nổi lên cho main.py xử lý resume."""
    if not questions:
        return 0
    from claude_cli import ClaudeError
    from gemini import GeminiError
    log(f"   [special ] chấm {len(questions)} câu cho video short "
        f"(chọn câu người lớn cũng phân vân)...")
    prompt = SPECIAL_PROMPT.format(
        topic_title=row["topic_title"], level=row["level"],
        questions=_fmt_questions_with_answer(questions))
    try:
        res = client.generate_json([{"text": prompt}], SPECIAL_SCHEMA,
                                   tag="special", temperature=0.2)
    except (GeminiError, ClaudeError):
        raise
    except Exception as e:
        warn(f"{row['topic_slug']}: đánh giá is_special lỗi ({e}) — để lần chạy sau.")
        return 0
    evals = {}
    for e in res.get("evals", []):
        try:
            i = int(e.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(questions) and i not in evals:
            gut = str(e.get("adult_gut_answer", "")).strip().upper()[:1]
            evals[i] = {"gut": gut if gut in ("A", "B", "C", "D") else "",
                        "trap": str(e.get("trap", "")).strip(),
                        "hesitation": _score(e.get("adult_hesitation")),
                        "hook": _score(e.get("hook"))}
    # câu đạt ngưỡng -> xếp theo mức phân vân rồi hook, lấy tối đa SPECIAL_MAX_PER_TOPIC
    passed = [i for i, q in enumerate(questions)
              if i in evals and evals[i]["gut"] and _passes(q, evals[i])]
    passed.sort(key=lambda i: (-evals[i]["hesitation"], -evals[i]["hook"], i))
    picked = set(passed[:SPECIAL_MAX_PER_TOPIC])
    for i, q in enumerate(questions):
        q["is_special"] = i in picked
        q["special_v"] = SPECIAL_VERSION
        if i in evals:
            q["special_eval"] = evals[i]
        else:
            q.pop("special_eval", None)      # AI bỏ sót câu -> coi như không đạt
        if i in picked:
            q["special_reason"] = evals[i]["trap"]
        else:
            q.pop("special_reason", None)
    log(f"   [special ] {len(picked)} câu is_special=true "
        f"({len(passed)} câu đạt ngưỡng)")
    return len(picked)
