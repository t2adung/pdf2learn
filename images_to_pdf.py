#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""images_to_pdf.py — Ghép ẢNH TRANG SÁCH thành file PDF cho từng cuốn.

Nguồn dữ liệu là ảnh (mỗi trang sách 1 file .png/.jpg) thay vì PDF. Script quét
cây thư mục ảnh, gom ảnh của TỪNG cuốn (mỗi thư mục con là 1 cuốn) rồi ghép thành
1 file PDF đặt vào thư mục `pdf/` (giữ nguyên cấu trúc lớp) — để chạy tiếp bằng
pipeline sẵn có (batch_toc.py + main.py) y như với PDF thật.

Cấu trúc đầu vào (như bộ tải ảnh SGK sinh ra):

    images/
      lop-4/
        sgk-khoa-hoc-4/
          _urls.json          (bỏ qua)
          page-001.png
          page-003.png        (thiếu page-002 -> ghép liền, bỏ qua chỗ thiếu)
          ...
        sgk-toan-4-tap-mot/
          page-001.png ...
      lop-5/
        ...

Sau khi chạy `python images_to_pdf.py images --out pdf`:

    pdf/
      lop-4/
        sgk-khoa-hoc-4.pdf
        sgk-toan-4-tap-mot.pdf
      lop-5/
        ...

Rồi chạy như với PDF thật:

    python batch_toc.py pdf --out tocs --also-txt          # sinh mục lục (tocs/)
    python main.py pdf/lop-4/sgk-khoa-hoc-4.pdf --level "Lớp 4" \
        --toc-file tocs/lop-4/sgk-khoa-hoc-4.toc.json --yes  # topics.csv + multichoice.csv

Thứ tự trang: sắp ẢNH theo SỐ trong tên file (page-001, page-003, ...) rồi ghép
LIỀN TIẾP thành trang 1..K (chỗ thiếu bị bỏ qua, không chèn trang trắng).

Mặc định resume: cuốn đã có PDF sẽ bỏ qua (--overwrite để ép ghép lại).
"""
import argparse
import re
import sys
from pathlib import Path

import fitz

from utils import log, warn

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _page_key(p: Path):
    """Khoá sắp xếp tự nhiên: theo SỐ đầu tiên trong tên file, rồi tới tên."""
    m = re.search(r"\d+", p.stem)
    return (int(m.group()) if m else 10**9, p.name.lower())


def find_books(images_root: Path):
    """Trả list (thư_mục_cuốn, [ảnh đã sắp xếp]). 'Cuốn' = thư mục chứa TRỰC TIẾP
    ít nhất 1 file ảnh."""
    books = {}
    for f in images_root.rglob("*"):
        if f.is_file() and f.suffix.lower() in IMG_EXTS:
            books.setdefault(f.parent, []).append(f)
    out = []
    for d in sorted(books):
        imgs = sorted(books[d], key=_page_key)
        out.append((d, imgs))
    return out


def build_pdf_from_images(image_paths, out_pdf: Path, max_width: int = 1600,
                          quality: int = 80, gray: bool = False) -> int:
    """Ghép các ảnh thành 1 PDF (mỗi ảnh 1 trang). Trả về số trang đã ghép.

    max_width>0: thu nhỏ ảnh rộng hơn ngưỡng đó (px) rồi nén JPEG -> PDF NHẸ,
    upload nhanh, tránh lỗi Gemini HTTP 400 với scan độ phân giải cao. max_width=0
    giữ nguyên bản gốc. gray=True: chuyển xám (nhẹ thêm ~1 nửa, đủ để OCR chữ)."""
    doc = fitz.open()
    cs = fitz.csGRAY if gray else fitz.csRGB
    n = 0
    for img in image_paths:
        try:
            if max_width and max_width > 0:
                with fitz.open(img) as im:            # ảnh -> tài liệu 1 trang
                    page = im[0]
                    w = page.rect.width or 1
                    scale = min(1.0, max_width / w)
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale),
                                          colorspace=cs)
                jpg = pix.tobytes("jpeg", jpg_quality=quality)
                pg = doc.new_page(width=pix.width, height=pix.height)
                pg.insert_image(pg.rect, stream=jpg)
            else:
                with fitz.open(img) as im:
                    pdf_bytes = im.convert_to_pdf()   # giữ nguyên bản gốc
                with fitz.open("pdf", pdf_bytes) as one:
                    doc.insert_pdf(one)
            n += 1
        except Exception as e:
            warn(f"    bỏ qua ảnh lỗi {img.name}: {e}")
    if n:
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_pdf, garbage=3, deflate=True)
    doc.close()
    return n


def main():
    ap = argparse.ArgumentParser(
        description="Ghép ảnh trang sách -> 1 PDF/cuốn, đặt vào thư mục pdf/.")
    ap.add_argument("images_root", type=Path,
                    help="thư mục gốc chứa ảnh (đệ quy; mỗi thư mục con 1 cuốn)")
    ap.add_argument("--out", type=Path, default=Path("pdf"),
                    help="thư mục gốc ghi PDF (mặc định: pdf/)")
    ap.add_argument("--overwrite", action="store_true",
                    help="ép ghép lại kể cả khi file PDF đã tồn tại (mặc định: resume)")
    ap.add_argument("--limit", type=int, default=0, metavar="N",
                    help="chỉ xử lý N cuốn đầu tiên rồi dừng (test nhanh). 0 = làm hết.")
    ap.add_argument("--max-width", type=int, default=1600,
                    help="thu nhỏ ảnh rộng hơn N px trước khi ghép (mặc định 1600 — "
                         "đủ nét để OCR, PDF nhẹ). 0 = giữ nguyên bản gốc.")
    ap.add_argument("--quality", type=int, default=80,
                    help="chất lượng nén JPEG khi thu nhỏ (mặc định 80)")
    ap.add_argument("--gray", action="store_true",
                    help="chuyển ảnh sang xám (nhẹ hơn ~1 nửa; đủ cho OCR chữ, "
                         "nhưng mất màu — cân nhắc với sách có hình màu)")
    args = ap.parse_args()

    if not args.images_root.exists() or not args.images_root.is_dir():
        sys.exit(f"Không phải thư mục: {args.images_root}")

    books = find_books(args.images_root)
    if not books:
        sys.exit(f"Không tìm thấy ảnh nào (png/jpg/...) trong: {args.images_root}")

    total = len(books)
    if args.limit and 0 < args.limit < total:
        books = books[:args.limit]
        log(f"🔎 Tìm thấy {total} cuốn — --limit {args.limit}: chỉ ghép {len(books)} "
            f"cuốn đầu -> {args.out}/.")
    else:
        log(f"🔎 Tìm thấy {total} cuốn (thư mục ảnh) trong {args.images_root} "
            f"-> ghép PDF vào {args.out}/ (giữ nguyên cấu trúc).")

    counts = {"ok": 0, "skip": 0, "empty": 0}
    for i, (book_dir, imgs) in enumerate(books, 1):
        rel = book_dir.relative_to(args.images_root)
        out_pdf = args.out / rel.parent / (book_dir.name + ".pdf")
        log(f"[{i}/{len(books)}] {rel}  ({len(imgs)} ảnh)")
        if out_pdf.exists() and not args.overwrite:
            log(f"  ↷ bỏ qua (đã có): {out_pdf}")
            counts["skip"] += 1
            continue
        n = build_pdf_from_images(imgs, out_pdf, max_width=args.max_width,
                                  quality=args.quality, gray=args.gray)
        if n == 0:
            warn(f"  không ghép được trang nào -> bỏ: {rel}")
            counts["empty"] += 1
            continue
        size_mb = out_pdf.stat().st_size / 1e6
        log(f"  ✅ {out_pdf}  ({n} trang, {size_mb:.1f}MB)")
        counts["ok"] += 1

    log("\n────────── TỔNG KẾT ──────────")
    log(f"  ✅ đã ghép : {counts['ok']}")
    log(f"  ↷ bỏ qua  : {counts['skip']} (đã có — dùng --overwrite để ép ghép lại)")
    log(f"  ✖ rỗng    : {counts['empty']}")
    log("\nBước tiếp theo (pipeline sẵn có):")
    log(f"  python batch_toc.py {args.out} --out tocs --also-txt")
    log(f"  python main.py {args.out}/<lop>/<sach>.pdf --level \"Lớp N\" "
        f"--toc-file tocs/<lop>/<sach>.toc.json --yes")
    sys.exit(1 if counts["empty"] else 0)


if __name__ == "__main__":
    main()
