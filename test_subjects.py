# -*- coding: utf-8 -*-
"""test_subjects.py — Nghiệm thu nhận diện môn học + chèn hướng dẫn riêng vào prompt.
Chạy: python3 test_subjects.py — KHÔNG gọi API, KHÔNG cần key. 0 token.
"""
import sys

import fitz

from stage_content import generate_content_one
from stage_essay import generate_essay_one
from stage_questions import generate_questions_one
from subjects import GENERAL, PROFILES, detect_subject, guide_block

ROW = {"module_slug": "chuong-1", "module_title": "Chương 1", "topic_slug": "bai-1",
       "topic_title": "Bài 1", "order": 1, "level": "Lớp 6",
       "page_start": 1, "page_end": 1}
LO = {"objectives": ["x"], "sections": [{"heading": "h", "points": ["p"]}],
      "key_points": ["k1"]}


class FakeClient:
    """Ghi lại prompt theo tag, trả về JSON tối thiểu hợp lệ."""
    def __init__(self):
        self.prompts = {}

    def pdf_part(self, data, name):
        return {"pdf": len(data)}

    def generate_json(self, parts, schema, tag, temperature=0.3):
        self.prompts[tag] = parts[-1]["text"]
        if tag == "content":
            return dict(LO)
        if tag == "questions":
            return {"questions": [{"question": "q", "A": "a", "B": "b", "C": "c",
                                   "D": "d", "correct_answer": "A",
                                   "explanation_vi": "e", "difficulty": 1}]}
        if tag == "validate":
            return {"answers": [{"index": 0, "answer": "A"}]}
        return {"questions": []}


def main():
    fails = []

    def check(cond, msg):
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            fails.append(msg)

    def key(**kw):
        return detect_subject(**kw)[0].key

    print("Nhận diện môn:")
    check(key(pdf_name="sgk-toan-4-tap-mot") == "toan", "tên file sgk-toan-4 -> toan")
    check(key(pdf_name="khtn-lop6") == "khoa-hoc", "khtn-lop6 -> khoa-hoc")
    check(key(pdf_name="sgk-khoa-hoc-4") == "khoa-hoc", "sgk-khoa-hoc-4 -> khoa-hoc")
    check(key(pdf_name="sgk-tieng-viet-3") == "ngu-van", "tieng-viet -> ngu-van")
    check(key(pdf_name="tieng-anh-6-global-success") == "tieng-anh", "tieng-anh -> tieng-anh")
    check(key(subject="Lịch sử và Địa lí") == "lich-su-dia-li", "--subject có dấu tiếng Việt")
    check(key(subject="Tin học", pdf_name="sgk-toan-6") == "tin-hoc",
          "--subject ưu tiên hơn tên file")
    check(key(profile_arg="general", pdf_name="sgk-toan-6") == "general",
          "--subject-profile ghi đè nhận diện tự động")
    check(key(pdf_name="sach") == "general", "không có manh mối -> general")
    check(key(titles=["Bài 1. Nguyên tử", "Bài 2. Tính chất của chất",
                      "Bài 3. Tế bào"]) == "khoa-hoc", "nhận diện từ mục lục (KHTN)")
    check(key(titles=["Phân số", "Phép cộng phân số"]) == "toan",
          "nhận diện từ mục lục (Toán)")
    check(key(titles=["Bài 1. Nguyên tử"]) == "general",
          "chỉ 1 tiêu đề khớp -> không đoán, dùng general")
    check(key(titles=["Ôn tập an toàn giao thông", "Bài 2"]) == "general",
          "'an toàn' không bị nhận nhầm là Toán")

    print("Khối hướng dẫn:")
    check(guide_block(GENERAL, "essay") == "", "general -> không chèn gì")
    check(guide_block(None, "mcq") == "", "None -> không chèn gì")
    for p in PROFILES.values():
        ok = all(guide_block(p, part) for part in ("content", "mcq", "essay"))
        check(ok, f"{p.key}: có đủ hướng dẫn content/mcq/essay")

    print("Chèn vào prompt:")
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "x")
    toan = PROFILES["toan"]
    c = FakeClient()
    generate_content_one(doc, ROW, c, subject_profile=toan)
    generate_questions_one(ROW, LO, c, validate=True, subject_profile=toan)
    generate_essay_one(doc, ROW, LO, c, subject_profile=toan)
    for tag in ("content", "questions", "validate", "essay"):
        check("HƯỚNG DẪN RIÊNG MÔN TOÁN" in c.prompts[tag], f"prompt {tag} có khối môn Toán")
    check("LỜI GIẢI TỪNG BƯỚC" in c.prompts["essay"], "tự luận Toán yêu cầu lời giải từng bước")

    g = FakeClient()
    generate_content_one(doc, ROW, g)
    generate_questions_one(ROW, LO, g, validate=True)
    generate_essay_one(doc, ROW, LO, g)
    check(all("HƯỚNG DẪN RIÊNG MÔN" not in t and "{subject_guide}" not in t
              for t in g.prompts.values()),
          "không truyền profile -> prompt giữ nguyên như cũ")

    print("\nKẾT QUẢ:", "PASS" if not fails else f"FAIL ({len(fails)})")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
