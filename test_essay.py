# -*- coding: utf-8 -*-
"""test_essay.py — Nghiệm thu bước sinh câu hỏi tự luận + import-payload.json.
Chạy: python3 test_essay.py — KHÔNG gọi API, KHÔNG cần key. 0 token.
"""
import csv
import json
import sys
import tempfile
from pathlib import Path

import fitz

from stage_essay import ESSAY_MAX, generate_essay_one
from stage_export import export

ROW = {"module_slug": "unit-3-tenses", "module_title": "Unit 3 — Các thì cơ bản",
       "topic_slug": "present-perfect", "topic_title": "Thì hiện tại hoàn thành",
       "order": 1, "level": "A2", "page_start": 1, "page_end": 1}
LO = {"objectives": ["Nêu được cấu trúc thì hiện tại hoàn thành."],
      "sections": [{"heading": "Cấu trúc", "points": ["S + have/has + V3/ed."]}],
      "key_points": ["S + have/has + V3/ed."]}


class FakeClient:
    """Trả về 16 câu (vượt ESSAY_MAX) + 1 câu rỗng + difficulty lệch để test làm sạch."""
    def __init__(self):
        self.parts = None

    def pdf_part(self, data, name):
        return {"pdf": len(data)}

    def generate_json(self, parts, schema, tag, temperature=0.3):
        assert tag == "essay"
        self.parts = parts
        qs = [{"question": "", "correct_answer": "x", "explanation_vi": "", "difficulty": 1}]
        qs += [{"question": f"Câu {i}?", "correct_answer": f"Đáp án {i}",
                "explanation_vi": "giải thích", "difficulty": d}
               for i, d in enumerate([0, 5, "2"] + [1, 2, 3] * 4 + [1])]
        return {"questions": qs}


def main():
    fails = []

    def check(cond, msg):
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            fails.append(msg)

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Present perfect")
    client = FakeClient()
    essays = generate_essay_one(doc, ROW, LO, client)
    prompt = client.parts[-1]["text"]
    check(client.parts[0] == {"pdf": client.parts[0]["pdf"]}, "gửi kèm sub-PDF của topic")
    check("BOX" in prompt and "ĐỊNH NGHĨA" in prompt and "LIỆT KÊ" in prompt,
          "prompt ưu tiên box màu + định nghĩa/liệt kê/giải thích")
    check(len(essays) == ESSAY_MAX, f"cắt còn tối đa {ESSAY_MAX} câu, bỏ câu rỗng")
    check([q["difficulty"] for q in essays[:3]] == [1, 3, 2], "difficulty kẹp 1..3")

    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        export([ROW], {"present-perfect": LO}, {}, {"present-perfect": []}, out,
               pdf_name="x.pdf", model="mock", essays={"present-perfect": essays},
               teacher_id="t-1")
        payload = json.loads((out / "import-payload.json").read_text(encoding="utf-8"))
        sample_topic_keys = ["module_slug", "module_title", "topic_slug", "topic_title",
                             "order", "level", "content", "page_start"]
        sample_ex_keys = ["type", "topic_slug", "question", "correct_answer",
                          "explanation_vi", "difficulty"]
        check(list(payload) == ["teacher_id", "topics", "exercises"], "key gốc đúng mẫu")
        check(payload["teacher_id"] == "t-1", "teacher_id lấy từ tham số")
        check(list(payload["topics"][0]) == sample_topic_keys, "key topic đúng mẫu")
        check(payload["topics"][0]["content"].strip() != "", "topic có content")
        check(all(list(e) == sample_ex_keys and e["type"] == "essay"
                  for e in payload["exercises"]), "key exercise đúng mẫu, type=essay")
        check(len(payload["exercises"]) == ESSAY_MAX, "đủ số câu tự luận")
        with open(out / "essay.csv", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        check(open(out / "essay.csv", "rb").read(3) == b"\xef\xbb\xbf", "essay.csv có UTF-8 BOM")
        check(len(rows) == ESSAY_MAX and list(rows[0]) == ["topic_slug", "question",
              "correct_answer", "explanation_vi", "difficulty"], "essay.csv đúng cột, đủ dòng")
        check(rows[0]["question"] == essays[0]["question"], "essay.csv khớp nội dung câu hỏi")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        check(manifest["stats"]["essays"] == ESSAY_MAX, "manifest đếm câu tự luận")

        out2 = Path(td) / "noessay"
        export([ROW], {"present-perfect": LO}, {}, {}, out2, pdf_name="x.pdf", model="mock")
        check(not (out2 / "import-payload.json").exists(),
              "essays=None (--no-essay) thì không ghi import-payload.json")
        check(not (out2 / "essay.csv").exists(), "essays=None thì không ghi essay.csv")

    print("\nKẾT QUẢ:", "PASS" if not fails else f"FAIL ({len(fails)})")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
