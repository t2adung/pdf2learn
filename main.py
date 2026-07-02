#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf2learn — Prototype: PDF -> topics.csv + multichoice.csv + images/ + manifest.json

Pipeline 6 stage, kết quả trung gian lưu ở runs/<tên-pdf>/work/:
  1. TOC        : bookmark PDF (code) hoặc AI suy ra mục lục
  2. Structure  : chuẩn hoá + sinh slug/order (code, deterministic)
  3. Content    : mỗi topic -> Markdown bài học + key_points (AI, chunk theo trang)
  4. Images     : trích ảnh PDF + AI lọc; fallback sinh SVG diagram
  5. Questions  : MCQ theo key_points (coverage) + pass validation đáp án
  6. Export     : CSV UTF-8 BOM đúng template + manifest.json

Resume: mặc định LUÔN resume — stage/topic đã xong sẽ bỏ qua (an toàn khi
đứt giữa chừng vì rate limit). Muốn sinh lại từ stage N: --redo-from N.

Dùng:
  export GEMINI_API_KEY=...            # lấy free tại https://aistudio.google.com
  python main.py sach.pdf --level "Lớp 6"

  python main.py sach.pdf --dry-run          # test KHÔNG cần API key (mock AI)
  python main.py sach.pdf --redo-from 5      # xoá cache stage 5+, sinh lại câu hỏi
  python main.py sach.pdf --no-images --no-validate   # nhanh, ít request
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

from utils import load_json, log, save_json


def main():
    ap = argparse.ArgumentParser(description="PDF -> learning package (topics + MCQ)")
    ap.add_argument("pdf", type=Path, help="đường dẫn file PDF")
    ap.add_argument("--level", default="Lớp 6", help='giá trị cột level, vd "Lớp 6"')
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--interval", type=float, default=6.0,
                    help="giây giữa 2 request (free tier ~10 RPM -> 6s)")
    ap.add_argument("--dpi", type=int, default=0,
                    help="nén trang PDF scan về N dpi grayscale trước khi gửi "
                         "(giảm token mạnh; khuyến nghị 110 cho sách scan; 0 = tắt)")
    ap.add_argument("--redo-from", type=int, default=99, choices=range(1, 8),
                    metavar="N", help="xoá cache từ stage N trở đi rồi sinh lại")
    ap.add_argument("--force-ai-toc", action="store_true",
                    help="bỏ qua bookmark PDF, luôn dùng AI trích mục lục")
    ap.add_argument("--no-images", action="store_true", help="bỏ qua stage 4")
    ap.add_argument("--no-validate", action="store_true",
                    help="bỏ qua pass kiểm chứng đáp án ở stage 5")
    ap.add_argument("--review", action="store_true",
                    help="v2: stage 6 — model thứ hai review lại content + câu hỏi")
    ap.add_argument("--reviewer", default="groq",
                    choices=["groq", "openrouter", "gemini-pro"],
                    help="model reviewer (groq=Llama 70B, openrouter=DeepSeek R1 free, "
                         "gemini-pro=đọc được PDF gốc)")
    ap.add_argument("--review-fix", action="store_true",
                    help="tự loại câu hỏi bị review đánh severity=high (mặc định chỉ báo cáo)")
    ap.add_argument("--dry-run", action="store_true",
                    help="dùng MockGemini, không cần API key (test pipeline/format)")
    args = ap.parse_args()

    if not args.pdf.exists():
        sys.exit(f"Không tìm thấy file: {args.pdf}")

    # ---- client ----
    if args.dry_run:
        from gemini import MockGemini
        client = MockGemini()
        log("🧪 DRY-RUN: dùng MockGemini (không gọi API thật).")
    else:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            sys.exit("Thiếu GEMINI_API_KEY. Lấy key miễn phí tại https://aistudio.google.com "
                     "rồi: export GEMINI_API_KEY=...  (hoặc chạy --dry-run để test)")
        from gemini import Gemini
        client = Gemini(api_key, model=args.model, interval=args.interval)

    run_dir = Path("runs") / args.pdf.stem
    work = run_dir / "work"
    out_dir = run_dir / "output"
    images_dir = out_dir / "images"
    work.mkdir(parents=True, exist_ok=True)

    caches = {1: work / "01_toc.json", 2: work / "02_structure.json",
              3: work / "03_content.json", 4: work / "04_images.json",
              5: work / "05_questions.json", 6: work / "06_review.json"}

    # ---- --redo-from: xoá cache từ stage N trở đi ----
    for n, f in caches.items():
        if n >= args.redo_from and f.exists():
            f.unlink()
            log(f"♻️  Xoá cache stage {n}: {f.name}")
    if args.redo_from <= 4 and images_dir.exists():
        shutil.rmtree(images_dir)

    # ---- Stage 1: TOC ----
    toc = load_json(caches[1])
    if toc is None:
        log("── Stage 1/7: Trích mục lục ──")
        from stage_toc import extract_toc
        toc = extract_toc(args.pdf, client, force_ai=args.force_ai_toc)
        save_json(caches[1], toc)
    else:
        log("── Stage 1/7: dùng lại 01_toc.json ──")

    # ---- Stage 2: Structure + slug ----
    structure = load_json(caches[2])
    if structure is None:
        log("── Stage 2/7: Sinh cấu trúc + slug ──")
        from stage_toc import build_structure
        structure = build_structure(toc, args.level)
        save_json(caches[2], structure)
        for r in structure:
            log(f"   {r['order']:>3}. [{r['module_slug']}] {r['topic_slug']} "
                f"(tr.{r['page_start']}-{r['page_end']})")
    else:
        log("── Stage 2/7: dùng lại 02_structure.json ──")

    if not structure:
        sys.exit("Không xác định được topic nào — kiểm tra lại PDF/mục lục.")

    # ---- Stage 3: Content (incremental resume theo topic) ----
    log("── Stage 3/7: Sinh nội dung bài học ──")
    from stage_content import generate_content
    content = load_json(caches[3], {}) or {}
    for content in generate_content(args.pdf, structure, client, content,
                                    dpi=args.dpi):
        save_json(caches[3], content)

    # ---- Stage 4: Images ----
    if args.no_images:
        log("── Stage 4/7: bỏ qua (--no-images) ──")
        images = load_json(caches[4], {}) or {}
    else:
        log("── Stage 4/7: Hình minh hoạ ──")
        from stage_images import generate_images
        images = load_json(caches[4], {}) or {}
        for images in generate_images(args.pdf, structure, content, client,
                                      images_dir, images):
            save_json(caches[4], images)

    # ---- Stage 5: Questions ----
    log("── Stage 5/7: Sinh câu hỏi trắc nghiệm ──")
    from stage_questions import generate_questions
    questions = load_json(caches[5], {}) or {}
    for questions in generate_questions(structure, content, client, questions,
                                        validate=not args.no_validate):
        save_json(caches[5], questions)
    questions.pop("_dropped", None)

    # ---- Stage 6 (v2): Cross-model review ----
    review = {}
    if args.review:
        log(f"── Stage 6/7: Cross-model review (reviewer: {args.reviewer}) ──")
        from stage_review import run_review
        reviewer, with_pdf = _build_reviewer(args, client)
        review = load_json(caches[6], {}) or {}
        for review in run_review(structure, content, questions, reviewer,
                                 review, with_pdf=with_pdf):
            save_json(caches[6], review)
    else:
        log("── Stage 6/7: bỏ qua review (bật bằng --review) ──")

    # ---- Stage 7: Export ----
    log("── Stage 7/7: Export package ──")
    from stage_export import export
    if args.review and args.review_fix and review:
        from stage_review import apply_fixes
        questions, removed = apply_fixes(questions, review)
        for r in removed:
            log(f"   ✂️  [{r['topic_slug']}] loại: {r['question'][:60]}... ({r['reason'][:60]})")
    export(structure, content, images, questions, out_dir,
           pdf_name=args.pdf.name, model="mock" if args.dry_run else args.model)
    if args.review and review:
        from stage_review import write_report
        write_report(review, structure, out_dir / "review_report.md")
        log(f"   review_report.md : báo cáo thẩm định (đọc trước khi import!)")
    log("\n✅ Hoàn tất. Import thử topics.csv + multichoice.csv, "
        "upload thư mục images/ theo manifest.json.")


def _build_reviewer(args, gemini_client):
    """Trả về (reviewer_client, with_pdf). with_pdf != None nếu reviewer đọc được PDF."""
    if args.dry_run:
        return gemini_client, None  # MockGemini tự xử lý tag "review"
    if args.reviewer == "gemini-pro":
        from gemini import Gemini
        rv = Gemini(gemini_client.api_key, model="gemini-2.5-pro",
                    interval=max(args.interval, 15.0))  # quota Pro free tier thấp hơn
        return rv, (args.pdf, rv)
    from gemini import OpenAICompatClient
    env_key = OpenAICompatClient.PRESETS[args.reviewer][2]
    key = os.environ.get(env_key, "").strip()
    if not key:
        sys.exit(f"--reviewer {args.reviewer} cần biến môi trường {env_key}. "
                 f"Lấy free: groq -> https://console.groq.com, "
                 f"openrouter -> https://openrouter.ai/keys")
    return OpenAICompatClient(args.reviewer, key), None


if __name__ == "__main__":
    main()
