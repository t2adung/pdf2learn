# -*- coding: utf-8 -*-
"""test_special.py — Nghiệm thu pass đánh giá is_special (câu hấp dẫn cho video short).
Chạy: python3 test_special.py — KHÔNG gọi API, KHÔNG cần key. 0 token.
"""
import csv
import sys
import tempfile
from pathlib import Path

from gemini import GeminiError
from stage_export import QUESTION_COLS, export
from stage_questions import SPECIAL_VERSION, mark_special_one, needs_special

ROW = {"module_slug": "chuong-1", "module_title": "Chương 1",
       "topic_slug": "thuc-vat", "topic_title": "Thực vật quanh ta",
       "order": 1, "level": "Lớp 6", "page_start": 1, "page_end": 2}


def _qs(n):
    return [{"question": f"Câu {i}?", "A": "a", "B": "b", "C": "c", "D": "d",
             "correct_answer": "A", "explanation_vi": "vì a", "difficulty": 1}
            for i in range(n)]


def _ev(i, gut="B", hes=4, hook=4, trap="hiểu lầm phổ biến"):
    return {"index": i, "trap": trap, "adult_gut_answer": gut,
            "adult_hesitation": hes, "hook": hook}


class FakeClient:
    def __init__(self, evals=None, exc=None):
        self.evals, self.exc, self.calls, self.prompt = evals or [], exc, 0, ""

    def generate_json(self, parts, schema, tag, temperature=0.3):
        assert tag == "special"
        self.calls += 1
        self.prompt = parts[0]["text"]
        if self.exc:
            raise self.exc
        return {"evals": self.evals}


def _special_idx(qs):
    return [i for i, q in enumerate(qs) if q["is_special"]]


def main():
    fails = []

    def check(cond, msg):
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            fails.append(msg)

    # ---- luật ngưỡng (đáp án đúng của mọi câu = A) ----
    qs = _qs(6)
    fc = FakeClient([
        _ev(0, gut="A", hes=4, hook=4),            # trực giác đúng nhưng nhiều người phân vân -> true
        _ev(1, gut="B", hes=2, hook=4),            # trực giác SAI -> true dù hesitation thấp
        _ev(2, gut="A", hes=3, hook=5),            # trực giác đúng, chỉ "phải nghĩ" -> false
        _ev(3, gut="B", hes=5, hook=3),            # hook thấp -> false
        _ev(4, gut="B", hes=5, hook=5, trap=""),   # không có hiểu lầm thật -> false
        _ev(5, gut="?", hes=5, hook=5),            # gut không hợp lệ -> false
    ])
    n = mark_special_one(ROW, qs, fc)
    check(_special_idx(qs) == [0, 1] and n == 2, f"luật ngưỡng chọn đúng câu 0, 1 (được {_special_idx(qs)})")
    check("Đáp án đúng: A" in fc.prompt, "prompt gửi kèm đáp án đúng")
    check("tối đa" not in fc.prompt.lower(), "prompt không còn con số quota mồi model")
    check(qs[1]["special_reason"] == "hiểu lầm phổ biến", "special_reason = trap")
    check(qs[2]["special_eval"] == {"gut": "A", "trap": "hiểu lầm phổ biến",
                                    "hesitation": 3, "hook": 5},
          "special_eval lưu điểm để soát (cả câu false)")
    check(all(q["special_v"] == SPECIAL_VERSION for q in qs) and not needs_special(qs),
          "mọi câu gắn special_v hiện hành")
    check(all("special_reason" not in q for q in qs if not q["is_special"]),
          "câu false không có special_reason")

    # ---- trần 2 câu / bài, xếp theo hesitation rồi hook ----
    qs = _qs(5)
    mark_special_one(ROW, qs, FakeClient([_ev(0, hes=4, hook=4), _ev(1, hes=5, hook=4),
                                          _ev(2, hes=4, hook=5), _ev(3, hes=5, hook=5),
                                          _ev(4, hes=4, hook=4)]))
    check(_special_idx(qs) == [1, 3], f"trần 2 câu, lấy điểm cao nhất (được {_special_idx(qs)})")

    # ---- bài toàn câu hiển nhiên -> 0 câu, không ép đủ số ----
    qs = _qs(8)
    n = mark_special_one(ROW, qs, FakeClient([_ev(i, gut="A", hes=1, hook=2, trap="")
                                              for i in range(8)]))
    check(n == 0 and not any(q["is_special"] for q in qs) and not needs_special(qs),
          "bài toàn câu dễ -> 0 câu true (không có sàn)")

    # ---- index lạ / trùng bị bỏ; AI bỏ sót câu -> false ----
    qs = _qs(3)
    mark_special_one(ROW, qs, FakeClient([_ev(0), _ev(0, hook=1), _ev(99), {"index": "x"}]))
    check(_special_idx(qs) == [0], "index trùng giữ dòng đầu, index lạ bị bỏ")
    check("special_eval" not in qs[1] and qs[1]["is_special"] is False,
          "câu AI bỏ sót -> false, không có special_eval")

    # ---- lỗi AI tạm thời: không gán key (lần sau thử lại); lỗi quota: nổi lên ----
    qs = _qs(4)
    mark_special_one(ROW, qs, FakeClient(exc=ValueError("JSON hỏng")))
    check(needs_special(qs) and all("is_special" not in q for q in qs),
          "lỗi parse -> KHÔNG gán is_special, để chạy lại")
    try:
        mark_special_one(ROW, qs, FakeClient(exc=GeminiError("QUOTA")))
        check(False, "GeminiError phải nổi lên cho main.py resume")
    except GeminiError:
        check(True, "GeminiError (quota) nổi lên cho main.py resume")
    fc = FakeClient()
    check(mark_special_one(ROW, [], fc) == 0 and fc.calls == 0,
          "topic 0 câu -> không gọi AI")

    # ---- cache cũ / tiêu chí v1 / dở dang -> cần chấm lại ----
    check(needs_special(_qs(1)), "câu cache cũ (chưa chấm) -> needs_special")
    v1 = _qs(2)
    for q in v1:
        q["is_special"] = True                     # chấm theo v1: có is_special, thiếu special_v
    check(needs_special(v1), "câu chấm theo tiêu chí v1 -> needs_special (tự chấm lại)")
    mixed = _qs(2)
    mixed[0].update(is_special=False, special_v=SPECIAL_VERSION)
    check(needs_special(mixed), "trộn câu đã/chưa chấm -> needs_special")

    # ---- CSV: cột cuối is_special, true/false; câu chưa đánh giá -> false ----
    check(QUESTION_COLS[-1] == "is_special", "is_special là cột CUỐI của multichoice.csv")
    qs = _qs(3)
    qs[0]["is_special"] = True
    qs[1]["is_special"] = False                     # qs[2]: chưa đánh giá
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        export([ROW], {}, {}, {ROW["topic_slug"]: qs}, out,
               pdf_name="x.pdf", model="mock")
        with open(out / "multichoice.csv", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
        check(header[-1] == "is_special", "header CSV kết thúc bằng is_special")
        check([r[-1] for r in rows] == ["true", "false", "false"],
              "giá trị true / false / false (chưa đánh giá -> false)")

    print("\nKẾT QUẢ:", "PASS" if not fails else f"FAIL ({len(fails)})")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
