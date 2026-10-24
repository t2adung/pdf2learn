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

from stage_essay import ESSAY_MAX, _dup_key, _is_dup, generate_essay_one
from stage_export import export, export_essay_more

ROW = {"module_slug": "unit-3-tenses", "module_title": "Unit 3 — Các thì cơ bản",
       "topic_slug": "present-perfect", "topic_title": "Thì hiện tại hoàn thành",
       "order": 1, "level": "A2", "page_start": 1, "page_end": 1}
LO = {"objectives": ["Nêu được cấu trúc thì hiện tại hoàn thành."],
      "sections": [{"heading": "Cấu trúc", "points": ["S + have/has + V3/ed."]}],
      "key_points": ["S + have/has + V3/ed."]}


class FakeClient:
    """Trả về 16 câu (vượt ESSAY_MAX) + 1 câu rỗng + level lệch để test làm sạch."""
    def __init__(self):
        self.parts = None

    def pdf_part(self, data, name):
        return {"pdf": len(data)}

    def generate_json(self, parts, schema, tag, temperature=0.3):
        assert tag == "essay"
        self.parts = parts
        qs = [{"question": "", "correct_answer": "x", "explanation_vi": "", "level": 1}]
        qs += [{"question": f"Câu {i}?", "correct_answer": f"(1) [1đ] Đáp án {i}",
                "explanation_vi": "giải thích", "level": lv}
               for i, lv in enumerate([0, 5, "2", 4] + [1, 2, 3] * 4)]
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
    check("BOX" in prompt and "VẬN DỤNG CAO" in prompt and "THANG ĐIỂM" in prompt,
          "prompt ưu tiên box màu + ma trận 4 mức + thang điểm theo ý")
    check("{" not in prompt.split("NỘI DUNG BÀI HỌC")[0], "prompt đã format hết placeholder")
    check(len(essays) == ESSAY_MAX, f"cắt còn tối đa {ESSAY_MAX} câu, bỏ câu rỗng")
    check([q["level"] for q in essays[:4]] == [1, 4, 2, 4], "level kẹp 1..4")
    check([q["difficulty"] for q in essays[:4]] == [1, 3, 2, 3],
          "difficulty = level kẹp 1..3 (Vận dụng cao -> 3)")

    # ---- sinh THÊM (--essay-more): truyền câu đã có, chỉ nhận câu mới ----
    more_client = FakeClient()
    existing = [dict(essays[0]), dict(essays[1])]
    added = generate_essay_one(doc, ROW, LO, more_client, existing=existing, round_no=2)
    more_prompt = more_client.parts[-1]["text"]
    check("CÁC CÂU ĐÃ CÓ CỦA BÀI NÀY (2 câu)" in more_prompt
          and essays[0]["question"] in more_prompt, "prompt sinh thêm liệt kê câu đã có")
    check(all(q["question"] not in {e["question"] for e in existing} for q in added),
          "bỏ câu trùng nguyên văn với câu đã có")
    check(added and all(q.get("round") == 2 for q in added), "câu sinh thêm gắn round")
    check("round" not in essays[0], "lượt đầu không gắn round")
    check("BIẾN THỂ" in prompt and all(q["source"] in ("book", "variant", "new")
                                       for q in essays), "prompt có biến thể + field source")

    # ---- so trùng: diễn đạt lại = trùng; đổi số / đổi khái niệm = câu mới ----
    def dup(a, b):
        return _is_dup(_dup_key(a), [_dup_key(b)])
    check(dup("Nêu khái niệm mạng LAN.", "Hãy nêu khái niệm về mạng LAN."), "trùng: thêm hư từ")
    check(dup("Mạng LAN là gì?", "Nêu khái niệm mạng LAN."), "trùng: 'là gì' = 'khái niệm'")
    check(dup("Kể tên các khu vực chính trong nhà ở.",
              "Hãy kể tên các khu vực chính của nhà ở."), "trùng: đổi hư từ")
    check(not dup("Nêu khái niệm mạng LAN.", "Nêu khái niệm mạng WAN."),
          "không trùng: khác khái niệm")
    check(not dup("Một ô tô đi 120 km trong 2 giờ. Tính vận tốc.",
                  "Một ô tô đi 150 km trong 3 giờ. Tính vận tốc."),
          "không trùng: biến thể đổi số liệu")
    check(dup("Một ô tô đi 120 km trong 2 giờ. Tính vận tốc.",
              "Một ô tô đi 120 km trong 2 giờ. Hãy tính vận tốc của ô tô."),
          "trùng: cùng số liệu, chỉ diễn đạt lại")
    check(not dup("Nêu vai trò của nhà ở đối với con người.",
                  "Nêu đặc điểm chung của nhà ở Việt Nam."), "không trùng: khác ý")

    para_client = FakeClient()
    para_client.generate_json = lambda parts, schema, tag, temperature=0: {"questions": [
        {"level": 1, "source": "new", "question": "Hãy nêu khái niệm về mạng LAN.",
         "correct_answer": "(1) [1đ] ...", "explanation_vi": ""},
        {"level": 1, "source": "new", "question": "Nêu khái niệm mạng WAN.",
         "correct_answer": "(1) [1đ] ...", "explanation_vi": ""}]}
    got = generate_essay_one(doc, ROW, LO, para_client, round_no=3, existing=[
        {"question": "Mạng LAN là gì?", "correct_answer": "x"}])
    check([q["question"] for q in got] == ["Nêu khái niệm mạng WAN."],
          "sinh thêm: bỏ câu diễn đạt lại câu cũ, giữ câu mới")

    with tempfile.TemporaryDirectory() as td:
        out_more = Path(td) / "essay-more-02"
        n_more = export_essay_more([ROW], {"present-perfect": essays + added}, out_more, 2)
        with open(out_more / "essay.csv", encoding="utf-8-sig", newline="") as f:
            more_rows = list(csv.DictReader(f))
        check(n_more == len(added) == len(more_rows)
              and {r["question"] for r in more_rows} == {q["question"] for q in added},
              "essay-more-NN/essay.csv chỉ chứa câu của lượt đó")

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
              "answer", "explanation_vi", "difficulty"], "essay.csv đúng cột template, đủ dòng")
        check(rows[0]["answer"] == essays[0]["correct_answer"], "cột answer = đáp án mẫu")
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
