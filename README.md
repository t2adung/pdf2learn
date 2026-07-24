# pdf2learn — PDF → Learning Package (topics.csv + multichoice.csv)

Pipeline AI: đọc PDF giáo trình (kể cả PDF **scan**) → chia module/topic → soạn bài
học Markdown kèm ảnh **sơ đồ tư duy (mindmap)** → sinh câu hỏi trắc nghiệm phủ hết
kiến thức → export đúng template import (`topics.csv`, `multichoice.csv`) + `images/` +
`manifest.json`, kèm cross-model review, quality checks và báo cáo token.

AI chính: **Google Gemini API free tier** (đọc PDF native, structured output).
Reviewer (tuỳ chọn): Groq / OpenRouter / Gemini Pro.

> **Nội dung** xuất ra Markdown (`.md`) — bibeli render bằng markdown-it/marked.
> **Ảnh minh hoạ** là 1 sơ đồ tư duy `.svg` vẽ THUẦN CODE cho mỗi topic (0 token,
> 0 dependency ngoài). Pipeline KHÔNG sinh file HTML — phần hiển thị sinh động do
> bibeli tự dựng bằng HTML ở phía frontend.

## Yêu cầu

- Python **3.9+** (khuyến nghị 3.12+)
- `pip install -r requirements.txt` — chỉ 3 gói: pymupdf + requests + python-dotenv.
  Ảnh mindmap vẽ bằng code (SVG), KHÔNG cần Playwright/Chromium hay dependency ngoài.
- API key miễn phí: https://aistudio.google.com → `export GEMINI_API_KEY=AIza...`

## Bắt đầu nhanh

```bash
# 1. Test pipeline KHÔNG cần API key (mock AI) — nên chạy đầu tiên:
python main.py sach.pdf --dry-run

# 2. Test với AI thật nhưng CHỈ 3 topic — xem chất lượng/format thật trước
#    khi tốn token cho cả sách:
python main.py sach.pdf --level "Lớp 6" --limit 3

# 3. Ưng ý -> bỏ --limit, chạy tiếp phần còn lại (resume, không sinh lại 3
#    topic đã test ở bước 2):
python main.py sach.pdf --level "Lớp 6"

# 4. Tiết kiệm quota (khuyến nghị cho sách dài, free tier):
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
├── images/           # ảnh mindmap {topic_slug}_mindmap.svg (+ ảnh PDF nếu --book-images) — upload riêng
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
3. Content    Markdown bài học + key_points + mindmap (AI, chunk) → work/03_content.json
4. Images     vẽ mindmap SVG bằng code (0 token) [+ ảnh PDF nếu --book-images] → output/images/
5. Questions  MCQ theo key_points (coverage) + validation     → work/05_questions.json
6. Review     (--review) model thứ 2 thẩm định                → work/06_review.json
─ hết vòng lặp ─
7. Export     batch delta + snapshot full + quality checks    → output/
```

**Resume mặc định**: đứt giữa chừng → chạy lại lệnh cũ; topic hoàn chỉnh bỏ
qua, topic dở dang chạy tiếp đúng bước thiếu. Gặp lỗi hết quota ngày: tool báo
rõ, export partial rồi thoát — quota reset ~14-15h chiều giờ VN.

## Câu lệnh đầy đủ (mọi option)

Cú pháp: `python main.py <file.pdf> [options]`. Chỉ `<file.pdf>` là bắt buộc;
mọi option đều có mặc định hợp lý (chạy trơn chỉ với `--level`). Bản tham chiếu
đầy đủ — copy về rồi bỏ bớt cờ không cần:

```bash
python main.py sach.pdf \
  --level "Lớp 6" \            # giá trị cột level (mặc định "Lớp 6")
  --subject "Khoa học tự nhiên" \  # tên môn, chỉ ghi vào JSON (--export-json / --content-format json)
  --grade 6 \                 # khối lớp ghi vào JSON (mặc định tự rút số từ --level)
  --density full \            # mật độ chữ cột content: full | compact | minimal (0 token, chỉ re-render)
  --content-format markdown \ # cột content: markdown (mặc định) | json (Learning Object thô, nhúng quiz)
  --export-json \             # ghi thêm output/json/{slug}.json theo format đích (0 token)
  --model gemini-2.5-flash \  # model Gemini (mặc định gemini-2.5-flash)
  --interval 6 \              # giây giữa 2 request (free tier ~10 RPM -> 6s)
  --dpi 0 \                   # nén trang scan HD về N dpi gray trước khi gửi (0=tắt; scan nên 110)
  --limit 0 \                 # chỉ xử lý N topic đầu rồi export (0=cả sách); test nhanh trước khi chạy full
  --no-images \               # bỏ hẳn stage 4 (không ảnh nào)
  --no-mindmap \              # bật stage 4 nhưng KHÔNG vẽ mindmap (chỉ có ý nghĩa khi kèm --book-images)
  --book-images \             # trích THÊM ảnh gốc từ PDF + AI lọc (+1 request/topic)
  --no-validate \             # bỏ pass tự giải kiểm chứng đáp án (không khuyến nghị)
  --fused \                   # sinh content + câu hỏi trong 1 request/topic (~50% request, xem trade-off)
  --review \                  # bật stage 6: model thứ 2 thẩm định content + câu hỏi
  --reviewer groq \           # groq (Llama 70B, mặc định) | openrouter (DeepSeek R1) | gemini-pro (đọc được PDF)
  --review-fix \              # tự loại câu hỏi bị review đánh severity=high (mặc định chỉ báo cáo)
  --force-ai-toc \            # bỏ qua bookmark PDF, luôn dùng AI trích mục lục
  --toc-file work/01_toc.json \ # dùng file TOC dựng sẵn (build_toc.py / toc_from_images.py) — 0 token
  --yes \                     # bỏ bước xác nhận mục lục trước khi gọi AI (CI/Colab)
  --dry-run                   # MockGemini, không cần API key — test pipeline & format output
```

Các cờ "sinh lại" (không đổi số liệu, chỉ xoá cache có chọn lọc rồi chạy lại):

```bash
python main.py sach.pdf --redo-content   # chỉ sinh lại content (stage 3), giữ ảnh/câu hỏi
python main.py sach.pdf --redo-images    # chỉ sinh lại ảnh (stage 4), giữ content/câu hỏi
python main.py sach.pdf --redo-from 5    # xoá cache stage 5→7 rồi sinh lại (vd sinh lại câu hỏi)
```

## Bảng tra nhanh options

| Flag | Mặc định | Ý nghĩa |
|---|---|---|
| `--level "Lớp 6"` | `"Lớp 6"` | Giá trị cột `level` |
| `--subject X` | `""` | Tên môn học, chỉ ghi vào JSON bài học |
| `--grade N` | tự rút từ `--level` | Khối lớp ghi vào JSON (`"Lớp 6"` → `6`) |
| `--density X` | `full` | Mật độ chữ cột content: `full` \| `compact` (3 point/mục) \| `minimal` (rút gọn). Đổi mức 0 token — chỉ re-render |
| `--content-format X` | `markdown` | Cột content: `markdown` (render bằng code) \| `json` (Learning Object thô, nhúng quiz) |
| `--export-json` | tắt | Ghi thêm `output/json/{slug}.json` theo format đích (0 token) |
| `--dry-run` | tắt | MockGemini, không cần API key — kiểm tra pipeline & format |
| `--limit N` | `0` (cả sách) | Chỉ xử lý N topic đầu rồi export — test chất lượng/format với AI thật; bỏ cờ ở lần sau để resume |
| `--no-images` | tắt | Bỏ stage ảnh hoàn toàn; lấy ảnh sau bằng cách chạy lại bỏ cờ này |
| `--no-mindmap` | tắt (mindmap BẬT) | Không vẽ mindmap SVG. Ảnh chính của topic là mindmap (vẽ bằng code, 0 token, 0 dependency) nên chỉ nên dùng cờ này khi đã có `--book-images` |
| `--book-images` | tắt | Trích THÊM ảnh gốc từ trang PDF + AI lọc (+1 request/topic), liệt kê riêng, tách khỏi mindmap |
| `--redo-images` | tắt | Chỉ xoá cache + thư mục ảnh (stage 4) rồi sinh lại — giữ nguyên content/câu hỏi |
| `--redo-content` | tắt | Chỉ xoá cache content (stage 3) rồi sinh lại — giữ nguyên câu hỏi/ảnh. Dùng thay `--redo-from 3` khi câu hỏi cũ vẫn dùng được (có thể lệch coverage nếu content đổi nhiều) |
| `--redo-from N` | `99` (tắt) | Xoá cache stage N→7 rồi sinh lại (vd `5`: sinh lại câu hỏi; ≤5 reset đánh số batch) |
| `--no-validate` | tắt | Bỏ pass tự giải kiểm chứng đáp án (không khuyến nghị) |
| `--fused` | tắt | Sinh content + câu hỏi trong 1 request/topic (~50% request stage 3+5) |
| `--review` | tắt | Bật stage 6: model thứ hai thẩm định content + câu hỏi |
| `--reviewer X` | `groq` | `groq` (Llama 70B, độc lập nhà cung cấp) \| `openrouter` (DeepSeek R1) \| `gemini-pro` (duy nhất đối chiếu được PDF gốc) |
| `--review-fix` | tắt | Tự loại câu hỏi bị review đánh `severity=high` (mặc định chỉ báo cáo) |
| `--force-ai-toc` | tắt | Bỏ qua bookmark PDF, luôn dùng AI trích mục lục |
| `--toc-file F` | — | Dùng file `01_toc.json` dựng sẵn (build_toc.py / toc_from_images.py) — 0 token, chính xác 100% |
| `--yes` | tắt | Bỏ bước xác nhận mục lục trước khi gọi AI (dùng cho CI/Colab không có TTY) |
| `--dpi N` | `0` (tắt) | Nén trang scan độ phân giải CAO về N dpi gray (có guard chống upscale) |
| `--model X` | `gemini-2.5-flash` | Model Gemini |
| `--interval S` | `6` | Giây giữa 2 request (≈ 10 RPM free tier) |

Biến môi trường: `GEMINI_API_KEY` (bắt buộc trừ `--dry-run`), `GROQ_API_KEY` /
`OPENROUTER_API_KEY` (theo `--reviewer`).

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

## Notes
```
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r pdf2learn/requirements.txt
EXPORT GEMINI_API_KEY=

export GROQ_API_KEY=gsk_...          # free: https://console.groq.com
python3 main.py sach.pdf --level "Lớp 6" --review

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
