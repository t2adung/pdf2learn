# pdf2learn — PDF → Learning Package (topics.csv + multichoice.csv)

Pipeline AI: đọc PDF giáo trình (kể cả PDF **scan**) → chia module/topic → soạn bài
học Markdown kèm hình minh hoạ → sinh câu hỏi trắc nghiệm phủ hết kiến thức →
export đúng template import (`topics.csv`, `multichoice.csv`) + `images/` +
`manifest.json`, kèm cross-model review, quality checks và báo cáo token.

**Hai backend AI** (chọn bằng `--backend`):

- `gemini` (mặc định) — **Google Gemini API free tier**, tính theo token, cần
  `GEMINI_API_KEY`. Reviewer tuỳ chọn: Groq / OpenRouter / Gemini Pro.
- `claude` — dùng **gói subscription Claude Max/Pro** qua Claude Code CLI
  (`claude -p`) trên máy. **KHÔNG cần API key, KHÔNG tính tiền theo token** (chỉ
  ăn hạn mức subscription). Xem [Dùng Claude thay cho Google API](#dùng-claude-thay-cho-google-api-backend-claude).

## Yêu cầu

- Python **3.9+** (khuyến nghị 3.12+)
- `pip install -r requirements.txt` (pymupdf + requests + python-dotenv)
- Backend `gemini`: API key miễn phí tại https://aistudio.google.com →
  `export GEMINI_API_KEY=AIza...` (hoặc chép `env.example` thành `.env` và dán key
  vào — pipeline tự nạp qua python-dotenv, khỏi export mỗi lần).
- Backend `claude`: đã cài **Claude Code** và `claude login` bằng tài khoản
  **Max/Pro** — không cần biến môi trường nào.

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

# 5. Dùng SUBSCRIPTION Claude Max/Pro thay API key (0đ phụ trội, không cần GEMINI_API_KEY):
#    cần: đã cài Claude Code + `claude login` (Max/Pro)
python main.py sach.pdf --level "Lớp 6" --backend claude
```

> **`--backend claude`**: gọi Claude Code CLI (`claude -p`) trên máy, dùng đúng gói
> subscription — **không tính tiền theo token**, chỉ ăn hạn mức. Chi tiết cách hoạt
> động ở mục [Dùng Claude thay cho Google API](#dùng-claude-thay-cho-google-api-backend-claude) ngay dưới đây.

## Dùng Claude thay cho Google API (backend claude)

Thay vì gọi REST API của Gemini (tính tiền/hạn mức theo token), backend này gọi
**Claude Code CLI** ngay trên máy bằng đúng phiên đăng nhập Claude Max/Pro của bạn.
Mọi stage AI (content, câu hỏi, review, và cả trích mục lục bằng AI) đều đi qua
`claude -p` — **0đ phụ trội, không tính token, chỉ trừ vào hạn mức subscription**.

### Điều kiện

1. Cài **Claude Code** và đăng nhập gói Max/Pro:
   ```bash
   claude login          # đăng nhập bằng tài khoản Max/Pro
   claude -p "xin chào"  # thử: phải trả lời được là OK
   ```
   Nếu `claude` không có trong PATH, tool sẽ cảnh báo ngay khi khởi động.
2. **Không cần** `GEMINI_API_KEY` (và không cần key reviewer Groq/OpenRouter).

### Chạy

```bash
# Mặc định model sonnet:
python main.py sach.pdf --level "Lớp 6" --backend claude

# Đổi model (opus mạnh hơn, tốn hạn mức hơn):
python main.py sach.pdf --level "Lớp 6" --backend claude --model opus

# Có review chéo model (reviewer tự dùng model KHÁC — xem dưới):
python main.py sach.pdf --level "Lớp 6" --backend claude --review
```

> `--model` mặc định là `gemini-2.5-flash`. Khi bật `--backend claude`, nếu `--model`
> vẫn là giá trị Gemini thì tool **tự đổi sang `sonnet`**. Truyền tên model Claude
> (`sonnet`, `opus`, …) để chỉ định rõ.

### Cơ chế hoạt động (bên trong)

- **Cùng interface với `gemini.Gemini`** (`generate_json` / `generate_text` /
  `pdf_part` / `image_part`), nên các stage KHÔNG phải sửa gì — chỉ thay client.
- Mỗi lời gọi AI = **1 lần shell ra**:
  ```
  claude -p "<prompt>" --output-format json --model <model> \
         --allowedTools Read --add-dir <thư-mục-tạm>
  ```
- **PDF/ảnh KHÔNG nhúng vào prompt**: chúng được ghi ra file tạm, prompt chỉ chứa
  đường dẫn + yêu cầu Claude **đọc bằng công cụ `Read`** (Read hỗ trợ cả PDF lẫn
  ảnh). Nhờ vậy prompt luôn nhỏ, không đụng giới hạn độ dài dòng lệnh.
- **Ép JSON**: với các stage cần structured output, prompt kèm schema và yêu cầu
  "trả về DUY NHẤT JSON". Nếu output lỡ không parse được → tool **tự sửa 1 lần**
  (gửi lại nhờ Claude chỉnh cú pháp JSON) trước khi báo lỗi.
- **Retry**: lỗi tạm thời retry tối đa 4 lần (backoff 5s→60s). Riêng lỗi **hết hạn
  mức** thì không retry — nhường cho cơ chế resume.

### Reviewer khi dùng Claude

Bật `--review` với backend claude thì reviewer là **một model Claude KHÁC** (cross-model):
mặc định content sinh bằng `sonnet` → reviewer dùng `opus` (và ngược lại). Reviewer
đọc được **PDF gốc** qua `Read` để đối chiếu. Lúc này cờ `--reviewer`
(groq/openrouter/gemini-pro) bị bỏ qua — không cần key ngoài.

### Hết hạn mức → tự dừng & resume

Khi CLI báo hết hạn mức (usage/rate limit, "resets at", 429…), tool ném
`ClaudeLimitError`:

- **Export ngay phần các topic đã hoàn chỉnh** (partial), rồi **thoát mã 42**.
- Mã 42 để runner tự động phân biệt "**tạm dừng chờ reset**" với hoàn tất (0) hay
  lỗi thật (1).
- **Resume**: khi cửa sổ hạn mức reset, chạy lại **đúng lệnh cũ** — topic đã xong
  bị bỏ qua, chỉ làm tiếp topic dở dang. Không mất tiến độ.

### Lưu ý riêng của backend claude

- **Mục lục**: nên dùng bookmark PDF hoặc `--toc-file` (dựng sẵn bằng
  `build_toc.py` / `toc_from_images.py`) thay vì để AI đọc cả cuốn suy ra mục lục —
  vừa chính xác 100%, vừa tránh cho Claude phải Read toàn bộ PDF dài.
- **Báo cáo token vẫn in** như backend Gemini (lấy từ `usage` trong envelope JSON
  của CLI) để bạn theo dõi mức tiêu thụ — nhưng **bạn không bị tính tiền theo token**,
  đây chỉ là số liệu tham khảo.
- Chạy **local/Cowork trên máy có Claude Code**; không dùng được trong môi trường
  CI không cài `claude`.

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

Cú pháp: `python main.py <file.pdf> [options]`. Dưới đây là **tất cả cờ đang hoạt
động**, nhóm theo mục đích.

### Nguồn AI & tốc độ

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--backend gemini\|claude` | `gemini` | Nguồn AI. `gemini` = REST API, cần `GEMINI_API_KEY`. `claude` = Claude Code CLI `claude -p`, dùng **subscription** Max/Pro (không cần key, không tính token; hết hạn mức → thoát mã 42, chạy lại để resume). Xem mục Claude ở trên |
| `--model X` | `gemini-2.5-flash` | Tên model. Với `--backend claude`: nếu vẫn để giá trị Gemini thì tự đổi sang `sonnet`; truyền `sonnet`/`opus` để chỉ định rõ |
| `--interval S` | `6.0` | Giây tối thiểu giữa 2 request (Gemini free tier ~10 RPM → 6s) |
| `--dry-run` | tắt | Dùng MockGemini, **không cần API key** — kiểm tra pipeline & format output |

### Nội dung bài học (`level`, phạm vi, định dạng cột content)

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--level "Lớp 6"` | `Lớp 6` | Giá trị cột `level` trong CSV |
| `--limit N` | `0` (hết) | CHỈ xử lý N bài ĐẦU rồi export luôn (vd `--limit 2` test nhanh bài 1-2). Cache giữ nguyên: bỏ cờ này chạy lại sẽ làm tiếp phần còn lại |
| `--density full\|compact\|minimal` | `full` | Mật độ chữ cột content: `full` (đủ) / `compact` (3 point/mục, cắt point dài) / `minimal` (chỉ mục tiêu + nội dung chính + mindmap). Đổi mức **0 token** — chỉ re-render |
| `--content-format markdown\|json` | `markdown` | Định dạng cột content: `markdown` (render bằng code) hoặc `json` (Learning Object thô). Đổi qua lại **0 token**, chỉ chạy lại |
| `--subject "..."` | rỗng | Tên môn học ghi vào JSON bài học (vd `"Lịch sử và Địa lí"`) |
| `--grade "..."` | tự rút từ `--level` | Khối lớp ghi vào JSON (mặc định lấy số từ `--level`, `"Lớp 6"` → `"6"`) |
| `--export-json` | tắt | Ghi thêm `output/json/{topic_slug}.json` theo format đích (nhúng quiz, mindmap_mermaid) — **0 token**, sinh từ cache |

### Mục lục (TOC)

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--toc-file PATH` | không | Dùng file `01_toc.json` dựng sẵn (vd từ `build_toc.py`/`toc_from_images.py`) thay cho bookmark/AI — **0 token, chính xác 100%**. Khuyến nghị cho backend claude |
| `--force-ai-toc` | tắt | Bỏ qua bookmark PDF, **luôn** dùng AI trích mục lục |
| `--yes` | tắt | Bỏ bước dừng xác nhận mục lục trước khi gọi AI (bắt buộc trong môi trường không có TTY: Colab/CI) |

### Hình ảnh

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--no-images` | tắt | Bỏ stage ảnh (−1..2 request/topic ~30%). Lấy ảnh sau bằng cách chạy lại, bỏ cờ này |
| `--book-images` | tắt | Đính kèm **NGUYÊN TRANG sách** (không cắt hình) — **0 token, thuần code**: render từng trang trong page range ra PNG rồi gắn mỗi trang vào đúng mục nội dung. Ảnh trang nằm trong "Nội dung chính"; mục "🖼️ Hình minh hoạ" cuối bài chỉ còn mindmap. Mặc định TẮT: chỉ giữ mindmap SVG |
| `--dpi N` | `0` (tắt) | Nén trang scan độ phân giải CAO về N dpi grayscale trước khi gửi/ render (giảm token mạnh; khuyến nghị ~110 cho sách scan). Có guard chống upscale — scan đã nhỏ thì giữ nguyên |

### Câu hỏi & review

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--no-validate` | tắt | Bỏ pass tự giải kiểm chứng đáp án ở stage 5 (không khuyến nghị) |
| `--review` | tắt | Bật stage 6: model thứ hai thẩm định content + câu hỏi |
| `--reviewer groq\|openrouter\|gemini-pro` | `groq` | Model reviewer (chỉ áp dụng khi backend `gemini`): `groq` (Llama 70B) / `openrouter` (DeepSeek R1 free) / `gemini-pro` (duy nhất đối chiếu được PDF gốc). Với backend `claude` cờ này bị bỏ qua — reviewer là model Claude khác |
| `--review-fix` | tắt | Tự loại câu hỏi bị review đánh `severity=high` (mặc định chỉ báo cáo) |

### Cache & sinh lại

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--redo-from N` | không | Xoá cache từ stage N (1–7) trở đi rồi sinh lại (vd `5`: sinh lại câu hỏi; N≤4 xoá cả ảnh; N≤5 reset đánh số batch) |
| `--redo-content` | tắt | Sinh LẠI content (stage 3, gọi AI) + ảnh mindmap (stage 4), NHƯNG giữ nguyên câu hỏi (stage 5) + review (stage 6) đã có — **0 token cho câu hỏi**. Làm mới bài học mà không đụng bộ câu hỏi đã duyệt |

### Biến môi trường

| Biến | Khi nào cần |
|---|---|
| `GEMINI_API_KEY` | Backend `gemini` (bắt buộc, trừ `--dry-run`). **Không** cần cho backend `claude` |
| `GROQ_API_KEY` / `OPENROUTER_API_KEY` | Chỉ khi `--review` với `--reviewer groq`/`openrouter` (backend gemini) |

Có thể đặt các biến trên trong file `.env` (chép từ `env.example`) — tự nạp qua
python-dotenv.

## Công cụ dựng mục lục (`toc_from_images.py` + `build_toc.py`)

Hai script phụ để tạo sẵn `01_toc.json` chính xác 100% rồi nạp vào `main.py` bằng
`--toc-file` — tránh để AI đọc cả cuốn PDF suy ra mục lục (đặc biệt hữu ích với
`--backend claude`). AI **chỉ làm đúng việc OCR vài trang mục lục** (1 request rẻ);
việc tính `page_end`, áp offset, kiểm tra thứ tự trang là **code deterministic**.

Luồng đầy đủ:

```
ảnh/PDF trang mục lục
   └─(toc_from_images.py — 1 request AI OCR)→ toc.txt   ← MỞ RA SOÁT/SỬA TAY (0 token)
        └─(build_toc.py — thuần code)→ 01_toc.json
             └─ main.py sach.pdf --toc-file 01_toc.json
```

### `toc_from_images.py` — OCR trang mục lục → `toc.txt`

```bash
# Nguồn có thể là: thư mục ảnh, thư mục chứa PDF, 1 file .pdf, hoặc 1 file ảnh
python3 toc_from_images.py toc_images/ten-sach --out ten-sach.toc.txt
python3 toc_from_images.py toc_images/ten-sach.pdf --out ten-sach.toc.txt

# Dùng SUBSCRIPTION Claude thay GEMINI_API_KEY (giống main.py):
python3 toc_from_images.py toc_images/ten-sach --backend claude --out ten-sach.toc.txt

# Gộp luôn ra 01_toc.json (khi đã biết offset + last-page):
python3 toc_from_images.py toc_images/ten-sach --offset 2 --last-page 197 \
    --json-out runs/ten-sach/work/01_toc.json
```

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `images_dir` (vị trí) | — | Nguồn mục lục: thư mục ảnh/PDF, 1 file `.pdf`, hoặc 1 file ảnh. PDF được render từng trang rồi OCR (khỏi chụp tay) |
| `--backend gemini\|claude` | `gemini` | Nguồn AI OCR — **giống `main.py`**: `gemini` (cần `GEMINI_API_KEY`) hoặc `claude` (Claude Code CLI `claude -p`, dùng subscription Max/Pro, không cần key). Ảnh mục lục được ghi file tạm cho Claude đọc bằng `Read` |
| `--out PATH` | `<images_dir>.toc.txt` | Nơi ghi `toc.txt` (điểm dừng để soát tay) |
| `--offset N` | — | (tuỳ chọn) `page_pdf = page_in + offset` — kèm `--last-page` để ghi thẳng JSON |
| `--last-page M` | — | (tuỳ chọn) trang PDF nơi bài cuối kết thúc |
| `--json-out PATH` | không | Ghi thẳng `01_toc.json` (**cần cả** `--offset` + `--last-page`) |
| `--model X` | `gemini-2.5-flash` | Model OCR. Với `--backend claude`: giá trị Gemini tự đổi sang `sonnet` |
| `--interval S` | `6.0` | Giây giữa 2 request |
| `--dry-run` | tắt | MockGemini, không cần API key |

### `build_toc.py` — `toc.txt` (đã soát) → `01_toc.json`

```bash
python3 build_toc.py ten-sach.toc.txt --offset 2 --last-page 197 \
    --out runs/ten-sach/work/01_toc.json
```

| Flag | Bắt buộc | Ý nghĩa |
|---|---|---|
| `toc_txt` (vị trí) | ✔ | File `.txt` định dạng `= Tên module` / `Tên bài \| số trang IN` (dòng `#` bị bỏ qua) |
| `--offset N` | ✔ | `page_pdf = page_in + offset`. Ví dụ: trang in "6" nằm ở trang PDF thứ 8 → offset = 2. Gõ thẳng số trang PDF thì để `0` |
| `--last-page M` | ✔ | Trang PDF nơi **bài cuối** kết thúc (`page_end` bài cuối). `page_end` mỗi bài = trang bắt đầu bài kế − 1 |
| `--out PATH` | ✔ | Nơi ghi `01_toc.json` |

Chạy **thuần code, 0 token**. Sai số trang → sửa lại `toc.txt` rồi chạy lại
`build_toc.py`; không tốn request AI.

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

- **"HẾT QUOTA NGÀY" (Gemini)**: chạy lại chính lệnh cũ sau ~14-15h chiều giờ VN — resume tự lo.
- **429 kèm hint "theo PHÚT"**: tăng `--interval 15`.
- **Backend claude báo hết hạn mức (thoát mã 42)**: bình thường — đã export phần
  hoàn chỉnh. Chờ cửa sổ subscription reset rồi chạy lại **đúng lệnh cũ** để resume.
- **`Không tìm thấy lệnh claude trong PATH`**: cài Claude Code + `claude login`
  (Max/Pro) trước khi dùng `--backend claude`.
- **Mục lục sai**: sửa `work/01_toc.json` → `--redo-from 2`.
- **Tiếng Việt vỡ trong Excel**: file có UTF-8 BOM; nếu vẫn vỡ dùng Data → From Text/CSV → UTF-8.
- **Reviewer lỗi/hết quota**: chạy lại — topic đã review bỏ qua; đổi `--reviewer` khác cũng được.

## Lưu ý dữ liệu

Free tier của Google **có thể dùng dữ liệu gửi lên để cải thiện model** —
không dùng cho tài liệu nội bộ/nhạy cảm. Khi cần: paid tier, dùng **`--backend claude`**
(gửi qua phiên Claude Code của bạn), hoặc self-host (viết thêm client cùng interface
trong `gemini.py`).

## Notes
```
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

# Backend gemini:
export GEMINI_API_KEY=AIza...
export GROQ_API_KEY=gsk_...          # (tuỳ chọn) free: https://console.groq.com
python3 main.py sach.pdf --level "Lớp 6" --review

# Backend claude (không cần API key, cần đã `claude login` Max/Pro):
python3 main.py sach.pdf --level "Lớp 6" --backend claude
```
## Cowork + Claude app

[Điện thoại: thả PDF vào Google Drive]
        │  (folder đồng bộ về Mac)
[Claude app trên điện thoại] ──remote──> [Cowork trên Mac ở nhà]
        │                                      │ đọc COWORK_GUIDE.md
        │                                      │ chạy main.py, theo dõi log
        └── nhận thông báo xong <────── copy output/ vào folder Drive
        
### Giai đoạn 1 — Chuẩn bị Mac ở nhà (làm 1 lần, ~15 phút)
- Bước 1. Chống ngủ. Máy ngủ = mọi thứ chết. System Settings → Displays → Advanced → Prevent automatic sleeping on power adapter when the display is off: ON. Cắm sạc thường trực. (Kiểm tra thêm Battery/Energy tuỳ bản macOS.)
- Bước 2. API key phải "sống" trong mọi shell. Cowork sẽ mở shell mới để chạy lệnh, export tạm trong terminal cũ không còn tác dụng. Ghi vào profile:
```
bashecho 'export GEMINI_API_KEY=AIza...' >> ~/.zshrc
source ~/.zshrc
echo $GEMINI_API_KEY   # phải in ra key
```
- Bước 3. Tạo cấu trúc thư mục vào/ra qua Google Drive. Cài [Google Drive for desktop] trên Mac, rồi:
```
bashmkdir -p ~/Google\ Drive/My\ Drive/pdf2learn-inbox
mkdir -p ~/Google\ Drive/My\ Drive/pdf2learn-outbox
(Đường dẫn thật có thể là ~/Library/CloudStorage/GoogleDrive-<email>/My Drive/... tuỳ bản Drive — chạy ls ~/Library/CloudStorage/ để xác định, và dùng đường dẫn đó nhất quán ở Bước 4.)
```
- Bước 4. Viết file hướng dẫn cho agent — trái tim của cả flow. Tạo ~/Documents/pdf2learn/pdf2learn/COWORK_GUIDE.md:
markdown# Vận hành pdf2learn (PDF -> topics.csv + multichoice.csv)

#### Đường dẫn
- Project: ~/Documents/pdf2learn/pdf2learn
- PDF đầu vào: <đường dẫn Drive>/pdf2learn-inbox/
- Kết quả trả về: <đường dẫn Drive>/pdf2learn-outbox/

#### Quy trình chuẩn khi được yêu cầu "xử lý file X.pdf"
1. Copy file từ inbox vào thư mục project.
2. Chạy:
   cd ~/Documents/pdf2learn/pdf2learn
   source ../.venv/bin/activate
   python3 main.py X.pdf --level "Lớp 6"
3. Theo dõi output. Tool tự resume: nếu bị ngắt/HTTP 429 kéo dài,
   chờ 2 phút rồi chạy LẠI CHÍNH LỆNH ĐÓ (topic đã xong sẽ bỏ qua).
4. Khi hoàn tất: nén runs/X/output/ thành X-package.zip,
   copy vào pdf2learn-outbox/.
5. Báo cáo: số topics, số câu hỏi, danh sách "warnings" trong
   runs/X/output/manifest.json, và các câu bị loại trong
   runs/X/work/05_questions.json (key "_dropped") nếu có.

#### Quy tắc an toàn
- KHÔNG sửa code trong project, không xoá thư mục runs/ trừ khi
  được yêu cầu rõ ràng ("xoá cache", "làm lại từ đầu").
- KHÔNG chạy --dry-run cho yêu cầu xử lý thật.
- Nếu Stage 1-2 in mục lục ra: DỪNG LẠI, gửi danh sách topic cho tôi
  duyệt trước khi chạy tiếp (trừ khi tôi nói "chạy thẳng").
Điểm đáng chú ý ở dòng cuối: mình chủ động thiết kế human-in-the-loop vào đúng chỗ rủi ro nhất (mục lục sai → 120 request đổ sông) — bạn duyệt mục lục từ điện thoại rồi mới cho chạy tiếp, y hệt bước smoke test đã bàn nhưng giờ agent tự dừng chờ thay vì bạn phải Ctrl+C.
Bước 5. Chạy tay 1 lần để nghiệm thu. Tự mình chạy đúng chuỗi lệnh trong guide từ đầu đến cuối. Nguyên tắc: đừng bao giờ giao cho agent một quy trình mà chính mình chưa chạy thành công — lỗi môi trường (như 3 lỗi Python bạn vừa trải qua) phải được diệt sạch trước, vì agent gặp lỗi lạ sẽ "sáng tạo" cách sửa và có thể làm rối thêm.

### Giai đoạn 2 — Cài Cowork và kết nối tài khoản

- Tải Claude desktop/Cowork từ trang chính thức của Anthropic, đăng nhập cùng tài khoản với Claude app trên điện thoại. ⚠️ Cowork có thể yêu cầu gói trả phí — xác nhận tại support.claude.com.
- Khi Cowork hỏi quyền truy cập thư mục, cấp cho nó: thư mục project và 2 thư mục inbox/outbox. Chỉ cấp đúng 3 thư mục này, không cấp cả Home — Cowork là agent thực thi lệnh thật trên máy bạn, nguyên tắc least privilege áp dụng y như phân quyền hệ thống.
- Mở một phiên Cowork, yêu cầu nó đọc COWORK_GUIDE.md và chạy thử end-to-end với 1 PDF nhỏ ngay tại máy (bạn ngồi xem). Đây là bước nghiệm thu agent — quan sát nó có làm đúng quy trình, có dừng chờ duyệt mục lục không.
- ⚠️ Bật/kiểm tra khả năng truy cập từ xa của phiên Cowork qua Claude mobile app — cách bật cụ thể bạn hỏi trực tiếp Claude trong app Cowork hoặc xem support.claude.com, vì chi tiết này mình không chắc và nó có thể thay đổi theo phiên bản.

### Giai đoạn 3 — Vòng lặp sử dụng từ xa
Từ bất kỳ đâu:

Điện thoại: mở app Google Drive → upload PDF vào pdf2learn-inbox.
Mở Claude app → vào phiên Cowork trên máy nhà → nhắn:

"Có file lsdl-lop6.pdf mới trong inbox, xử lý theo COWORK_GUIDE.md"
