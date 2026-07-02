# pdf2learn — PDF → Learning Package (topics.csv + multichoice.csv)

Prototype pipeline: đọc PDF giáo trình → chia module/topic → soạn bài học Markdown
(kèm hình minh hoạ) → sinh câu hỏi trắc nghiệm phủ hết kiến thức → export đúng
template import (`topics.csv`, `multichoice.csv`) + thư mục `images/` + `manifest.json`.

AI: **Google Gemini API free tier** (đọc PDF native, structured output).

## Yêu cầu

- Python **3.9+** (khuyến nghị 3.12+; bản 3.9 của macOS hệ thống chạy được nhưng đã EOL)

## Cài đặt

```bash
pip install -r requirements.txt        # pymupdf + requests
```

Lấy API key **miễn phí** tại https://aistudio.google.com → Get API key, rồi:

```bash
export GEMINI_API_KEY=AIza...
```

## Chạy

```bash
# Test pipeline KHÔNG cần API key (mock AI) — nên chạy đầu tiên:
python main.py sach.pdf --dry-run

# Chạy thật:
python main.py sach.pdf --level "Lớp 6"
```

Kết quả nằm ở `runs/<tên-pdf>/output/`:

```
output/
├── topics.csv        # UTF-8 BOM, cột: module_slug,module_title,topic_slug,topic_title,order,level,content
├── multichoice.csv   # UTF-8 BOM, cột: topic_slug,question,A,B,C,D,correct_answer,explanation_vi,difficulty
├── images/           # {topic_slug}_{nn}.png|jpg|svg — upload riêng vào hệ thống
└── manifest.json     # bản đồ topic → ảnh → caption → nguồn (để đối soát/QC)
```

Trong cột `content`, ảnh được tham chiếu bằng **filename trần**:
`![caption](chuong-1-bai-1_01.svg)` — khớp tên file trong `images/`.

## Options

| Flag | Ý nghĩa |
|---|---|
| `--level "Lớp 6"` | Giá trị cột `level` (mặc định "Lớp 6") |
| `--dry-run` | MockGemini, không gọi API — kiểm tra pipeline & format output |
| `--redo-from N` | Xoá cache từ stage N trở đi rồi sinh lại (vd `--redo-from 5`: chỉ sinh lại câu hỏi) |
| `--no-images` | Bỏ qua stage hình minh hoạ (nhanh, tiết kiệm ~40% request) |
| `--no-validate` | Bỏ qua pass kiểm chứng đáp án (không khuyến nghị) |
| `--force-ai-toc` | Bỏ qua bookmark PDF, luôn dùng AI trích mục lục |
| `--model` | Mặc định `gemini-2.5-flash`; nâng chất lượng: `gemini-2.5-pro` (free tier ít quota hơn) |
| `--interval` | Giây giữa 2 request, mặc định 6 (free tier ~10 RPM) |

## v2 — Cross-model review (`--review`)

Model THỨ HAI (khác gốc) thẩm định lại toàn bộ content + câu hỏi: tự giải lại
đáp án, soi distractor, bắt mâu thuẫn/nghi bịa, liệt kê key point chưa có câu hỏi.

```bash
# Groq (Llama 3.3 70B) — free, độc lập nhà cung cấp (khuyến nghị mặc định):
export GROQ_API_KEY=gsk_...        # lấy free: https://console.groq.com
python main.py sach.pdf --review

# DeepSeek R1 free qua OpenRouter — reasoning mạnh, chấm đáp án kỹ:
export OPENROUTER_API_KEY=sk-or-...   # https://openrouter.ai/keys
python main.py sach.pdf --review --reviewer openrouter

# Gemini 2.5 Pro (cùng GEMINI_API_KEY) — DUY NHẤT đối chiếu được PDF gốc
# (faithfulness check); quota free tier Pro thấp, interval tự nâng 15s:
python main.py sach.pdf --review --reviewer gemini-pro
```

Mặc định **chỉ báo cáo** ra `output/review_report.md` — người QC đọc và quyết.
Thêm `--review-fix` để tự loại câu hỏi bị đánh `severity=high` (câu bị loại
in ra console kèm lý do). Review có cache riêng (`work/06_review.json`),
resume theo topic; sinh lại review: `--redo-from 6`.

Chiến thuật dùng free tier hiệu quả: chạy chính bằng Gemini Flash, review
bằng Groq — hai quota độc lập, không giẫm chân nhau.

## Pipeline & resume

```
1. TOC        bookmark PDF (0 token) hoặc AI     → work/01_toc.json
2. Structure  slug/order sinh bằng code           → work/02_structure.json
3. Content    Markdown + key_points / topic (AI)  → work/03_content.json
4. Images     trích ảnh PDF + AI lọc; fallback SVG→ work/04_images.json + output/images/
5. Questions  MCQ theo key_points + validation    → work/05_questions.json
6. Review     (v2, --review) model 2 thẩm định     → work/06_review.json
7. Export     CSV + manifest + review_report.md    → output/
```

**Mặc định luôn resume**: đứt giữa chừng (hết quota ngày, rate limit) → chạy lại
lệnh cũ, các topic đã xong tự bỏ qua. Kết quả trung gian lưu **theo từng topic**
sau mỗi request.

## Ước lượng request / free tier

Mỗi topic ≈ 3–4 request (content 1, lọc ảnh/SVG 1, câu hỏi 1, validation 1).
Sách 30 bài ≈ ~110 request → nằm gọn trong quota ngày của free tier Flash.
PDF > 15MB tự động upload qua Files API thay vì inline.

## Kiểm tra chất lượng (khuyến nghị QC)

1. Chạy 1 chương trước, import thử vào hệ thống, soát nội dung + đáp án.
2. Xem `work/05_questions.json` → key `_dropped`: các câu bị loại vì validation
   (AI tự giải ra đáp án khác đáp án khai báo) — đọc để đánh giá độ tin cậy.
3. `manifest.json` → `warnings`: topic thiếu câu hỏi, đáp án lỗi.

## Troubleshooting

- **HTTP 429 liên tục**: tăng `--interval 15`; hoặc đã hết quota ngày → chạy lại
  hôm sau, pipeline tự resume.
- **Mục lục sai** (PDF bookmark lởm): sửa tay `runs/<pdf>/work/01_toc.json`
  rồi `--redo-from 2`.
- **PDF scan (ảnh chụp)**: Gemini vẫn đọc được (OCR ngầm) nhưng bookmark thường
  không có → tự động rơi vào nhánh AI TOC.
- **Tiếng Việt vỡ khi mở CSV bằng Excel**: file đã có UTF-8 BOM, mở bằng
  Excel bình thường; nếu vẫn vỡ → dùng Data > From Text/CSV chọn UTF-8.

## Lưu ý dữ liệu

Free tier của Google **có thể dùng dữ liệu gửi lên để cải thiện model**.
Không dùng cho tài liệu nội bộ/nhạy cảm — khi cần, chuyển sang paid tier
hoặc self-host (Ollama) bằng cách viết thêm client cùng interface với `gemini.py`.
