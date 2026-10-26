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
from stage_questions import mark_special_one, needs_special

ROW = {"module_slug": "chuong-1", "module_title": "Chương 1",
       "topic_slug": "thuc-vat", "topic_title": "Thực vật quanh ta",
       "order": 1, "level": "Lớp 6", "page_start": 1, "page_end": 2}


def _qs(n):
    return [{"question": f"Câu {i}?", "A": "a", "B": "b", "C": "c", "D": "d",
             "correct_answer": "A", "explanation_vi": "vì a", "difficulty": 1}
            for i in range(n)]


class FakeClient:
    def __init__(self, picks=None, exc=None):
        self.picks, self.exc, self.calls = picks or [], exc, 0

    def generate_json(self, parts, schema, tag, temperature=0.3):
        assert tag == "special"
        self.calls += 1
        if self.exc:
            raise self.exc
        return {"picks": self.picks}


def main():
    fails = []

    def check(cond, msg):
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            fails.append(msg)

    # ---- quota ~25%, index lạ / trùng / sai kiểu bị bỏ ----
    qs = _qs(8)                                     # tối đa round(8*0.25) = 2 câu
    picks = [{"index": 5, "reason": "bất ngờ"}, {"index": 5, "reason": "trùng"},
             {"index": 99, "reason": "lạ"}, {"index": "x", "reason": "sai kiểu"},
             {"index": 1, "reason": "đời sống"}, {"index": 2, "reason": "vượt quota"}]
    n = mark_special_one(ROW, qs, FakeClient(picks))
    check(n == 2, f"chỉ chọn tối đa 2/8 câu (được {n})")
    check([i for i, q in enumerate(qs) if q["is_special"]] == [1, 5],
          "đúng câu 1, 5 được đánh dấu")
    check(qs[5]["special_reason"] == "bất ngờ", "giữ reason của lần chọn đầu")
    check(not needs_special(qs), "mọi câu đều có key is_special sau khi đánh giá")
    check(all("special_reason" not in q for q in qs if not q["is_special"]),
          "câu false không có special_reason")

    # ---- không có câu nào đạt -> tất cả false, không ép đủ số ----
    qs = _qs(4)
    check(mark_special_one(ROW, qs, FakeClient([])) == 0 and not needs_special(qs)
          and not any(q["is_special"] for q in qs), "picks rỗng -> toàn bộ false")

    # ---- topic ít câu vẫn được chọn tối đa 1 ----
    qs = _qs(2)
    mark_special_one(ROW, qs, FakeClient([{"index": 0, "reason": "r"},
                                          {"index": 1, "reason": "r"}]))
    check(sum(q["is_special"] for q in qs) == 1, "topic 2 câu -> tối đa 1 câu")

    # ---- lỗi AI tạm thời: không gán key (lần sau thử lại); lỗi quota: nổi lên ----
    qs = _qs(4)
    mark_special_one(ROW, qs, FakeClient(exc=ValueError("JSON hỏng")))
    check(needs_special(qs), "lỗi parse -> KHÔNG gán is_special, để chạy lại")
    try:
        mark_special_one(ROW, qs, FakeClient(exc=GeminiError("QUOTA")))
        check(False, "GeminiError phải nổi lên cho main.py resume")
    except GeminiError:
        check(True, "GeminiError (quota) nổi lên cho main.py resume")
    fc = FakeClient()
    check(mark_special_one(ROW, [], fc) == 0 and fc.calls == 0,
          "topic 0 câu -> không gọi AI")

    # ---- cache cũ thiếu key -> cần đánh giá; trộn câu có/không key (dở dang) ----
    check(needs_special(_qs(1)), "câu cache cũ (thiếu key) -> needs_special")
    mixed = _qs(2)
    mixed[0]["is_special"] = False
    check(needs_special(mixed), "trộn câu đã/chưa đánh giá -> needs_special")

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
