# -*- coding: utf-8 -*-
"""export_json.py — Map dữ liệu nội bộ pipeline -> JSON bài học theo format đích.
THUẦN CODE, 0 token AI.

Format đích (theo mẫu lich_su_la_gi_learning_object.json):
{
  "title", "subject", "grade", "prompt_version",
  "concept_overview", "objectives", "hook",
  "key_terms":      [{term, definition, example}],
  "sections":       [{heading, icon_hint, formula?, points}],
  "real_life", "memory_hooks", "quick_review",
  "misconceptions": [{wrong, correct}],
  "infographic_html": "<!doctype html>...",   # xem bên dưới
  "quiz": [{question, options[4], answer_index, explanation, bloom, difficulty}]
}

Khác biệt so với dữ liệu nội bộ (và lý do):
- quiz:      nội bộ dùng A/B/C/D + correct_answer + difficulty 1-3 (khớp template
             multichoice.csv). Mapper đổi sang options + answer_index + bloom/
             difficulty dạng chữ.
- key_points: GIỮ NỘI BỘ, không xuất — nó là công cụ đảm bảo coverage câu hỏi
             (Stage 5) và mốc đối chiếu cho reviewer (Stage 6), không phải nội
             dung hiển thị cho người học.
- infographic_html: NHÚNG THẲNG cả trang HTML (đủ <!doctype>/<style>) làm 1
             string JSON — không phải file rời như stage_images.py ghi ra
             images/. Gọi lại infographic_html.render() ngay tại bước export
             (THUẦN CODE, 0 token, deterministic — không cần lưu trung gian).
             "Mã hoá" ở đây chỉ là escape chuỗi JSON chuẩn (json.dumps tự lo
             dấu ", xuống dòng...) — KHÔNG base64: base64 sẽ chỉ làm bloat
             kích thước (~33%) trong khi JSON string đã an toàn 100% qua CSV
             round-trip (đã có test), và frontend nhận về là dùng được ngay
             (vd `<iframe srcdoc={value}>`) mà không cần decode gì thêm.
             Rỗng ("") nếu Learning Object không có gì để vẽ.
"""
import json
import re

from infographic_html import render as render_infographic_html

PROMPT_VERSION = "v3"

# difficulty nội bộ 1-3 (khớp cột multichoice.csv) -> 2 trục của format đích.
# 1 = nhớ/nhận biết, 2 = hiểu, 3 = vận dụng (định nghĩa ở QUESTIONS_PROMPT).
BLOOM_MAP = {1: "nho", 2: "hieu", 3: "van_dung"}
DIFFICULTY_MAP = {1: "de", 2: "trung_binh", 3: "kho"}
LETTER_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}


def _grade_from_level(level: str) -> str:
    """'Lớp 6' -> '6'; không match số thì trả nguyên chuỗi level."""
    m = re.search(r"\d+", level or "")
    return m.group(0) if m else (level or "")


def map_question(q: dict) -> dict:
    """1 câu hỏi nội bộ (A/B/C/D) -> item quiz của format đích."""
    d = min(3, max(1, int(q.get("difficulty", 1))))
    return {
        "question": q["question"],
        "options": [q["A"], q["B"], q["C"], q["D"]],
        "answer_index": LETTER_INDEX[q["correct_answer"]],
        "explanation": q.get("explanation_vi", ""),
        "bloom": BLOOM_MAP[d],
        "difficulty": DIFFICULTY_MAP[d],
    }


def compose_learning_object(row: dict, lo: dict, questions: list,
                            subject: str = "", grade: str = "",
                            include_quiz: bool = True,
                            include_infographic: bool = True) -> dict:
    """Ghép bản ghi structure + Learning Object cache + câu hỏi -> JSON đích.

    Thứ tự key cố định theo file mẫu (deterministic — diff được giữa 2 lần chạy).
    """
    lo = lo or {}
    out = {
        "title": row["topic_title"],
        "subject": subject,
        "grade": grade or _grade_from_level(row.get("level", "")),
        "prompt_version": PROMPT_VERSION,
        "concept_overview": lo.get("concept_overview", ""),
        "objectives": lo.get("objectives", []),
        "hook": lo.get("hook", ""),
        "key_terms": lo.get("key_terms", []),
        "sections": [{
            "heading": s.get("heading", ""),
            "icon_hint": s.get("icon_hint", ""),
            **({"formula": s["formula"]} if s.get("formula") else {}),
            "points": s.get("points", []),
        } for s in lo.get("sections", [])],
        "real_life": lo.get("real_life", []),
        "memory_hooks": lo.get("memory_hooks", []),
        "misconceptions": lo.get("misconceptions", []),
        "quick_review": lo.get("quick_review", []),
    }
    if include_infographic:
        try:
            out["infographic_html"] = render_infographic_html(lo, row["topic_title"])
        except ValueError:
            out["infographic_html"] = ""  # Learning Object rỗng (vd cache v1 cũ)
    if include_quiz:
        out["quiz"] = [map_question(q) for q in (questions or [])
                       if q.get("correct_answer") in LETTER_INDEX]
    # cache v1 (blob markdown) lọt vào đây -> giữ dưới tên rõ ràng, không mất dữ liệu
    if "content_markdown" in lo:
        out["legacy_markdown"] = lo["content_markdown"]
    return out


def dumps(obj: dict, compact: bool = False) -> str:
    if compact:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(obj, ensure_ascii=False, indent=2)
