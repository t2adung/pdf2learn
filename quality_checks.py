# -*- coding: utf-8 -*-
"""Quality checks thuần code — 0 token, luôn bật.

Bắt các "tell" kinh điển của câu hỏi trắc nghiệm do AI sinh:
1. Thiên vị vị trí đáp án (model rất hay dồn đáp án đúng vào 1 chữ cái)
2. Đáp án đúng luôn là phương án DÀI NHẤT (học sinh tinh ý đoán được không cần học)
3. Phương án trùng nhau trong cùng 1 câu
4. Câu hỏi gần-trùng-lặp giữa các topic (near-duplicate)
5. Thiếu giải thích
"""
import difflib
from collections import Counter

from utils import strip_diacritics

LETTER_BIAS_MIN_N = 12      # đủ mẫu mới kết luận thiên vị
LETTER_BIAS_THRESHOLD = 0.4  # 1 chữ cái chiếm >40% là bất thường (kỳ vọng 25%)
LONGEST_BIAS_MIN_N = 10
LONGEST_BIAS_THRESHOLD = 0.6
DUP_RATIO = 0.92
DUP_MAX_REPORT = 10


def _norm(text: str) -> str:
    return " ".join(strip_diacritics(text).lower().split())


def run_checks(questions_by_slug: dict) -> list:
    """Trả về danh sách cảnh báo (chuỗi). questions_by_slug: {slug: [q...]}."""
    warnings = []
    flat = [(slug, i, q) for slug, qs in questions_by_slug.items()
            if slug != "_dropped" for i, q in enumerate(qs)]
    n = len(flat)
    if n == 0:
        return warnings

    # 1. Phân bố chữ cái đáp án đúng
    letters = Counter(q["correct_answer"] for _, _, q in flat)
    if n >= LETTER_BIAS_MIN_N:
        letter, cnt = letters.most_common(1)[0]
        if cnt / n > LETTER_BIAS_THRESHOLD:
            warnings.append(
                f"[phân bố đáp án] Chữ '{letter}' chiếm {cnt}/{n} câu "
                f"({cnt/n:.0%}, kỳ vọng ~25%) — model đang thiên vị vị trí; "
                f"cân nhắc --redo-from 5. Phân bố: "
                + ", ".join(f"{k}={v}" for k, v in sorted(letters.items())))

    # 2. Đáp án đúng có phải luôn dài nhất không
    if n >= LONGEST_BIAS_MIN_N:
        longest = sum(
            1 for _, _, q in flat
            if len(q[q["correct_answer"]]) > max(len(q[c]) for c in "ABCD"
                                                 if c != q["correct_answer"]))
        if longest / n > LONGEST_BIAS_THRESHOLD:
            warnings.append(
                f"[độ dài phương án] Đáp án đúng là phương án dài nhất ở "
                f"{longest}/{n} câu ({longest/n:.0%}) — người làm bài đoán được "
                f"không cần kiến thức; cần cân bằng độ dài distractor.")

    # 3. Phương án trùng nhau trong cùng câu + thiếu giải thích
    for slug, i, q in flat:
        opts = [_norm(q[c]) for c in "ABCD"]
        if len(set(opts)) < 4:
            warnings.append(f"[trùng phương án] {slug} câu #{i}: có phương án "
                            f"trùng nhau — {q['question'][:60]}...")
        if not q.get("explanation_vi", "").strip():
            warnings.append(f"[thiếu giải thích] {slug} câu #{i}")

    # 4. Câu hỏi gần-trùng giữa các topic (prefilter theo độ dài cho nhanh)
    normed = [(slug, i, _norm(q["question"])) for slug, i, q in flat]
    dups = []
    for a in range(len(normed)):
        sa, ia, ta = normed[a]
        for b in range(a + 1, len(normed)):
            sb, ib, tb = normed[b]
            if abs(len(ta) - len(tb)) > 0.2 * max(len(ta), len(tb), 1):
                continue
            sm = difflib.SequenceMatcher(None, ta, tb)
            if sm.quick_ratio() >= DUP_RATIO and sm.ratio() >= DUP_RATIO:
                dups.append(f"[gần trùng] {sa}#{ia} ≈ {sb}#{ib}: {ta[:60]}...")
                if len(dups) >= DUP_MAX_REPORT:
                    dups.append(f"[gần trùng] ... (dừng báo cáo ở {DUP_MAX_REPORT} cặp)")
                    break
        if len(dups) > DUP_MAX_REPORT:
            break
    warnings.extend(dups)
    return warnings
