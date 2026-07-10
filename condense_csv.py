#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""condense_csv.py — Hậu xử lý topics.csv ĐÃ XUẤT (0 token, thuần code).

Làm 2 việc trên cột `content` (markdown):
  1. ẢNH: bỏ ảnh trang sách (.jpg/.jpeg/.png), CHỈ GIỮ mindmap .svg.
  2. GỌN (tuỳ chọn --trim): trong mỗi mục "### ..." của Nội dung chính, giữ tối
     đa N bullet đầu và bỏ bullet TRÙNG/GẦN TRÙNG. KHÔNG cắt cụt giữa câu
     (chỉ bỏ nguyên bullet dư) => không làm sai lệch ý từng câu.

Vì sao KHÔNG viết lại câu cho ngắn ở đây: rút gọn câu mà vẫn đủ ý cần AI đọc
hiểu nội dung — code chỉ cắt được máy móc. Muốn chất lượng như viết tay,
dùng: python3 main.py <pdf> --redo-from 3  (prompt v2 đã siết độ dài).

CHẠY:
    python3 condense_csv.py topics.csv --out topics.clean.csv           # chỉ bỏ ảnh jpg
    python3 condense_csv.py topics.csv --out topics.clean.csv --trim    # + gọn bullet
    python3 condense_csv.py topics.csv --out topics.clean.csv --trim --max-points 4
"""
import argparse
import csv
import difflib
import re
import sys
from pathlib import Path

KEEP_IMG_EXTS = {".svg"}          # chỉ giữ đuôi này ở section hình minh hoạ
NEAR_DUP_RATIO = 0.90


def strip_book_images(content: str) -> tuple:
    """Bỏ dòng ảnh không phải .svg. Trả về (content_mới, số_ảnh_bỏ)."""
    removed = 0
    out = []
    for ln in content.splitlines():
        m = re.match(r"!\[[^\]]*\]\(([^)]+)\)\s*$", ln.strip())
        if m:
            ext = "." + m.group(1).rsplit(".", 1)[-1].lower()
            if ext not in KEEP_IMG_EXTS:
                removed += 1
                continue
        out.append(ln)
    return "\n".join(out), removed


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[*_`]", "", s).lower().split())


def trim_sections(content: str, max_points: int) -> tuple:
    """Trong từng mục '### ', bỏ bullet gần-trùng và cap còn max_points.
    Chỉ tác động khối bullet '- ' ngay dưới mỗi '### '. Trả về (content, số_bỏ)."""
    lines = content.splitlines()
    out, removed = [], 0
    i = 0
    in_h3 = False
    kept_norms, kept_count = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("### "):
            in_h3, kept_norms, kept_count = True, [], 0
            out.append(ln)
        elif in_h3 and ln.startswith("- "):
            body = ln[2:]
            n = _norm(body)
            dup = any(difflib.SequenceMatcher(None, n, k).ratio() >= NEAR_DUP_RATIO
                      for k in kept_norms)
            if dup or (max_points > 0 and kept_count >= max_points):
                removed += 1
            else:
                out.append(ln)
                kept_norms.append(n)
                kept_count += 1
        else:
            # rời khỏi khối bullet của mục khi gặp dòng không phải bullet
            if not ln.startswith("- "):
                in_h3 = in_h3 and ln.strip() == ""  # dòng trống vẫn trong mục
            out.append(ln)
        i += 1
    return "\n".join(out), removed


def main():
    ap = argparse.ArgumentParser(description="Hậu xử lý topics.csv: bỏ ảnh sách, gọn bullet.")
    ap.add_argument("csv_in", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--trim", action="store_true",
                    help="bật gọn bullet (bỏ trùng + cap point/mục)")
    ap.add_argument("--max-points", type=int, default=4,
                    help="số bullet tối đa mỗi mục '###' khi --trim (0 = không cap)")
    args = ap.parse_args()

    if not args.csv_in.exists():
        sys.exit(f"Không tìm thấy: {args.csv_in}")

    rows = list(csv.DictReader(open(args.csv_in, encoding="utf-8-sig")))
    if not rows or "content" not in rows[0]:
        sys.exit("File không có cột 'content' — đúng là topics.csv chứ?")

    def wc(s): return len(s.split())
    total_before = sum(wc(r["content"]) for r in rows)
    img_removed = bullet_removed = 0

    for r in rows:
        c, ni = strip_book_images(r["content"])
        img_removed += ni
        if args.trim:
            c, nb = trim_sections(c, args.max_points)
            bullet_removed += nb
        # dọn dòng trống thừa sinh ra sau khi xoá
        c = re.sub(r"\n{3,}", "\n\n", c).strip() + "\n"
        r["content"] = c

    total_after = sum(wc(r["content"]) for r in rows)

    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows)

    print(f"✅ {args.out}")
    print(f"   {len(rows)} topic | bỏ {img_removed} ảnh trang sách (giữ .svg)")
    if args.trim:
        print(f"   gọn bullet: bỏ {bullet_removed} bullet trùng/dư (cap {args.max_points}/mục)")
    print(f"   Tổng từ: {total_before:,} -> {total_after:,} "
          f"({100 - round(total_after/total_before*100)}% ngắn hơn)")
    print("   ⚠️  Đây là rút gọn bằng CODE (bỏ ảnh + bỏ bullet dư), KHÔNG viết lại câu.")
    print("       Muốn câu ngắn mà đủ ý như viết tay: python3 main.py <pdf> --redo-from 3")


if __name__ == "__main__":
    main()
