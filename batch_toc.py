#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""batch_toc.py — Sinh HÀNG LOẠT mục lục (TOC) cho cả một CÂY THƯ MỤC PDF.

Ý tưởng: bạn có 1 thư mục gốc, mỗi lớp là 1 thư mục con, trong đó là các file
sách PDF. Chạy 1 lệnh, trỏ vào thư mục gốc, tool sẽ quét đệ quy mọi file .pdf và
sinh ra 1 CÂY THƯ MỤC TƯƠNG ỨNG chứa các file TOC (mặc định: <tên-sách>.toc.json).

Ví dụ cấu trúc đầu vào:

    pdf/
      lop6/
        khtn.pdf
        lich-su.pdf
      lop7/
        toan.pdf

Sau khi chạy `python batch_toc.py pdf --out tocs`:

    tocs/
      lop6/
        khtn.toc.json
        lich-su.toc.json
      lop7/
        toan.toc.json

Mỗi file *.toc.json có ĐÚNG shape của 01_toc.json mà pipeline dùng, nên có thể
đưa thẳng vào main.py qua --toc-file (0 token cho khâu mục lục):

    python main.py pdf/lop6/khtn.pdf --level "Lớp 6" \
        --toc-file tocs/lop6/khtn.toc.json

Nguồn mục lục theo đúng quy tắc của stage_toc.extract_toc:
  • PDF có sẵn bookmark  -> dùng code, 0 token AI, chính xác 100%.
  • PDF không có bookmark -> nhờ AI (Gemini/Claude) suy ra mục lục kèm page range.

CHẠY:
  python batch_toc.py pdf                     # gemini, cần GEMINI_API_KEY
  python batch_toc.py pdf --dry-run           # test KHÔNG cần API key (mock AI)
  python batch_toc.py pdf --backend claude    # dùng subscription Claude
  python batch_toc.py pdf --out tocs --also-txt --overwrite

Mặc định LUÔN resume: file TOC đã có sẽ được BỎ QUA (an toàn khi đứt giữa chừng
vì rate limit). Muốn ép sinh lại: --overwrite. Một file lỗi KHÔNG làm dừng cả lô;
cuối cùng in bảng tổng kết (đã sinh / bỏ qua / lỗi).
"""
import argparse
import os
import sys
from pathlib import Path

from utils import log, save_json, warn


def build_client(args):
    """Chọn nguồn AI y hệt main.py: mock (dry-run) | claude | gemini.

    Chỉ khởi tạo khi THỰC SỰ cần (có ít nhất 1 PDF thiếu bookmark). Với PDF có
    bookmark, extract_toc không đụng tới client nên có thể chạy 0 token."""
    if args.dry_run:
        from gemini import MockGemini
        log("🧪 DRY-RUN: dùng MockGemini (không gọi API thật).")
        return MockGemini()
    if args.backend == "claude":
        from claude_cli import CLAUDE_DEFAULT_MODEL, ClaudeCLI
        model = CLAUDE_DEFAULT_MODEL if args.model.startswith("gemini") else args.model
        log(f"🟣 Backend CLAUDE (subscription qua `claude -p`, model={model}). "
            "Không cần API key.")
        return ClaudeCLI(model=model, interval=args.interval)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        sys.exit("Thiếu GEMINI_API_KEY. Lấy key miễn phí tại https://aistudio.google.com "
                 "rồi: export GEMINI_API_KEY=...  (hoặc chạy --dry-run để test, "
                 "hoặc --backend claude để dùng subscription Claude)")
    from gemini import Gemini
    return Gemini(api_key, model=args.model, interval=args.interval)


def toc_to_txt(toc: dict) -> str:
    """Xuất TOC ra định dạng .txt của build_toc.py để người dùng dễ soát/sửa tay.

    LƯU Ý: số trang ghi ra là SỐ TRANG PDF (đã tính từ 1), nên nếu sửa file này
    rồi dựng lại bằng build_toc.py thì dùng --offset 0."""
    lines = ["# Sinh tự động bởi batch_toc.py — số trang là SỐ TRANG PDF (offset 0).",
             "# Soát lại tên bài + trang, rồi: build_toc.py <file> --offset 0 --last-page <M> --out ...",
             ""]
    for m in toc.get("modules", []):
        lines.append(f"= {m['title']}")
        for t in m.get("topics", []):
            lines.append(f"{t['title']} | {t['page_start']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def process_one(pdf_path: Path, out_json: Path, args, get_client) -> str:
    """Sinh TOC cho 1 PDF. Trả về 'ok' | 'skip' | 'error'. get_client() lazy-init client."""
    if out_json.exists() and not args.overwrite:
        log(f"  ↷ bỏ qua (đã có): {out_json}")
        return "skip"

    from stage_toc import extract_toc
    # PDF có bookmark -> extract_toc không dùng client; chỉ khởi tạo AI khi cần.
    toc = extract_toc(pdf_path, get_client(), force_ai=args.force_ai_toc)

    n_mod = len(toc.get("modules", []))
    n_top = sum(len(m.get("topics", [])) for m in toc.get("modules", []))
    if n_top == 0:
        warn(f"  {pdf_path.name}: không trích được topic nào (bỏ ghi file).")
        return "error"

    save_json(out_json, toc)
    log(f"  ✅ {out_json}  ({n_mod} module, {n_top} bài)")
    if args.also_txt:
        out_txt = out_json.with_suffix("").with_suffix(".toc.txt")
        out_txt.write_text(toc_to_txt(toc), encoding="utf-8")
        log(f"     + {out_txt}")
    return "ok"


def main():
    ap = argparse.ArgumentParser(
        description="Quét cây thư mục PDF -> sinh cây thư mục TOC tương ứng.")
    ap.add_argument("pdf_root", type=Path,
                    help="thư mục gốc chứa PDF (đệ quy; mỗi lớp 1 thư mục con)")
    ap.add_argument("--out", type=Path, default=Path("tocs"),
                    help="thư mục gốc ghi các file TOC (mặc định: tocs/)")
    ap.add_argument("--suffix", default=".toc.json",
                    help="đuôi file TOC json (mặc định: .toc.json)")
    ap.add_argument("--also-txt", action="store_true",
                    help="ghi thêm bản .toc.txt để soát/sửa tay (build_toc.py, offset 0)")
    ap.add_argument("--overwrite", action="store_true",
                    help="ép sinh lại kể cả khi file TOC đã tồn tại (mặc định: resume)")
    # Các cờ chọn nguồn AI — giống main.py.
    ap.add_argument("--backend", default="gemini", choices=["gemini", "claude"],
                    help="nguồn AI khi PDF thiếu bookmark (mặc định gemini)")
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--interval", type=float, default=6.0,
                    help="giây giữa 2 request (free tier ~10 RPM -> 6s)")
    ap.add_argument("--force-ai-toc", action="store_true",
                    help="bỏ qua bookmark PDF, luôn dùng AI trích mục lục")
    ap.add_argument("--dry-run", action="store_true",
                    help="dùng MockGemini, không cần API key (test pipeline/format)")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if not args.pdf_root.exists() or not args.pdf_root.is_dir():
        sys.exit(f"Không phải thư mục: {args.pdf_root}")

    pdfs = sorted(p for p in args.pdf_root.rglob("*.pdf") if p.is_file())
    if not pdfs:
        sys.exit(f"Không tìm thấy file .pdf nào trong: {args.pdf_root}")

    log(f"🔎 Tìm thấy {len(pdfs)} file PDF trong {args.pdf_root} "
        f"-> ghi TOC vào {args.out}/ (giữ nguyên cấu trúc thư mục).")

    # Lazy client: chỉ khởi tạo khi có PDF đầu tiên cần AI (tiết kiệm khi toàn bookmark).
    _client_box = {}

    def get_client():
        if "c" not in _client_box:
            _client_box["c"] = build_client(args)
        return _client_box["c"]

    counts = {"ok": 0, "skip": 0, "error": 0}
    errors = []
    for i, pdf_path in enumerate(pdfs, 1):
        rel = pdf_path.relative_to(args.pdf_root)
        # Giữ nguyên cây thư mục; đuôi có thể nhiều chấm (.toc.json) nên ghép thủ công.
        out_json = args.out / rel.parent / (pdf_path.stem + args.suffix)
        log(f"[{i}/{len(pdfs)}] {rel}")
        try:
            counts[process_one(pdf_path, out_json, args, get_client)] += 1
        except KeyboardInterrupt:
            raise
        except Exception as e:  # 1 file hỏng không làm dừng cả lô
            counts["error"] += 1
            errors.append((str(rel), str(e)))
            warn(f"  Lỗi ở {rel}: {e}")

    log("\n────────── TỔNG KẾT ──────────")
    log(f"  ✅ đã sinh : {counts['ok']}")
    log(f"  ↷ bỏ qua  : {counts['skip']} (đã có sẵn — dùng --overwrite để ép sinh lại)")
    log(f"  ✖ lỗi     : {counts['error']}")
    if errors:
        log("  Chi tiết lỗi:")
        for rel, msg in errors:
            log(f"    - {rel}: {msg}")

    if "c" in _client_box and getattr(_client_box["c"], "usage", None):
        from main import _report_usage
        _report_usage([_client_box["c"]], args.out / "usage.json")

    # Có lỗi -> mã thoát 1 để CI/runner biết; mọi thứ ổn -> 0.
    sys.exit(1 if counts["error"] else 0)


if __name__ == "__main__":
    main()
