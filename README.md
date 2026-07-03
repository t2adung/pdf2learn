# pdf2learn — PDF → Learning Package (topics.csv + multichoice.csv)

Pipeline AI: đọc PDF giáo trình (kể cả PDF **scan**) → chia module/topic → soạn bài
học Markdown kèm hình minh hoạ → sinh câu hỏi trắc nghiệm phủ hết kiến thức →
export đúng template import (`topics.csv`, `multichoice.csv`) + `images/` +
`manifest.json`, kèm cross-model review, quality checks và báo cáo token.

AI chính: **Google Gemini API free tier** (đọc PDF native, structured output).
Reviewer (tuỳ chọn): Groq / OpenRouter / Gemini Pro.

## Yêu cầu

- Python **3.9+** (khuyến nghị 3.12+)
- `pip install -r requirements.txt` (pymupdf + requests)
- API key miễn phí: https://aistudio.google.com → `export GEMINI_API_KEY=AIza...`

## Bắt đầu nhanh

```bash
# 1. Test pipeline KHÔNG cần API key (mock AI) — nên chạy đầu tiên:
python main.py sach.pdf --dry-run

# 2. Chạy thật:
python main.py sach.pdf --level "Lớp 6"

# 3. Tiết kiệm quota (khuyến nghị cho sách dài, free tier):
python main.py sach.pdf --level "Lớp 6" --no-images

# 4. Có thẩm định chéo bởi model thứ hai:
export GROQ_API_KEY=gsk_...          # free: https://console.groq.com
python main.py sach.pdf --level "Lớp 6" --review
```

## Kết quả (`runs/<tên-pdf>/output/`)

```
output/
├── topics.csv        # snapshot TÍCH LUỸ đầy đủ — dùng cho lần import chính thức
├── multichoice.csv   #   (UTF-8 BOM, đúng cột template; ảnh tham chiếu bằng filename trần)
├── images/           # TẤT CẢ ảnh: {topic_slug}_{nn}.png|jpg|svg — upload riêng vào hệ thống
├── manifest.json     # bản đồ topic → ảnh → caption → nguồn + warnings + quality checks
├── review_report.md  # (nếu --review) báo cáo thẩm định — ĐỌC TRƯỚC KHI IMPORT
├── batch-01/         # DELTA: chỉ các topic hoàn chỉnh trong lần chạy 1
│   └── topics.csv + multichoice.csv + images/ + manifest.json
├── batch-02/         # chỉ topic MỚI của lần chạy tiếp (sau khi hết quota, resume...)
└── ...
```

**Batch để test từng lô, snapshot gốc để ship.** File batch cũ bất biến;
chạy lại mà không có topic mới thì không sinh batch mới.

## Pipeline (topic-major)

Sau khi có mục lục (stage 1-2), tool xử lý **trọn gói từng topic** —
hết quota giữa chừng vẫn có N topic hoàn chỉnh, tự export partial trước khi thoát:

```
1. TOC        bookmark PDF (0 token) hoặc AI đọc PDF suy ra   → work/01_toc.json
2. Structure  slug/order sinh bằng code (deterministic)       → work/02_structure.json
─ vòng lặp từng topic ─
3. Content    Markdown bài học + key_points (AI, chunk trang) → work/03_content.json
4. Images     trích ảnh PDF + AI lọc; fallback sinh SVG       → work/04_images.json + output/images/
5. Questions  MCQ theo key_points (coverage) + validation     → work/05_questions.json
6. Review     (--review) model thứ 2 thẩm định                → work/06_review.json
─ hết vòng lặp ─
7. Export     batch delta + snapshot full + quality checks    → output/
```

**Resume mặc định**: đứt giữa chừng → chạy lại lệnh cũ; topic hoàn chỉnh bỏ
qua, topic dở dang chạy tiếp đúng bước thiếu. Gặp lỗi hết quota ngày: tool báo
rõ, export partial rồi thoát — quota reset ~14-15h chiều giờ VN.

## Toàn bộ options

| Flag | Ý nghĩa |
|---|---|
| `--level "Lớp 6"` | Giá trị cột `level` (mặc định "Lớp 6") |
| `--dry-run` | MockGemini, không cần API key — kiểm tra pipeline & format output |
| `--no-images` | Bỏ stage ảnh: −1..2 request/topic (~30%), lấy ảnh sau bằng cách chạy lại bỏ cờ này |
| `--no-validate` | Bỏ pass tự giải kiểm chứng đáp án (không khuyến nghị) |
| `--review` | Bật stage 6: model thứ hai thẩm định content + câu hỏi |
| `--reviewer X` | `groq` (Llama 70B, độc lập nhà cung cấp — mặc định) / `openrouter` (DeepSeek R1) / `gemini-pro` (duy nhất đối chiếu được PDF gốc) |
| `--review-fix` | Tự loại câu hỏi bị review đánh `severity=high` (mặc định chỉ báo cáo) |
| `--redo-from N` | Xoá cache stage N→7 rồi sinh lại (vd `5`: sinh lại câu hỏi; ≤5 reset đánh số batch) |
| `--force-ai-toc` | Bỏ qua bookmark PDF, luôn dùng AI trích mục lục |
| `--dpi N` | Nén trang scan độ phân giải CAO về N dpi gray (có guard chống upscale — scan đã nhỏ thì tự giữ nguyên) |
| `--model` | Mặc định `gemini-2.5-flash` |
| `--interval` | Giây giữa 2 request (mặc định 6 ≈ 10 RPM free tier) |

Biến môi trường: `GEMINI_API_KEY` (bắt buộc trừ dry-run), `GROQ_API_KEY` /
`OPENROUTER_API_KEY` (theo reviewer).

## Báo cáo token (luôn bật)

Cuối mỗi phiên in bảng token theo tag (content/questions/validate/review/...),
phiên này + cộng dồn; chi tiết ở `work/usage.json`. Dùng nó để quyết định
tối ưu bằng SỐ LIỆU: ví dụ so tổng token trước/sau khi bật `--no-images`,
hoặc xem validation chiếm bao nhiêu % trước khi cân nhắc bỏ.

## Quality checks thuần code (luôn bật, 0 token)

Chạy trên toàn bộ câu hỏi mỗi lần export, ghi vào console + `manifest.json`:

- **Thiên vị vị trí đáp án**: 1 chữ cái chiếm >40% (kỳ vọng 25%) → cảnh báo
- **Đáp án đúng luôn dài nhất** (>60% số câu) → người làm bài đoán được không cần học
- **Phương án trùng nhau** trong cùng câu; **thiếu giải thích**
- **Câu hỏi gần-trùng-lặp** giữa các topic (similarity ≥ 0.92)

## Quy trình khuyến nghị (QC-friendly)

1. `--dry-run` → xác nhận format với hệ thống import.
2. Chạy thật; khi Stage 1-2 in mục lục, soát page range trong
   `work/01_toc.json` (PDF scan: số trang in lệch số trang file). Sai thì sửa
   tay JSON + `--redo-from 2`.
3. Test import `batch-01/` trước; đọc `review_report.md` + phần `warnings`
   trong `manifest.json` + key `_dropped` trong `work/05_questions.json`.
4. Ưng chất lượng → chạy hết, import file snapshot gốc.
5. Sau lần chạy full đầu tiên: xem `work/usage.json` để biết chi phí thật
   từng công đoạn trước khi tối ưu tiếp.

## Troubleshooting

- **"HẾT QUOTA NGÀY"**: chạy lại chính lệnh cũ sau ~14-15h chiều giờ VN — resume tự lo.
- **429 kèm hint "theo PHÚT"**: tăng `--interval 15`.
- **Mục lục sai**: sửa `work/01_toc.json` → `--redo-from 2`.
- **Tiếng Việt vỡ trong Excel**: file có UTF-8 BOM; nếu vẫn vỡ dùng Data → From Text/CSV → UTF-8.
- **Reviewer lỗi/hết quota**: chạy lại — topic đã review bỏ qua; đổi `--reviewer` khác cũng được.

## Lưu ý dữ liệu

Free tier của Google **có thể dùng dữ liệu gửi lên để cải thiện model** —
không dùng cho tài liệu nội bộ/nhạy cảm. Khi cần: paid tier hoặc self-host
(viết thêm client cùng interface trong `gemini.py`).
