#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
toc_from_images.py — Đọc ẢNH CHỤP trang mục lục -> toc.txt (định dạng build_toc.py).

Vị trí trong quy trình:
    toc_images/ten-sach/hinh1.png, hinh2.png...
        └─(1 request AI OCR — rẻ: chỉ vài ảnh, không phải cả cuốn PDF)
            └─ toc.txt  ←— BẠN MỞ RA KIỂM TRA / SỬA TAY (guard 0 token)
                └─ build_toc.py (thuần code) -> 01_toc.json
                    └─ main.py sach.pdf --toc-file 01_toc.json

AI chỉ làm đúng việc OCR ra DỮ LIỆU (tên bài + số trang IN trên sách);
việc tính page_end, áp offset, kiểm tra thứ tự trang vẫn là code
deterministic trong build_toc.py — sai ở đâu sửa toc.txt ở đó, không tốn token.

CHẠY:
    # Bước 1 — OCR ảnh -> toc.txt rồi tự kiểm tra:
    python3 toc_from_images.py toc_images/ten-sach --out ten-sach.toc.txt

    # Bước 2 — dựng 01_toc.json (xem cách tính --offset trong build_toc.py):
    python3 build_toc.py ten-sach.toc.txt --offset 2 --last-page 197 \
        --out runs/ten-sach/work/01_toc.json

    # Hoặc GỘP 2 bước (khi đã tin kết quả OCR + biết offset):
    python3 toc_from_images.py toc_images/ten-sach --offset 2 --last-page 197 \
        --json-out runs/ten-sach/work/01_toc.json

    # Test không cần API key:
    python3 toc_from_images.py toc_images/ten-sach --out /tmp/t.txt --dry-run
"""
import argparse
import os
import re
import sys
from pathlib import Path

import fitz

from build_toc import build, parse_toc_text
from utils import log, save_json, warn

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MAX_WIDTH = 1600   # ảnh chụp điện thoại 4000px -> shrink để giảm token, vẫn thừa nét để OCR

TOC_OCR_SCHEMA = {
    "type": "object",
    "properties": {
        "modules": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "topics": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "page": {"type": "integer"},
                    },
                    "required": ["title", "page"],
                }},
            },
            "required": ["title", "topics"],
        }},
    },
    "required": ["modules"],
}

TOC_OCR_PROMPT = """Các ảnh đính kèm là TRANG MỤC LỤC của một cuốn sách giáo dục,
theo đúng thứ tự. Hãy đọc và trả về cấu trúc mục lục:

- MODULE = chương / phần lớn (vd "Chương I. Chất quanh ta"). Nếu sách không chia
  chương, tạo 1 module duy nhất tên "Nội dung chính".
- TOPIC = bài học / mục con, kèm "page" = SỐ TRANG IN trên mục lục (số nguyên).

Yêu cầu nghiêm ngặt:
- CHÉP NGUYÊN VĂN tiêu đề (giữ số bài, dấu chấm, dấu tiếng Việt) — không sửa
  chính tả, không dịch, không tự bịa mục không nhìn thấy trong ảnh.
- Đúng thứ tự xuất hiện. Số trang phải là số đọc được trong ảnh.
- BỎ QUA: lời nói đầu, hướng dẫn sử dụng sách, mục lục, phụ lục, bảng tra cứu,
  đáp án, tài liệu tham khảo."""


def _natural_key(p: Path):
    """hinh1, hinh2, hinh10 đúng thứ tự (sort chuỗi thường ra 1, 10, 2)."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", p.name)]


def _load_images(folder: Path) -> list:
    files = sorted((f for f in folder.iterdir()
                    if f.suffix.lower() in IMG_EXTS), key=_natural_key)
    if not files:
        sys.exit(f"Không thấy ảnh nào trong {folder} (hỗ trợ: {', '.join(sorted(IMG_EXTS))})")
    out = []
    for f in files:
        pix = fitz.Pixmap(str(f))
        if pix.alpha:                     # JPEG không nhận alpha
            pix = fitz.Pixmap(pix, 0)
        n_shrink = 0
        while pix.width > MAX_WIDTH * (2 ** n_shrink):
            n_shrink += 1
        if n_shrink:
            pix.shrink(n_shrink)          # halve n lần — giảm token, đủ nét OCR
        out.append({"name": f.name, "data": pix.tobytes("jpeg", jpg_quality=85)})
    return out


def _to_toc_txt(result: dict, source_names: list) -> str:
    lines = [f"# Sinh tự động từ ảnh: {', '.join(source_names)}",
             "# KIỂM TRA KỸ tên bài + số trang so với ảnh gốc trước khi chạy build_toc.py!",
             "# Định dạng: '= Tên module' / 'Tên bài | số trang IN'. Dòng # bị bỏ qua.",
             ""]
    for m in result.get("modules", []):
        lines.append(f"= {m['title'].strip()}")
        for t in m.get("topics", []):
            lines.append(f"{t['title'].strip()} | {int(t['page'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="OCR ảnh chụp trang mục lục -> toc.txt (hoặc thẳng 01_toc.json).")
    ap.add_argument("images_dir", type=Path,
                    help="thư mục chứa ảnh mục lục, vd toc_images/ten-sach")
    ap.add_argument("--out", type=Path, default=None,
                    help="nơi ghi toc.txt (mặc định: <images_dir>.toc.txt)")
    ap.add_argument("--offset", type=int, default=None,
                    help="(tuỳ chọn) page_pdf = page_in + offset — kèm --last-page "
                         "để ghi thẳng 01_toc.json")
    ap.add_argument("--last-page", type=int, default=None,
                    help="(tuỳ chọn) trang PDF nơi bài cuối kết thúc")
    ap.add_argument("--json-out", type=Path, default=None,
                    help="nơi ghi 01_toc.json (cần --offset và --last-page)")
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--interval", type=float, default=6.0)
    ap.add_argument("--dry-run", action="store_true", help="MockGemini, không cần API key")
    args = ap.parse_args()

    if not args.images_dir.is_dir():
        sys.exit(f"Không tìm thấy thư mục: {args.images_dir}")
    if args.json_out and (args.offset is None or args.last_page is None):
        sys.exit("--json-out cần cả --offset và --last-page (xem docstring build_toc.py).")

    # ---- client ----
    if args.dry_run:
        from gemini import MockGemini
        client = MockGemini()
        log("🧪 DRY-RUN: dùng MockGemini.")
    else:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            sys.exit("Thiếu GEMINI_API_KEY (hoặc chạy --dry-run để test).")
        from gemini import Gemini
        client = Gemini(api_key, model=args.model, interval=args.interval)

    # ---- OCR: 1 request duy nhất cho toàn bộ ảnh ----
    imgs = _load_images(args.images_dir)
    log(f"📷 {len(imgs)} ảnh mục lục: {', '.join(i['name'] for i in imgs)}")
    parts = [{"text": TOC_OCR_PROMPT}]
    for im in imgs:
        parts.append(client.image_part(im["data"], "image/jpeg"))
    result = client.generate_json(parts, TOC_OCR_SCHEMA, tag="toc_ocr")

    n_topics = sum(len(m.get("topics", [])) for m in result.get("modules", []))
    if n_topics == 0:
        sys.exit("AI không đọc được mục nào — ảnh có đúng là trang mục lục, đủ nét không?")

    # ---- toc.txt: điểm dừng để người duyệt ----
    out_txt = args.out or args.images_dir.with_suffix(".toc.txt")
    txt = _to_toc_txt(result, [i["name"] for i in imgs])
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text(txt, encoding="utf-8")
    log(f"✅ Đã ghi {out_txt} — {len(result['modules'])} module, {n_topics} bài.")
    for m in result["modules"]:
        log(f"   ▪ {m['title']}")
        for t in m["topics"]:
            log(f"       - {t['title']}  (tr.in {t['page']})")

    # ---- (tuỳ chọn) dựng luôn 01_toc.json bằng code của build_toc.py ----
    if args.json_out:
        modules = parse_toc_text(txt)               # tái dùng parser + validate
        toc = build(modules, args.offset, args.last_page)
        save_json(args.json_out, toc)
        log(f"✅ Đã ghi {args.json_out} (offset={args.offset}, last_page={args.last_page}).")
        log(f"   Chạy tiếp: python3 main.py sach.pdf --toc-file {args.json_out}")
    else:
        warn("MỞ FILE toc.txt ĐỐI CHIẾU VỚI ẢNH trước khi chạy bước sau — "
             "OCR số trang sai 1 trang là lệch page range cả bài.")
        log(f"   Bước sau: python3 build_toc.py {out_txt} --offset <N> --last-page <M> "
            f"--out runs/<ten-sach>/work/01_toc.json")


if __name__ == "__main__":
    main()
