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
- export đúng template: `topics.csv`, `multichoice.csv`, `images/`, `manifest.json`.

AI chính: **Google Gemini API (free tier)** — đọc PDF native, structured output.
Reviewer (tuỳ chọn): **Groq / OpenRouter / Gemini Pro**.

> **Điểm cốt lõi để tiết kiệm quota:** mọi khâu *định dạng* (render markdown, vẽ
> mindmap SVG, đính trang sách, đổi độ dài/format, dựng TOC từ file có sẵn) đều
> chạy **bằng code — 0 token**. AI chỉ dùng cho phần *nội dung* (soạn bài, ra đề,
> review). Nhờ đó đổi layout/độ dài/format chỉ cần chạy lại, không gọi lại AI.

---

## Yêu cầu & cài đặt

- Python **3.9+** (khuyến nghị 3.12+).
- API key miễn phí Gemini: https://aistudio.google.com

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # pymupdf + requests + python-dotenv
```

Đặt API key theo 1 trong 2 cách:

```bash
# Cách A — biến môi trường:
export GEMINI_API_KEY=AIza...

# Cách B — file .env (tiện chạy local, tự nạp nhờ python-dotenv):
cp env.example .env      # rồi dán key thật vào .env
```

Reviewer chỉ cần thêm key khi dùng `--review`:

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

### Mục lục chính xác 100% từ file có sẵn (0 token)

Với sách scan / bookmark rác, thay vì để AI đoán mục lục, hãy dựng TOC bằng code:

```bash
# A) Gõ tay mục lục ra .txt rồi dựng JSON (xem cách tính --offset trong build_toc.py):
python3 build_toc.py sach.toc.txt --offset 2 --last-page 197 \
    --out runs/sach/work/01_toc.json

# B) OCR ảnh/PDF trang mục lục -> toc.txt (kiểm tra tay) -> JSON:
python3 toc_from_images.py toc_images/sach --out sach.toc.txt        # 1 request OCR
python3 build_toc.py sach.toc.txt --offset 2 --last-page 197 --out runs/sach/work/01_toc.json

# rồi trỏ pipeline vào file đã dựng:
python3 main.py sach.pdf --toc-file runs/sach/work/01_toc.json --level "Lớp 6"
```

---

## Toàn bộ options

### Đầu vào & định danh

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `pdf` | — | (bắt buộc) đường dẫn file PDF cần xử lý |
| `--level "Lớp 6"` | `Lớp 6` | giá trị cột `level` trong `topics.csv` |
| `--subject "..."` | rỗng | tên môn học ghi vào JSON bài học (vd `"Lịch sử và Địa lí"`) |
| `--grade "6"` | tự suy từ `--level` | khối lớp ghi vào JSON (vd `"Lớp 6"` → `"6"`) |

### Kiểm soát khối lượng & tốc độ (tiết kiệm quota)

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--limit N` | `0` (làm hết) | CHỈ xử lý **N bài đầu** rồi export luôn — test nhanh bài 1–2. Cache giữ nguyên: bỏ cờ này chạy lại sẽ làm tiếp phần còn lại |
| `--dry-run` | tắt | dùng MockGemini, **không cần API key** — kiểm tra pipeline & format output |
| `--no-images` | tắt | bỏ stage ảnh cho nhẹ; lấy ảnh sau bằng cách chạy lại bỏ cờ này |
| `--no-validate` | tắt | bỏ pass tự giải kiểm chứng đáp án (nhanh hơn, **không khuyến nghị**) |
| `--interval SEC` | `6.0` | giây nghỉ giữa 2 request (free tier ~10 RPM → 6s; 429 "theo phút" thì tăng lên 15) |
| `--dpi N` | `0` (tắt) | nén trang PDF **scan** độ phân giải cao về N dpi grayscale trước khi gửi → giảm token mạnh (khuyến nghị `110`). Có guard chống upscale: scan đã nhỏ thì tự giữ nguyên |
| `--model NAME` | `gemini-2.5-flash` | model Gemini dùng cho content/questions |

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
| `--reviewer X` | `groq` | `groq` (Llama 3.3 70B, độc lập nhà cung cấp) / `openrouter` (DeepSeek R1 free) / `gemini-pro` (**duy nhất đối chiếu được PDF gốc** để kiểm faithfulness) |
| `--review-fix` | tắt | tự loại câu hỏi bị review đánh `severity=high` (mặc định chỉ báo cáo, không tự xoá) |

**Biến môi trường:** `GEMINI_API_KEY` (bắt buộc trừ `--dry-run`);
`GROQ_API_KEY` / `OPENROUTER_API_KEY` (chỉ khi dùng reviewer tương ứng).

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
bao nhiêu % trước khi cân nhắc bỏ.

## Quality checks thuần code (luôn bật, 0 token)

Chạy trên toàn bộ câu hỏi mỗi lần export, ghi ra console + `manifest.json`:

- **Thiên vị vị trí đáp án**: 1 chữ cái chiếm >40% (kỳ vọng 25%) → cảnh báo.
- **Đáp án đúng luôn dài nhất** (>60% số câu) → người làm đoán được không cần học.
- **Phương án trùng nhau** trong cùng câu; **thiếu giải thích**.
- **Câu hỏi gần-trùng-lặp** giữa các topic (similarity ≥ 0.92).

---

## Troubleshooting

- **"HẾT QUOTA NGÀY"**: chạy lại chính lệnh cũ sau ~14–15h chiều giờ VN — resume tự lo.
- **429 kèm hint "theo PHÚT"**: tăng `--interval 15`.
- **Mục lục sai / page range lệch**: sửa `work/01_toc.json` → `--redo-from 2`
  (hoặc dựng lại bằng `build_toc.py` + `--toc-file`).
- **Cache content phiên bản cũ**: tool báo và yêu cầu `--redo-from 3`.
- **Tiếng Việt vỡ trong Excel**: file có UTF-8 BOM; nếu vẫn vỡ dùng Data → From Text/CSV → UTF-8.
- **Reviewer lỗi/hết quota**: chạy lại — topic đã review được bỏ qua; đổi
  `--reviewer` khác cũng được.
- **Chạy trên Colab/CI (không có TTY)**: thêm `--yes` để bỏ bước dừng xác nhận mục lục.

## Lưu ý dữ liệu

Free tier của Google **có thể dùng dữ liệu gửi lên để cải thiện model** — không
dùng cho tài liệu nội bộ/nhạy cảm. Khi cần: paid tier hoặc self-host (viết thêm
client cùng interface trong `gemini.py`).

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
