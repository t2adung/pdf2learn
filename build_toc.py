# -*- coding: utf-8 -*-
"""
build_toc.py — Dựng file 01_toc.json CHUẨN từ mục lục gõ tay (0 token AI, chính xác 100%).

Dùng khi PDF là sách scan / bookmark rác, và bạn muốn cấu trúc chương-bài chuẩn xác
thay vì để AI đoán. Bạn chỉ cần đọc trang MỤC LỤC của sách rồi gõ vào 1 file .txt đơn giản.

------------------------------------------------------------------
ĐỊNH DẠNG FILE MỤC LỤC (ví dụ toc.txt):
------------------------------------------------------------------
    # Dòng bắt đầu bằng "= " là MODULE (Chương / Phần).
    # Dòng "Tên bài | <số trang>" là TOPIC. Số trang là SỐ TRANG IN trên sách.
    # Dòng trống và dòng bắt đầu bằng "#" bị bỏ qua.

    = Mở đầu
    Bài 1. Giới thiệu về khoa học tự nhiên | 6
    Bài 2. An toàn trong phòng thực hành | 10
    = Chương I. Chất quanh ta
    Bài 5. Sự đa dạng của chất | 20
    Bài 6. Một số phương pháp tách chất ra khỏi hỗn hợp | 26

------------------------------------------------------------------
CÁCH TÍNH ĐỘ LỆCH (--offset):
------------------------------------------------------------------
    page_pdf = page_in + offset
    Mở PDF, tìm trang nơi BÀI ĐẦU TIÊN bắt đầu, xem trình duyệt báo đó là trang PDF số mấy,
    trừ đi số trang IN của bài đó. Ví dụ Bài 1 in ở trang 6 nhưng nằm ở trang PDF thứ 8
    => offset = 8 - 6 = 2.
    (Nếu bạn gõ thẳng SỐ TRANG PDF vào file thay vì số trang in, dùng --offset 0.)

------------------------------------------------------------------
CHẠY:
------------------------------------------------------------------
    python build_toc.py toc.txt --offset 2 --last-page 197 \
        --out runs/khtn-lop6/work/01_toc.json

    Sau đó chạy pipeline như thường; tool thấy 01_toc.json đã có -> dùng thẳng,
    bỏ qua cả bookmark lẫn AI cho khâu mục lục.
"""
import argparse
import json
import sys
from pathlib import Path


def parse_toc_text(text: str):
    """Đọc file .txt -> list module, mỗi module có list topic {title, page_in}."""
    modules = []
    cur = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("="):
            title = line[1:].strip()
            if not title:
                sys.exit(f"Dòng {lineno}: module rỗng.")
            cur = {"title": title, "topics": []}
            modules.append(cur)
            continue
        if "|" not in line:
            sys.exit(f"Dòng {lineno}: thiếu dấu '|' để tách số trang: {line!r}")
        title, page_str = line.rsplit("|", 1)
        title = title.strip()
        page_str = page_str.strip()
        if not title:
            sys.exit(f"Dòng {lineno}: tên bài rỗng.")
        if not page_str.lstrip("-").isdigit():
            sys.exit(f"Dòng {lineno}: số trang không hợp lệ: {page_str!r}")
        if cur is None:
            cur = {"title": "Nội dung chính", "topics": []}
            modules.append(cur)
        cur["topics"].append({"title": title, "page_in": int(page_str)})
    return [m for m in modules if m["topics"]]


def build(modules, offset: int, last_page: int):
    """Áp offset, tính page_end = trang bắt đầu bài kế - 1, kiểm tra hợp lệ."""
    # Gom tất cả topic theo thứ tự để tính page_end nối tiếp.
    flat = []
    for m in modules:
        for t in m["topics"]:
            t["page_start"] = t["page_in"] + offset
            flat.append(t)

    # Kiểm tra trang tăng dần
    for i in range(1, len(flat)):
        if flat[i]["page_start"] <= flat[i - 1]["page_start"]:
            sys.exit(f"Lỗi thứ tự trang: '{flat[i]['title']}' (tr.{flat[i]['page_start']}) "
                     f"không lớn hơn bài trước '{flat[i-1]['title']}' (tr.{flat[i-1]['page_start']}). "
                     "Kiểm tra lại số trang trong file mục lục.")

    for i, t in enumerate(flat):
        nxt = flat[i + 1]["page_start"] - 1 if i + 1 < len(flat) else last_page
        t["page_end"] = nxt
        if t["page_start"] < 1:
            sys.exit(f"'{t['title']}': page_start={t['page_start']} < 1. Offset sai?")
        if t["page_end"] < t["page_start"]:
            sys.exit(f"'{t['title']}': page_end={t['page_end']} < page_start={t['page_start']}. "
                     "Kiểm tra --last-page hoặc thứ tự bài.")
        del t["page_in"]  # dọn field tạm

    return {"modules": modules}


def main():
    ap = argparse.ArgumentParser(description="Dựng 01_toc.json chuẩn từ mục lục gõ tay.")
    ap.add_argument("toc_txt", type=Path, help="File .txt chứa mục lục (xem docstring).")
    ap.add_argument("--offset", type=int, required=True,
                    help="page_pdf = page_in + offset. Gõ thẳng trang PDF thì để 0.")
    ap.add_argument("--last-page", type=int, required=True,
                    help="Trang PDF nơi BÀI CUỐI kết thúc (page_end của bài cuối).")
    ap.add_argument("--out", type=Path, required=True, help="Nơi ghi 01_toc.json.")
    args = ap.parse_args()

    if not args.toc_txt.exists():
        sys.exit(f"Không tìm thấy: {args.toc_txt}")

    modules = parse_toc_text(args.toc_txt.read_text(encoding="utf-8"))
    if not modules:
        sys.exit("Không đọc được module/topic nào. Kiểm tra định dạng file.")

    toc = build(modules, args.offset, args.last_page)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(toc, ensure_ascii=False, indent=2), encoding="utf-8")

    n_topics = sum(len(m["topics"]) for m in toc["modules"])
    print(f"✅ Đã ghi {args.out}")
    print(f"   {len(toc['modules'])} module, {n_topics} bài.")
    print("   Xem trước:")
    for m in toc["modules"]:
        print(f"   ▪ {m['title']}")
        for t in m["topics"]:
            print(f"       - {t['title']}  (PDF tr.{t['page_start']}-{t['page_end']})")


if __name__ == "__main__":
    main()
