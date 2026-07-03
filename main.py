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

from utils import load_json, log, save_json, warn


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
    ap.add_argument("--fused", action="store_true",
                    help="sinh content + câu hỏi trong 1 request/topic "
                         "(tiết kiệm ~50% request stage 3+5; xem README về trade-off)")
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
    f_export_state = work / "07_export_state.json"

    # ---- --redo-from: xoá cache từ stage N trở đi ----
    for n, f in caches.items():
        if n >= args.redo_from and f.exists():
            f.unlink()
            log(f"♻️  Xoá cache stage {n}: {f.name}")
    if args.redo_from <= 4 and images_dir.exists():
        shutil.rmtree(images_dir)
    if args.redo_from <= 5 and f_export_state.exists():
        f_export_state.unlink()
        warn("Reset trạng thái batch export (các thư mục batch-* cũ đã lỗi thời, "
             "batch mới sẽ đánh số lại từ 01).")

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

    # ---- Stage 3-6: TOPIC-MAJOR — xong trọn gói từng topic ----
    # (content -> images -> questions -> review cho topic N rồi mới sang N+1;
    #  hết quota giữa chừng vẫn có N topic HOÀN CHỈNH để export)
    import fitz
    from gemini import GeminiError
    from stage_content import generate_content_one
    from stage_images import generate_images_one
    from stage_questions import generate_questions_one

    content = load_json(caches[3], {}) or {}
    images = load_json(caches[4], {}) or {}
    questions = load_json(caches[5], {}) or {}
    review = load_json(caches[6], {}) or {}

    reviewer, with_pdf_flag = (None, False)
    if args.review:
        from stage_review import review_one
        reviewer, with_pdf_flag = _build_reviewer(args, client)

    doc = fitz.open(args.pdf)
    aborted = None
    total = len(structure)
    for idx, row in enumerate(structure, 1):
        slug = row["topic_slug"]
        steps_done = (slug in content
                      and (args.no_images or slug in images)
                      and slug in questions
                      and (not args.review or slug in review))
        if steps_done:
            log(f"── Topic {idx}/{total}: {slug} ✓ (hoàn chỉnh, bỏ qua) ──")
            continue
        log(f"── Topic {idx}/{total}: {slug} — {row['topic_title']} ──")
        try:
            if slug not in content:
                content[slug] = generate_content_one(doc, row, client, dpi=args.dpi)
                save_json(caches[3], content)
            if not args.no_images and slug not in images:
                images[slug] = generate_images_one(doc, row, content[slug],
                                                   client, images_dir)
                save_json(caches[4], images)
            if slug not in questions:
                qs, dropped = generate_questions_one(row, content[slug], client,
                                                     validate=not args.no_validate)
                questions[slug] = qs
                if dropped:
                    questions.setdefault("_dropped", {})[slug] = dropped
                save_json(caches[5], questions)
            if args.review and slug not in review:
                wp = (doc, reviewer) if with_pdf_flag else None
                review[slug] = review_one(row, content[slug],
                                          questions.get(slug, []), reviewer, wp)
                save_json(caches[6], review)
        except GeminiError as e:
            aborted = str(e)
            warn(f"Dừng tại topic {idx}/{total} ({slug}): {e}")
            warn(f"Đã hoàn chỉnh {idx-1} topic — vẫn export phần này. "
                 "Chạy lại CHÍNH LỆNH CŨ để tiếp tục từ topic dở dang.")
            break
    doc.close()
    questions.pop("_dropped", None)

    # ---- Stage 7: Export (full snapshot + delta batch) ----
    log("── Export package ──" + (" (PARTIAL — bị dừng vì lỗi quota)" if aborted else ""))
    from stage_export import export
    if args.review and args.review_fix and review:
        from stage_review import apply_fixes
        questions, removed = apply_fixes(questions, review)
        for r in removed:
            log(f"   ✂️  [{r['topic_slug']}] loại: {r['question'][:60]}... ({r['reason'][:60]})")

    # topic "hoàn chỉnh" = đủ mọi bước theo cờ đang bật
    completed = [r["topic_slug"] for r in structure
                 if r["topic_slug"] in content
                 and (args.no_images or r["topic_slug"] in images)
                 and r["topic_slug"] in questions
                 and (not args.review or r["topic_slug"] in review)]

    state = load_json(f_export_state, {"exported": {}, "next_batch": 1})
    new_slugs = [s for s in completed if s not in state["exported"]]

    if new_slugs:
        n = state["next_batch"]
        batch_dir = out_dir / f"batch-{n:02d}"
        export(structure, content, images, questions, batch_dir,
               pdf_name=args.pdf.name, model="mock" if args.dry_run else args.model,
               only_slugs=set(new_slugs), label=f" [BATCH {n:02d} — {len(new_slugs)} topic MỚI]")
        # copy ảnh của riêng lô này vào batch để test upload trọn gói
        b_img = batch_dir / "images"
        for s in new_slugs:
            for im in images.get(s, []):
                src_f = images_dir / im["file"]
                if src_f.exists():
                    b_img.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_f, b_img / im["file"])
        for s in new_slugs:
            state["exported"][s] = n
        state["next_batch"] = n + 1
        save_json(f_export_state, state)
    else:
        log("   (không có topic mới hoàn chỉnh -> không tạo batch mới)")

    # Quality checks thuần code (0 token) trên toàn bộ câu hỏi đã có
    from quality_checks import run_checks
    qc_warnings = run_checks({s: questions[s] for s in completed})
    if qc_warnings:
        log(f"\n🔍 Quality checks: {len(qc_warnings)} cảnh báo")
        for w in qc_warnings:
            warn(w)
    else:
        log("\n🔍 Quality checks: không phát hiện vấn đề.")

    # snapshot tích luỹ đầy đủ ở gốc (dùng cho lần import chính thức cuối cùng)
    export(structure, content, images, questions, out_dir,
           pdf_name=args.pdf.name, model="mock" if args.dry_run else args.model,
           only_slugs=set(completed), label=" [FULL — snapshot tích luỹ]",
           extra_warnings=qc_warnings)
    if args.review and review:
        from stage_review import write_report
        write_report(review, structure, out_dir / "review_report.md")
        log(f"   review_report.md : báo cáo thẩm định (đọc trước khi import!)")
    _report_usage([client, reviewer], work / "usage.json")
    log("\n✅ Hoàn tất. Import thử topics.csv + multichoice.csv, "
        "upload thư mục images/ theo manifest.json.")


def _report_usage(clients, usage_path):
    """In báo cáo token phiên này + cộng dồn vào work/usage.json."""
    run = {}
    seen = set()
    for c in clients:
        if c is None or id(c) in seen:
            continue
        seen.add(id(c))
        for tag, u in (getattr(c, "usage", None) or {}).items():
            r = run.setdefault(tag, {"calls": 0, "in": 0, "out": 0})
            r["calls"] += u["calls"]; r["in"] += u["in"]; r["out"] += u["out"]
    if not run:
        return
    total = load_json(usage_path, {}) or {}
    for tag, u in run.items():
        t = total.setdefault(tag, {"calls": 0, "in": 0, "out": 0})
        t["calls"] += u["calls"]; t["in"] += u["in"]; t["out"] += u["out"]
    save_json(usage_path, total)

    def _fmt(d):
        return f"{d['calls']:>5} | {d['in']:>10,} | {d['out']:>9,}"
    log("\n📊 Token usage (phiên này / cộng dồn — chi tiết: work/usage.json)")
    log(f"   {'tag':<12} | {'calls':>5} | {'tok_in':>10} | {'tok_out':>9}")
    for tag in sorted(run):
        log(f"   {tag:<12} | {_fmt(run[tag])}")
    s = {"calls": sum(u["calls"] for u in run.values()),
         "in": sum(u["in"] for u in run.values()),
         "out": sum(u["out"] for u in run.values())}
    st = {"calls": sum(u["calls"] for u in total.values()),
          "in": sum(u["in"] for u in total.values()),
          "out": sum(u["out"] for u in total.values())}
    log(f"   {'PHIÊN NÀY':<12} | {_fmt(s)}")
    log(f"   {'CỘNG DỒN':<12} | {_fmt(st)}")


def _build_reviewer(args, gemini_client):
    """Trả về (reviewer_client, with_pdf: bool — reviewer có đọc được PDF không)."""
    if args.dry_run:
        return gemini_client, False  # MockGemini tự xử lý tag "review"
    if args.reviewer == "gemini-pro":
        from gemini import Gemini
        rv = Gemini(gemini_client.api_key, model="gemini-2.5-pro",
                    interval=max(args.interval, 15.0))  # quota Pro free tier thấp hơn
        return rv, True
    from gemini import OpenAICompatClient
    env_key = OpenAICompatClient.PRESETS[args.reviewer][2]
    key = os.environ.get(env_key, "").strip()
    if not key:
        sys.exit(f"--reviewer {args.reviewer} cần biến môi trường {env_key}. "
                 f"Lấy free: groq -> https://console.groq.com, "
                 f"openrouter -> https://openrouter.ai/keys")
    return OpenAICompatClient(args.reviewer, key), False


if __name__ == "__main__":
    main()
