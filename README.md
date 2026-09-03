# pdf2learn — PDF → gói học liệu (topics.csv + multichoice.csv)

Pipeline AI biến một PDF giáo trình (kể cả PDF **scan**) thành gói học liệu import
được ngay:

- chia **module → topic** theo mục lục,
- soạn **bài học** dạng Learning Object rồi render cột `content` theo thứ tự cố
  định: 🎯 Mục tiêu → 🤔 Câu hỏi khởi động → 🔑 Từ khoá → 📚 Nội dung chính →
  🌍 Liên hệ thực tế → 🖼️ Hình minh hoạ → ✅ Trả lời câu hỏi khởi động,
- đính **nguyên trang sách** vào đúng mục nội dung (0 token),
- sinh **câu hỏi trắc nghiệm** phủ hết kiến thức, có pass tự giải kiểm chứng đáp án,
- **cross-model review** (tuỳ chọn) + **quality checks** thuần code + **báo cáo token**,
- export đúng template: `topics.csv`, `multichoice.csv`, `images/`, `manifest.json`
  (tuỳ chọn `output/json/` — bộ Learning Object JSON hoàn chỉnh từng bài).

**Hai backend AI** (chọn bằng `--backend`):

- `gemini` (mặc định) — **Google Gemini API free tier**, đọc PDF native, structured
  output, tính theo token, cần `GEMINI_API_KEY`. Reviewer tuỳ chọn: Groq / OpenRouter / Gemini Pro.
- `claude` — dùng **gói subscription Claude Max/Pro** qua Claude Code CLI (`claude -p`)
  trên máy. **KHÔNG cần API key, KHÔNG tính tiền theo token** (chỉ ăn hạn mức
  subscription). Xem [Dùng Claude thay cho Google API](#dùng-claude-thay-cho-google-api-backend-claude).

> **Điểm cốt lõi để tiết kiệm quota:** mọi khâu *định dạng* (render markdown, vẽ
> mindmap SVG, đính trang sách, đổi độ dài/format, dựng TOC từ file có sẵn) đều
> chạy **bằng code — 0 token**. AI chỉ dùng cho phần *nội dung* (soạn bài, ra đề,
> review). Nhờ đó đổi layout/độ dài/format chỉ cần chạy lại, không gọi lại AI.

---

## Yêu cầu & cài đặt

- Python **3.9+** (khuyến nghị 3.12+).
- Backend `gemini`: API key miễn phí Gemini: https://aistudio.google.com
- Backend `claude`: đã cài **Claude Code** và `claude login` bằng tài khoản
  **Max/Pro** — không cần biến môi trường nào.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # pymupdf + requests + python-dotenv
```

Đặt API key (chỉ cho backend `gemini`) theo 1 trong 2 cách:

```bash
# Cách A — biến môi trường:
export GEMINI_API_KEY=AIza...

# Cách B — file .env (tiện chạy local, tự nạp nhờ python-dotenv):
cp env.example .env      # rồi dán key thật vào .env
```

Reviewer chỉ cần thêm key khi dùng `--review` với backend gemini:

```bash
export GROQ_API_KEY=gsk_...            # free: https://console.groq.com
export OPENROUTER_API_KEY=sk-or-...    # free: https://openrouter.ai/keys
```

---

## Hướng dẫn sử dụng

### Bắt đầu nhanh (4 lệnh)

```bash
# 1. Test pipeline & format output KHÔNG cần API key (mock AI) — luôn chạy đầu tiên:
python3 main.py sach.pdf --dry-run

# 2. Chạy thử 2 bài đầu để nghiệm thu chất lượng trước khi làm cả cuốn:
python3 main.py sach.pdf --level "Lớp 6" --limit 2

# 3. Chạy thật cả cuốn:
python3 main.py sach.pdf --level "Lớp 6"

# 4. Có thẩm định chéo bởi model thứ hai (đọc trước khi import):
python3 main.py sach.pdf --level "Lớp 6" --review
```

> Muốn dùng **subscription Claude** thay Gemini: thêm `--backend claude` vào bất kỳ
> lệnh nào ở trên (không cần `GEMINI_API_KEY`). Xem
> [Dùng Claude thay cho Google API](#dùng-claude-thay-cho-google-api-backend-claude).

### Flow đầy đủ: từ 1 file PDF → bộ JSON học liệu hoàn chỉnh

Toàn bộ hành trình một cuốn sách, kết thúc bằng **các file JSON học liệu**
`output/json/{topic_slug}.json` (bật bằng `--export-json`) — mỗi bài 1 file gồm
`title, objectives, hook, key_terms, sections, mindmap_mermaid, hook_answer, quiz[]`.
Cột mốc **in đậm** là chỗ nên dừng để duyệt.

```bash
# ── B0. Cài đặt (làm 1 lần) — xem mục "Yêu cầu & cài đặt" ─────────────────
#        backend gemini: export GEMINI_API_KEY=...   |   hoặc dùng --backend claude

# ── B1. (khuyến nghị) Dựng sẵn mục lục CHÍNH XÁC (0 token) ────────────────
#        Bỏ qua nếu PDF đã có bookmark chuẩn.
python3 toc_from_images.py toc_images/sach --out sach.toc.txt      # OCR → toc.txt
#   → 📌 MỞ sach.toc.txt ĐỐI CHIẾU ẢNH: đúng tên bài + số trang in chưa?
python3 build_toc.py sach.toc.txt --offset 2 --last-page 197 \
    --out runs/sach/work/01_toc.json                              # → 01_toc.json

# ── B2. Xem trước FORMAT JSON, 0 chi phí (mock AI, không cần key) ─────────
python3 main.py sach.pdf --dry-run --export-json --limit 2
#   → xem cấu trúc runs/sach/output/json/*.json có khớp hệ thống đích không

# ── B3. THỬ THẬT 1–2 bài đầu (content + hình + câu hỏi), rồi export ───────
python3 main.py sach.pdf --level "Lớp 6" --toc-file runs/sach/work/01_toc.json \
    --export-json --limit 2
#   → 📌 Stage 1–2 in mục lục: soát page range trong work/01_toc.json rồi Enter
#   → Mở runs/sach/output/json/<bai-1>.json kiểm tra chất lượng
#     (chưa ưng câu hỏi? thêm --redo-from 5, giữ nguyên --limit 2 để chỉ sinh lại câu hỏi)

# ── B4. Ưng rồi → chạy HẾT cả sách (bỏ --limit; 2 bài đầu đã cache, 0 token lại) ─
python3 main.py sach.pdf --level "Lớp 6" --toc-file runs/sach/work/01_toc.json \
    --export-json
```

**Kết quả cuối** ở `runs/sach/output/`: `json/{topic_slug}.json` (**bộ JSON hoàn
chỉnh từng bài** — thứ bạn cần), `topics.csv` + `multichoice.csv` + `images/` (đúng
template import), `manifest.json`, và `review_report.md` nếu `--review`.

> `--export-json` là **thuần code, 0 token** nên bật lúc nào cũng được — kể cả
> chạy lại từ cache đã có. Dùng `--backend claude` thì thêm cờ đó vào các lệnh
> `main.py` (và `toc_from_images.py` nếu OCR mục lục bằng Claude).

### Quy trình khuyến nghị (QC-friendly)

1. **`--dry-run`** → xác nhận format khớp với hệ thống import của bạn.
2. Chạy thật. Khi Stage 1–2 in mục lục ra màn hình, tool **dừng lại chờ Enter**
   (guard 0 token). Soát kỹ page range trong `work/01_toc.json`
   — PDF scan hay có số trang in lệch số trang file. Sai thì `Ctrl+C`, sửa tay
   JSON rồi chạy lại với `--redo-from 2`. (Bỏ qua bước dừng bằng `--yes`.)
3. Dùng **`--limit 2`** để soi kỹ bài 1–2, hoặc test import thư mục
   `output/batch-01/` trước.
4. Đọc `review_report.md` (nếu `--review`) + mục `warnings` trong `manifest.json`
   + key `_dropped` trong `work/05_questions.json` (các câu bị loại).
5. Ưng chất lượng → bỏ `--limit`, chạy hết, import **file snapshot gốc**.
6. Xem `work/usage.json` để biết chi phí token thật từng công đoạn trước khi tối ưu.

### Resume — chạy lại là tiếp tục

Tool xử lý **trọn gói từng topic** (content → images → questions → review cho
topic N rồi mới sang N+1). Đứt giữa chừng (rate limit, hết quota, tắt máy) →
**chỉ cần chạy lại đúng lệnh cũ**: topic đã hoàn chỉnh được bỏ qua, topic dở
dang chạy tiếp đúng bước còn thiếu. Gặp lỗi hết quota ngày, tool báo rõ, export
phần đã xong (partial) rồi thoát — quota free tier reset ~14–15h chiều giờ VN.
(Backend claude hết hạn mức thì thoát **mã 42** — xem mục Claude bên dưới.)

### Mục lục chính xác 100% từ file có sẵn (0 token)

Với sách scan / bookmark rác, thay vì để AI đoán mục lục, hãy dựng TOC bằng code:

```bash
# A) Gõ tay mục lục ra .txt rồi dựng JSON (xem cách tính --offset trong build_toc.py):
python3 build_toc.py sach.toc.txt --offset 2 --last-page 197 \
    --out runs/sach/work/01_toc.json

# B) OCR ảnh/PDF trang mục lục -> toc.txt (kiểm tra tay) -> JSON:
python3 toc_from_images.py toc_images/sach --out sach.toc.txt        # 1 request OCR
#    ...OCR bằng subscription Claude thay vì Gemini:
python3 toc_from_images.py toc_images/sach --backend claude --out sach.toc.txt
python3 build_toc.py sach.toc.txt --offset 2 --last-page 197 --out runs/sach/work/01_toc.json

# rồi trỏ pipeline vào file đã dựng:
python3 main.py sach.pdf --toc-file runs/sach/work/01_toc.json --level "Lớp 6"
```

`toc_from_images.py` nhận **cùng bộ cờ backend** như `main.py`
(`--backend {gemini,claude}`, `--model`, `--interval`, `--dry-run`), thêm
`--out`, `--offset`, `--last-page`, `--json-out` (ghi thẳng `01_toc.json` khi có
đủ offset + last-page). `build_toc.py` là **thuần code 0 token**: `toc_txt`
(vị trí) + `--offset` + `--last-page` + `--out` (đều bắt buộc), tự tính
`page_end = trang bắt đầu bài kế − 1`.

### Sinh TOC hàng loạt cho cả cây thư mục (`batch_toc.py`)

Khi có **nhiều sách xếp theo lớp**, thay vì chạy từng file, trỏ `batch_toc.py`
vào thư mục gốc. Nó quét đệ quy mọi `*.pdf` và sinh ra **một cây thư mục TOC
tương ứng** (giữ nguyên cấu trúc), mỗi sách một file `01_toc.json`:

```
pdf/                          tocs/
  lop6/                         lop6/
    khtn.pdf        ─────►         khtn.toc.json
    lich-su.pdf                    lich-su.toc.json
  lop7/                         lop7/
    toan.pdf                      toan.toc.json
```

```bash
python3 batch_toc.py pdf                    # gemini (cần GEMINI_API_KEY)
python3 batch_toc.py pdf --dry-run          # test KHÔNG cần API key (mock AI)
python3 batch_toc.py pdf --backend claude   # dùng subscription Claude
python3 batch_toc.py pdf --out tocs --also-txt --overwrite
```

- Nguồn mục lục theo đúng quy tắc `main.py`: PDF **có bookmark** → thuần code
  0 token; **không có** → AI (Gemini/Claude) suy ra. Client AI chỉ khởi tạo khi
  thực sự có sách thiếu bookmark, nên bộ sách toàn bookmark chạy **0 token**.
- Mặc định **resume + validate**: file TOC đã có được **kiểm tra hợp lệ** (đúng
  shape `01_toc.json`, có topic) rồi mới bỏ qua; file rỗng/hỏng do lần trước đứt
  giữa chừng sẽ **tự sinh lại**. Dùng `--overwrite` để ép sinh lại tất cả. Một
  file lỗi **không** làm dừng cả lô — cuối cùng in bảng tổng kết
  (đã sinh / bỏ qua / lỗi) và thoát mã `1` nếu có lỗi.
- Mỗi file `*.toc.json` dùng thẳng được cho pipeline:
  `python3 main.py pdf/lop6/khtn.pdf --level "Lớp 6" --toc-file tocs/lop6/khtn.toc.json`.
- `--also-txt` ghi kèm bản `.toc.txt` (định dạng `build_toc.py`, offset 0) để
  soát/sửa tay khi cần.

Bộ cờ dùng chung với `main.py`: `--backend {gemini,claude}`, `--model`,
`--interval`, `--force-ai-toc`, `--dry-run`; thêm `--out`, `--suffix`,
`--also-txt`, `--overwrite`.

---

## Dùng Claude thay cho Google API (backend claude)

Thay vì gọi REST API của Gemini (tính hạn mức theo token), backend này gọi
**Claude Code CLI** ngay trên máy bằng đúng phiên đăng nhập Claude Max/Pro của bạn.
Mọi stage AI (content, câu hỏi, review, OCR mục lục) đều đi qua `claude -p` —
**0đ phụ trội, không tính token, chỉ trừ vào hạn mức subscription**.

### Điều kiện

```bash
claude login          # đăng nhập gói Max/Pro
claude -p "xin chào"  # thử: trả lời được là OK
```

Nếu `claude` không có trong PATH, tool cảnh báo ngay khi khởi động. **Không cần**
`GEMINI_API_KEY` (và không cần key reviewer Groq/OpenRouter).

### Chạy

```bash
# Mặc định model sonnet:
python3 main.py sach.pdf --level "Lớp 6" --backend claude

# Đổi model (opus mạnh hơn, tốn hạn mức hơn):
python3 main.py sach.pdf --level "Lớp 6" --backend claude --model opus

# Review chéo model (reviewer tự dùng model KHÁC — xem dưới):
python3 main.py sach.pdf --level "Lớp 6" --backend claude --review
```

> `--model` mặc định là `gemini-2.5-flash`. Khi bật `--backend claude`, nếu `--model`
> vẫn là giá trị Gemini thì tool **tự đổi sang `sonnet`**. Truyền `sonnet`/`opus`
> để chỉ định rõ.

### Cơ chế hoạt động (bên trong)

- **Cùng interface với `gemini.Gemini`** (`generate_json` / `generate_text` /
  `pdf_part` / `image_part`), nên các stage KHÔNG phải sửa gì — chỉ thay client.
- Mỗi lời gọi AI = **1 lần shell ra**:
  `claude -p "<prompt>" --output-format json --model <model> --allowedTools Read --add-dir <tmp>`.
- **PDF/ảnh KHÔNG nhúng vào prompt**: chúng được ghi ra file tạm, prompt chỉ chứa
  đường dẫn + yêu cầu Claude **đọc bằng công cụ `Read`** (Read hỗ trợ cả PDF lẫn
  ảnh). Nhờ vậy prompt luôn nhỏ, không đụng giới hạn độ dài dòng lệnh.
- **Ép JSON**: các stage cần structured output kèm schema + yêu cầu "trả về DUY
  NHẤT JSON". Output lỡ không parse được → tool **tự sửa 1 lần** rồi mới báo lỗi.
- **Retry**: lỗi tạm thời retry tối đa 4 lần (backoff 5s→60s). Riêng lỗi **hết
  hạn mức** thì không retry — nhường cho cơ chế resume.

### Reviewer khi dùng Claude

Bật `--review` với backend claude thì reviewer là **một model Claude KHÁC**
(cross-model): content sinh bằng `sonnet` → reviewer dùng `opus` (và ngược lại),
đọc được **PDF gốc** qua `Read` để đối chiếu. Lúc này cờ `--reviewer`
(groq/openrouter/gemini-pro) bị bỏ qua — không cần key ngoài.

### Hết hạn mức → tự dừng & resume

Khi CLI báo hết hạn mức (usage/rate limit, "resets at", 429…), tool **export ngay
phần các topic đã hoàn chỉnh** (partial) rồi **thoát mã 42** (để runner tự động
phân biệt "tạm dừng chờ reset" với hoàn tất `0` / lỗi thật `1`). **Resume**: khi
cửa sổ hạn mức reset, chạy lại **đúng lệnh cũ** — topic đã xong bị bỏ qua.

### Lưu ý riêng của backend claude

- **Mục lục**: nên dùng bookmark PDF hoặc `--toc-file` (dựng sẵn) thay vì để AI đọc
  cả cuốn suy ra mục lục — vừa chính xác 100%, vừa tránh cho Claude Read cả PDF dài.
- **Báo cáo token vẫn in** (lấy từ `usage` của CLI) để theo dõi mức tiêu thụ, nhưng
  **bạn không bị tính tiền theo token** — chỉ là số liệu tham khảo.
- Chạy **local/Cowork trên máy có Claude Code**; không dùng được trong CI không cài `claude`.

---

## Toàn bộ options

### Đầu vào & định danh

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `pdf` | — | (bắt buộc) đường dẫn file PDF cần xử lý |
| `--level "Lớp 6"` | `Lớp 6` | giá trị cột `level` trong `topics.csv` |
| `--subject "..."` | rỗng | tên môn học ghi vào JSON bài học (vd `"Lịch sử và Địa lí"`) |
| `--grade "6"` | tự suy từ `--level` | khối lớp ghi vào JSON (vd `"Lớp 6"` → `"6"`) |

### Nguồn AI & tốc độ

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--backend gemini\|claude` | `gemini` | nguồn AI: `gemini` (REST API, cần `GEMINI_API_KEY`) hoặc `claude` (Claude Code CLI `claude -p`, dùng **subscription** Max/Pro, không cần key, không tính token; hết hạn mức → thoát mã 42, chạy lại để resume) |
| `--model NAME` | `gemini-2.5-flash` | model content/questions. Với `--backend claude`: giá trị Gemini tự đổi sang `sonnet`; truyền `sonnet`/`opus` để chỉ định rõ |
| `--interval SEC` | `6.0` | giây nghỉ giữa 2 request (free tier ~10 RPM → 6s; 429 "theo phút" thì tăng lên 15) |
| `--dry-run` | tắt | dùng MockGemini, **không cần API key** — kiểm tra pipeline & format output |

### Kiểm soát khối lượng & tốc độ (tiết kiệm quota)

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--limit N` | `0` (làm hết) | CHỈ xử lý **N bài đầu** rồi export luôn — test nhanh bài 1–2. Cache giữ nguyên: bỏ cờ này chạy lại sẽ làm tiếp phần còn lại |
| `--no-images` | tắt | bỏ stage ảnh cho nhẹ; lấy ảnh sau bằng cách chạy lại bỏ cờ này |
| `--no-validate` | tắt | bỏ pass tự giải kiểm chứng đáp án (nhanh hơn, **không khuyến nghị**) |
| `--dpi N` | `0` (tắt) | nén trang PDF **scan** độ phân giải cao về N dpi grayscale trước khi gửi → giảm token mạnh (khuyến nghị `110`). Có guard chống upscale: scan đã nhỏ thì tự giữ nguyên |

### Hình minh hoạ

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| *(mặc định)* | — | chỉ vẽ **mindmap SVG** bằng code từ Learning Object (**0 token**, gọn giao diện) |
| `--book-images` | tắt | đính thêm **NGUYÊN TRANG sách** (không cắt hình) — **0 token, thuần code**: render từng trang trong page range ra PNG rồi **gắn mỗi trang vào đúng mục nội dung** (khớp text trang với heading/points; sách scan không có text → ánh xạ theo thứ tự trang). Kết hợp `--dpi N` để render grayscale gọn cho sách scan |

### Định dạng & độ dài đầu ra (đổi qua lại **0 token** — chỉ re-render từ cache)

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--density LEVEL` | `full` | mật độ chữ cột content: `full` (đủ) / `compact` (≤3 point/mục, cắt point dài) / `minimal` (chỉ mục tiêu + nội dung chính + mindmap) |
| `--content-format FMT` | `markdown` | định dạng cột `content`: `markdown` (render bằng code) hoặc `json` (Learning Object thô, nhúng quiz + mindmap) |
| `--export-json` | tắt | ghi thêm `output/json/{topic_slug}.json` theo format đích (nhúng quiz, mindmap_mermaid) |

### Mục lục (TOC)

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--toc-file PATH` | — | dùng `01_toc.json` dựng sẵn (từ `build_toc.py`/`toc_from_images.py`) thay cho bookmark/AI — **0 token, chính xác 100%** |
| `--force-ai-toc` | tắt | bỏ qua bookmark PDF, luôn dùng AI trích mục lục |
| `--yes` | tắt | bỏ bước dừng-xác-nhận mục lục (cần cho môi trường không có TTY: Colab/CI) |

### Sinh lại có chọn lọc (cache-aware)

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--redo-from N` | — | xoá cache **stage N→7** rồi sinh lại (vd `5` = sinh lại câu hỏi; `≤5` reset đánh số batch; `≤4` xoá luôn ảnh) |
| `--redo-content` | tắt | sinh **LẠI content** (stage 3, gọi AI) + ảnh mindmap (stage 4), NHƯNG **giữ nguyên câu hỏi** (stage 5) + review (stage 6) đã có — 0 token cho câu hỏi. Dùng khi chỉ muốn làm mới bài học mà không đụng bộ câu hỏi đã duyệt |

### Thẩm định chéo (cross-model review)

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--review` | tắt | bật stage 6: model thứ hai thẩm định content + câu hỏi → `review_report.md` |
| `--reviewer X` | `groq` | (chỉ backend gemini) `groq` (Llama 3.3 70B, độc lập nhà cung cấp) / `openrouter` (DeepSeek R1 free) / `gemini-pro` (**duy nhất đối chiếu được PDF gốc**). Với `--backend claude`: bị bỏ qua, reviewer là model Claude khác (sonnet↔opus) |
| `--review-fix` | tắt | tự loại câu hỏi bị review đánh `severity=high` (mặc định chỉ báo cáo, không tự xoá) |

**Biến môi trường:** `GEMINI_API_KEY` (backend gemini, bắt buộc trừ `--dry-run`;
**không** cần cho backend claude); `GROQ_API_KEY` / `OPENROUTER_API_KEY` (chỉ khi
dùng reviewer tương ứng). Có thể đặt trong file `.env` (chép từ `env.example`).

---

## Kết quả (`runs/<tên-pdf>/output/`)

```
output/
├── topics.csv        # snapshot TÍCH LUỸ đầy đủ — dùng cho lần import chính thức
├── multichoice.csv   #   (UTF-8 BOM, đúng cột template; ảnh tham chiếu bằng filename trần)
├── images/           # TẤT CẢ ảnh: {topic_slug}_{nn}.png|svg — upload riêng vào hệ thống
├── manifest.json     # bản đồ topic → ảnh → caption → nguồn + warnings + quality checks
├── json/             # (nếu --export-json) 1 file Learning Object / topic theo format đích
├── review_report.md  # (nếu --review) báo cáo thẩm định — ĐỌC TRƯỚC KHI IMPORT
├── batch-01/         # DELTA: chỉ các topic hoàn chỉnh trong lần chạy 1 (topics/mc/images/manifest)
├── batch-02/         # chỉ topic MỚI của lần chạy tiếp (sau khi hết quota, resume...)
└── ...
```

**Batch để test từng lô, snapshot gốc để ship.** File batch cũ bất biến; chạy lại
mà không có topic mới hoàn chỉnh thì không sinh batch mới.

---

## Pipeline (topic-major)

Kết quả trung gian mỗi stage lưu ở `runs/<tên-pdf>/work/`:

```
1. TOC        bookmark PDF (0 token) / AI đọc PDF / --toc-file dựng sẵn   → work/01_toc.json
2. Structure  slug + order sinh bằng code (deterministic)                 → work/02_structure.json
─ vòng lặp trọn gói từng topic ─
3. Content    Learning Object JSON (objectives/sections/mindmap/…)        → work/03_content.json
4. Images     đính nguyên trang sách + vẽ mindmap SVG (0 token)           → work/04_images.json + output/images/
5. Questions  MCQ bám key_points (coverage) + pass tự giải kiểm chứng     → work/05_questions.json
6. Review     (--review) model thứ 2 thẩm định content + câu hỏi          → work/06_review.json
─ hết vòng lặp ─
7. Export     batch delta + snapshot full + quality checks                → output/
```

Content là **Learning Object có cấu trúc** (không phải blob markdown): AI chỉ trả
DỮ LIỆU (`objectives`, `hook`, `key_terms`, `sections`, `real_life`, `mindmap`,
`hook_answer`, `key_points`), cú pháp markdown/SVG do code sinh → đổi
`--density`/`--content-format` không tốn token. Chống hallucination: chỉ gửi
đúng các trang của topic (cắt sub-PDF theo page range) và tách rõ field phải bám
tài liệu vs field được bổ sung.

> Đổi schema ⇒ cache `03_content.json` đời cũ (còn `misconceptions`/`memory_hooks`)
> hết hợp lệ; tool sẽ báo và yêu cầu chạy lại với `--redo-from 3`.

---

## Báo cáo token (luôn bật)

Cuối mỗi phiên in bảng token theo tag (`content`/`questions`/`validate`/`review`/…),
phiên này + cộng dồn; chi tiết ở `work/usage.json`. Dùng nó để tối ưu **bằng số
liệu**: so tổng token trước/sau khi bật `--no-images`, hay xem `validate` chiếm
bao nhiêu % trước khi cân nhắc bỏ. (Backend claude vẫn in bảng này để tham khảo,
dù không bị tính tiền theo token.)

## Quality checks thuần code (luôn bật, 0 token)

Chạy trên toàn bộ câu hỏi mỗi lần export, ghi ra console + `manifest.json`:

- **Thiên vị vị trí đáp án**: 1 chữ cái chiếm >40% (kỳ vọng 25%) → cảnh báo.
- **Đáp án đúng luôn dài nhất** (>60% số câu) → người làm đoán được không cần học.
- **Phương án trùng nhau** trong cùng câu; **thiếu giải thích**.
- **Câu hỏi gần-trùng-lặp** giữa các topic (similarity ≥ 0.92).

---

## Troubleshooting

- **"HẾT QUOTA NGÀY" (Gemini)**: chạy lại chính lệnh cũ sau ~14–15h chiều giờ VN — resume tự lo.
- **429 kèm hint "theo PHÚT"**: tăng `--interval 15`.
- **Backend claude hết hạn mức (thoát mã 42)**: bình thường — đã export phần hoàn
  chỉnh. Chờ cửa sổ subscription reset rồi chạy lại **đúng lệnh cũ** để resume.
- **`Không tìm thấy lệnh claude trong PATH`**: cài Claude Code + `claude login`
  (Max/Pro) trước khi dùng `--backend claude`.
- **Mục lục sai / page range lệch**: sửa `work/01_toc.json` → `--redo-from 2`
  (hoặc dựng lại bằng `build_toc.py` + `--toc-file`).
- **Cache content phiên bản cũ**: tool báo và yêu cầu `--redo-from 3`.
- **Tiếng Việt vỡ trong Excel**: file có UTF-8 BOM; nếu vẫn vỡ dùng Data → From Text/CSV → UTF-8.
- **Reviewer lỗi/hết quota**: chạy lại — topic đã review được bỏ qua; đổi
  `--reviewer` khác cũng được.
- **Chạy trên Colab/CI (không có TTY)**: thêm `--yes` để bỏ bước dừng xác nhận mục lục.

## Lưu ý dữ liệu

Free tier của Google **có thể dùng dữ liệu gửi lên để cải thiện model** — không
dùng cho tài liệu nội bộ/nhạy cảm. Khi cần: paid tier, dùng **`--backend claude`**
(gửi qua phiên Claude Code của bạn), hoặc self-host (viết thêm client cùng
interface trong `gemini.py`).

---

## Vận hành từ xa qua Cowork + Claude app

Thả PDF vào Google Drive từ điện thoại → nhắn cho phiên Cowork trên Mac ở nhà →
agent chạy `main.py`, theo dõi log, trả `output/` về Drive.

```
[Điện thoại: thả PDF vào Google Drive]
        │  (folder đồng bộ về Mac)
[Claude app trên điện thoại] ──remote──> [Cowork trên Mac ở nhà]
        │                                      │ đọc COWORK_GUIDE.md
        │                                      │ chạy main.py, theo dõi log
        └── nhận thông báo xong <────── copy output/ vào folder Drive
```

### Giai đoạn 1 — Chuẩn bị Mac ở nhà (làm 1 lần, ~15 phút)

- **Chống ngủ.** Máy ngủ = mọi thứ chết. System Settings → Displays → Advanced →
  *Prevent automatic sleeping on power adapter when the display is off*: ON. Cắm
  sạc thường trực.
- **API key phải "sống" trong mọi shell.** Cowork mở shell mới để chạy lệnh,
  `export` tạm trong terminal cũ không còn tác dụng. Ghi vào profile:

  ```bash
  echo 'export GEMINI_API_KEY=AIza...' >> ~/.zshrc
  source ~/.zshrc
  echo $GEMINI_API_KEY   # phải in ra key
  ```

  (Dùng `--backend claude` thì bỏ qua bước này — chỉ cần đã `claude login`.)

- **Tạo cấu trúc vào/ra qua Google Drive.** Cài Google Drive for desktop rồi:

  ```bash
  mkdir -p ~/Google\ Drive/My\ Drive/pdf2learn-inbox
  mkdir -p ~/Google\ Drive/My\ Drive/pdf2learn-outbox
  # Đường dẫn thật có thể là ~/Library/CloudStorage/GoogleDrive-<email>/My Drive/...
  # tuỳ bản Drive — chạy: ls ~/Library/CloudStorage/ để xác định và dùng nhất quán.
  ```

- **Viết file hướng dẫn cho agent** — trái tim của cả flow. Tạo
  `~/Documents/pdf2learn/COWORK_GUIDE.md`:

  ```markdown
  # Vận hành pdf2learn (PDF -> topics.csv + multichoice.csv)

  ## Đường dẫn
  - Project: ~/Documents/pdf2learn
  - PDF đầu vào: <đường dẫn Drive>/pdf2learn-inbox/
  - Kết quả trả về: <đường dẫn Drive>/pdf2learn-outbox/

  ## Quy trình chuẩn khi được yêu cầu "xử lý file X.pdf"
  1. Copy file từ inbox vào thư mục project.
  2. Chạy:
     cd ~/Documents/pdf2learn
     source .venv/bin/activate
     python3 main.py X.pdf --level "Lớp 6"
  3. Theo dõi output. Tool tự resume: nếu bị ngắt / HTTP 429 kéo dài,
     chờ 2 phút rồi chạy LẠI CHÍNH LỆNH ĐÓ (topic đã xong sẽ bỏ qua).
  4. Khi hoàn tất: nén runs/X/output/ thành X-package.zip, copy vào pdf2learn-outbox/.
  5. Báo cáo: số topics, số câu hỏi, "warnings" trong runs/X/output/manifest.json,
     và các câu bị loại (_dropped) trong runs/X/work/05_questions.json nếu có.

  ## Quy tắc an toàn
  - KHÔNG sửa code, không xoá runs/ trừ khi được yêu cầu rõ ("xoá cache", "làm lại từ đầu").
  - KHÔNG chạy --dry-run cho yêu cầu xử lý thật.
  - Nếu Stage 1-2 in mục lục ra: DỪNG LẠI, gửi danh sách topic cho tôi duyệt
    trước khi chạy tiếp (trừ khi tôi nói "chạy thẳng").
  ```

  Dòng cuối chủ động thiết kế **human-in-the-loop** vào đúng chỗ rủi ro nhất:
  mục lục sai → hàng trăm request đổ sông. Bạn duyệt mục lục từ điện thoại rồi mới
  cho chạy tiếp.

- **Chạy tay 1 lần để nghiệm thu.** Tự chạy đúng chuỗi lệnh trong guide từ đầu
  đến cuối. Đừng bao giờ giao cho agent một quy trình mà chính mình chưa chạy
  thành công — lỗi môi trường phải diệt sạch trước.

### Giai đoạn 2 — Cài Cowork và kết nối tài khoản

- Tải Claude desktop/Cowork từ trang chính thức của Anthropic, đăng nhập cùng tài
  khoản với Claude app trên điện thoại. ⚠️ Cowork có thể yêu cầu gói trả phí —
  xác nhận tại support.claude.com.
- Khi Cowork hỏi quyền truy cập thư mục, chỉ cấp đúng **3 thư mục**: project +
  inbox + outbox. Không cấp cả Home (least privilege — Cowork chạy lệnh thật).
- Mở một phiên Cowork, yêu cầu nó đọc `COWORK_GUIDE.md` và chạy thử end-to-end với
  1 PDF nhỏ ngay tại máy (bạn ngồi xem) — quan sát nó có dừng chờ duyệt mục lục không.
- ⚠️ Bật/kiểm tra khả năng truy cập từ xa của phiên Cowork qua Claude mobile app
  (chi tiết hỏi trực tiếp trong app hoặc xem support.claude.com).

### Giai đoạn 3 — Vòng lặp sử dụng từ xa

Từ bất kỳ đâu:

1. Điện thoại: mở app Google Drive → upload PDF vào `pdf2learn-inbox`.
2. Mở Claude app → vào phiên Cowork trên máy nhà → nhắn:
   *"Có file lsdl-lop6.pdf mới trong inbox, xử lý theo COWORK_GUIDE.md"*.
