# -*- coding: utf-8 -*-
"""Stage 6 (v2): Cross-model review — model thứ hai thẩm định lại output.

Nguyên tắc "bốn mắt": model khác gốc thường không mắc cùng loại lỗi với
model sinh nội dung. Reviewer chấm 4 hạng mục:
  1. Đáp án: tự giải từng câu, đối chiếu correct_answer
  2. Chất lượng distractor: có lộ liễu / mơ hồ / nhiều đáp án đúng không
  3. Nội dung: mâu thuẫn nội bộ, chỗ khó hiểu so với trình độ, nghi bịa
  4. Coverage: key point nào chưa có câu hỏi kiểm tra

Mặc định CHỈ BÁO CÁO (report-only). Việc sửa/loại là quyết định của người
dùng hoặc cờ --review-fix (chỉ tự loại câu hỏi severity=high).

Reviewer "gemini-pro" là chế độ duy nhất được đính kèm trang PDF nguồn
=> kiểm tra thêm faithfulness (nội dung có trung thực với sách gốc không).
"""
from utils import log, warn

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer"},
        "content_issues": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                "issue": {"type": "string"},
                "suggestion": {"type": "string"},
            },
            "required": ["severity", "issue", "suggestion"],
        }},
        "question_issues": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                "issue": {"type": "string"},
                "suggestion": {"type": "string"},
            },
            "required": ["index", "severity", "issue", "suggestion"],
        }},
        "coverage_gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["overall_score", "content_issues", "question_issues", "coverage_gaps"],
}

REVIEW_PROMPT = """Bạn là chuyên gia thẩm định học liệu độc lập, nghiêm khắc và công tâm.
Thẩm định bài học và bộ câu hỏi trắc nghiệm dưới đây (trình độ "{level}",
bài "{topic_title}").

=== NỘI DUNG BÀI HỌC ===
{content}

=== KEY POINTS PHẢI ĐƯỢC KIỂM TRA ===
{key_points}

=== BỘ CÂU HỎI (index tính từ 0) ===
{questions}

Nhiệm vụ thẩm định:
1. ĐÁP ÁN: tự giải từng câu độc lập dựa trên nội dung bài học. Câu nào
   correct_answer sai, hoặc có >1 phương án chấp nhận được, hoặc không
   trả lời được từ nội dung -> question_issues với severity=high.
2. DISTRACTOR: phương án nhiễu vô lý lộ liễu, lệch hẳn độ dài, hoặc
   dùng "tất cả các ý trên" -> severity=medium.
3. NỘI DUNG: mâu thuẫn nội bộ, diễn đạt khó hiểu so với trình độ,
   thông tin đáng ngờ (số liệu/tên riêng có vẻ bịa) -> content_issues.
   {faithfulness_extra}
4. COVERAGE: liệt kê key point CHƯA có câu hỏi nào kiểm tra -> coverage_gaps.

overall_score: 1-10 (10 = dùng được ngay, <=5 = cần làm lại).
severity=high chỉ dành cho lỗi khiến người học hiểu sai kiến thức.
Viết issue/suggestion bằng tiếng Việt, ngắn gọn, cụ thể."""

FAITHFULNESS_EXTRA = """Ngoài ra, ĐỐI CHIẾU với các trang sách gốc đính kèm:
   nội dung nào trong "## Nội dung chính" KHÔNG có trong sách -> content_issues
   severity=high (ghi rõ 'không có trong nguồn')."""


def _fmt_questions(questions: list) -> str:
    lines = []
    for i, q in enumerate(questions):
        lines.append(f"[{i}] {q['question']}")
        for letter in "ABCD":
            mark = " (*)" if q["correct_answer"] == letter else ""
            lines.append(f"    {letter}. {q[letter]}{mark}")
        lines.append(f"    Giải thích: {q['explanation_vi']} | difficulty: {q['difficulty']}")
    return "\n".join(lines)


def review_one(row: dict, content_entry: dict, questions_list: list,
               reviewer, with_pdf=None) -> dict:
    """Review MỘT topic. with_pdf: (pdf_doc, gemini_client) nếu reviewer đọc PDF."""
    slug = row["topic_slug"]
    prompt = REVIEW_PROMPT.format(
        level=row["level"], topic_title=row["topic_title"],
        content=content_entry["content_markdown"],
        key_points="\n".join(f"- {k}" for k in content_entry.get("key_points", [])),
        questions=_fmt_questions(questions_list) if questions_list else "(chưa có câu hỏi)",
        faithfulness_extra=FAITHFULNESS_EXTRA if with_pdf else "")
    parts = [{"text": prompt}]
    if with_pdf:
        from stage_content import cut_pages
        doc, gclient = with_pdf
        sub = cut_pages(doc, row["page_start"], row["page_end"])
        parts.insert(0, gclient.pdf_part(sub, f"{slug}.pdf"))
    log(f"   [review  ] thẩm định {len(questions_list)} câu hỏi...")
    try:
        res = reviewer.generate_json(parts, REVIEW_SCHEMA, tag="review")
        res.setdefault("content_issues", [])
        res.setdefault("question_issues", [])
        res.setdefault("coverage_gaps", [])
        n_high = sum(1 for x in res["question_issues"] + res["content_issues"]
                     if x.get("severity") == "high")
        log(f"   [review  ] score {res.get('overall_score', '?')}/10, "
            f"{n_high} lỗi nặng, {len(res['coverage_gaps'])} key point chưa phủ")
        return res
    except Exception as e:
        warn(f"{slug}: review lỗi ({e}) -> đánh dấu chưa review.")
        return {"error": str(e)}


def apply_fixes(questions: dict, review: dict) -> tuple:
    """--review-fix: loại câu hỏi bị flag severity=high. Trả về (questions_mới, log_loại)."""
    fixed, removed_log = {}, []
    for slug, qs in questions.items():
        rev = review.get(slug, {})
        bad = {i["index"] for i in rev.get("question_issues", [])
               if i.get("severity") == "high"}
        kept = [q for i, q in enumerate(qs) if i not in bad]
        for i in sorted(bad):
            if i < len(qs):
                removed_log.append({"topic_slug": slug, "question": qs[i]["question"],
                                    "reason": next((x["issue"] for x in rev["question_issues"]
                                                    if x["index"] == i), "")})
        fixed[slug] = kept
    return fixed, removed_log


def write_report(review: dict, structure: list, out_path):
    """review_report.md: bản dễ đọc cho người QC duyệt."""
    lines = ["# Review Report (cross-model)\n"]
    for row in structure:
        slug = row["topic_slug"]
        r = review.get(slug)
        if not r or "error" in r or "skipped" in r:
            lines.append(f"## {slug} — ⚠️ {r}\n" if r else f"## {slug} — chưa review\n")
            continue
        lines.append(f"## {slug} — {row['topic_title']} — **{r.get('overall_score','?')}/10**\n")
        if r["content_issues"]:
            lines.append("**Nội dung:**")
            for x in r["content_issues"]:
                lines.append(f"- [{x['severity']}] {x['issue']} → _{x['suggestion']}_")
        if r["question_issues"]:
            lines.append("**Câu hỏi:**")
            for x in r["question_issues"]:
                lines.append(f"- [{x['severity']}] câu #{x['index']}: {x['issue']} → _{x['suggestion']}_")
        if r["coverage_gaps"]:
            lines.append("**Key point chưa có câu hỏi:**")
            for g in r["coverage_gaps"]:
                lines.append(f"- {g}")
        if not (r["content_issues"] or r["question_issues"] or r["coverage_gaps"]):
            lines.append("_Không phát hiện vấn đề._")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
