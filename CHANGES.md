# pdf2learn v2 — Content chuyển từ Markdown blob sang Learning Object JSON

## Cài đặt lần đầu (macOS / Linux)

Yêu cầu Python 3.9+ (khuyến nghị 3.12). Kiểm tra: `python3 --version`.

```bash
cd pdf2learn

# 1. Tạo môi trường ảo (venv) — chỉ làm MỘT LẦN cho mỗi máy:
python3 -m venv .venv

# 2. Kích hoạt venv — làm MỖI LẦN mở terminal mới (prompt sẽ hiện (.venv)):
source .venv/bin/activate

# 3. Cài thư viện (pymupdf/fitz, requests, python-dotenv):
python -m pip install -r requirements.txt

# 4. Smoke test — 0 token, không cần API key:
python test_render.py
python main.py sach.pdf --dry-run
```

Lỗi thường gặp:

| Lỗi | Nguyên nhân & cách xử |
|---|---|
| `zsh: command not found: pip` | macOS không có lệnh `pip` trần — dùng `python3 -m pip ...` hoặc kích hoạt venv rồi dùng `python -m pip ...` |
| `ModuleNotFoundError: No module named 'fitz'` | Chưa cài requirements, HOẶC quên `source .venv/bin/activate` nên đang chạy Python hệ thống (không có pymupdf) |
| `error: externally-managed-environment` | Homebrew Python chặn cài global (PEP 668) — dùng venv như trên là hết |
| pymupdf không có wheel / build lỗi | Python quá mới (bản beta) — cài Python 3.12 ổn định rồi tạo lại venv: `python3.12 -m venv .venv` |

Trên **Google Colab** không cần venv: `%pip -q install pymupdf requests python-dotenv`
trong cell đầu là đủ (xem mục Colab bên dưới cho phần API key).

---

## Nhập API key (token) của Gemini

Lấy key miễn phí tại https://aistudio.google.com (Get API key → Create API key,
chuỗi dạng `AIza...`). Tool đọc key từ biến môi trường `GEMINI_API_KEY`,
theo 1 trong 3 cách sau — **tuyệt đối không dán key thẳng vào code**:

**Cách 1 — file `.env` (khuyên dùng khi chạy local):** tạo file tên `.env`
đặt CÙNG THƯ MỤC với `main.py`, nội dung:

```
GEMINI_API_KEY=AIza...key-cua-ban...
# nếu dùng --review:
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
```

`main.py` và `toc_from_images.py` tự nạp file này qua `python-dotenv`
(đã có trong requirements.txt). Nhớ thêm `.env` vào `.gitignore` — key lộ
lên git là phải revoke tạo key mới.

**Cách 2 — export trong terminal (mất khi đóng shell):**

```bash
export GEMINI_API_KEY=AIza...        # macOS / Linux
$env:GEMINI_API_KEY="AIza..."        # Windows PowerShell
```

**Cách 3 — Google Colab:** sidebar trái → icon chìa khoá 🔑 (Secrets) →
Add secret tên `GEMINI_API_KEY`, dán key, bật "Notebook access", rồi trong cell:

```python
import os
from google.colab import userdata
os.environ["GEMINI_API_KEY"] = userdata.get("GEMINI_API_KEY")
```

Kiểm tra nhanh key đã vào chưa: `python3 -c "import os; print(bool(os.environ.get('GEMINI_API_KEY')))"`
— in `True` là ổn. Thiếu key tool sẽ tự báo và dừng (chỉ `--dry-run` chạy
được không cần key).

---

## Cập nhật 6: toc_from_images.py nhận thẳng FILE PDF trang mục lục (mới)

Nguồn mục lục giờ nhận diện theo đuôi file, không bắt buộc phải chụp ảnh trước:
`toc_from_images.py` chấp nhận **1 file `.pdf`** (mỗi trang được render thành ảnh
rồi OCR), **1 file ảnh**, hoặc **1 thư mục** chứa lẫn lộn ảnh + PDF. Trang PDF
được phóng để bề ngang ≈ 1600px (có trần chống upscale) nên số trang in vẫn nét.
Dùng khi bạn đã có sẵn PDF mục lục (vd tách từ chính cuốn sách) — khỏi phải chụp tay.

```bash
# thẳng từ 1 file PDF mục lục -> 01_toc.json:
python3 toc_from_images.py toc_images/khtn-lop7.pdf --offset 1 --last-page 197 \
    --json-out runs/khtn-lop7/work/01_toc.json
# vẫn giữ nguyên đường cũ: thư mục ảnh chụp
python3 toc_from_images.py toc_images/ten-sach --out ten-sach.toc.txt
```
(Đặt file PDF mục lục của bạn vào `toc_images/`, vd `toc_images/khtn-lop7.pdf`.)

---

## Cập nhật 6: bỏ mindmap, prompt v3 sinh động hơn (kiểu tờ tóm tắt infographic)

Mục tiêu: nội dung bài học dễ hiểu và sinh động hơn — bám theo bố cục các tờ
"Tổng hợp kiến thức" giáo viên hay tự làm tay (khối mở đầu nêu trọng tâm,
công thức tách riêng biến số, khối chốt cuối bài). Bỏ hẳn field `mindmap` —
sơ đồ tư duy khó đọc trên giao diện text/markdown và không tăng độ dễ hiểu
bằng cách trình bày trực tiếp trong nội dung.

- `stage_content.py`: `CONTENT_SCHEMA`/`CONTENT_PROMPT` v3.
  - Bỏ field `mindmap` (schema + prompt + required).
  - Thêm `concept_overview` (1-2 câu trọng tâm cả bài, mở đầu bài học).
  - Thêm `quick_review` (2-4 câu chốt ngắn cuối bài, kiểu "Ghi nhớ nhanh").
  - `sections[].formula` (tuỳ chọn): `{expression, variables: [{symbol, meaning}]}`
    — chỉ thêm khi mục có công thức/định luật thật trong tài liệu.
  - Thêm hướng dẫn văn phong: ưu tiên so sánh/ví dụ cụ thể gắn đời sống học
    sinh thay vì định nghĩa hàn lâm.
- `render_markdown.py`: render `concept_overview` (khối đầu, blockquote),
  `formula` trong section (khối code `Công thức:` + bullet biến số),
  `quick_review` (khối cuối, trước phần ảnh). Cập nhật `DENSITY` — mức
  `minimal` giờ giữ Khái niệm trọng tâm + Ghi nhớ nhanh thay vì mindmap.
- `stage_images.py`: bỏ hẳn `_mindmap_svg` (vẽ SVG từ field `mindmap`).
  Mặc định (`--book-images` tắt) topic giờ KHÔNG có ảnh nào — trước đây
  luôn có ít nhất mindmap SVG. Bật `--book-images` nếu cần ảnh trích từ PDF.
- `export_json.py`: bỏ `mindmap_mermaid`; xuất thêm `concept_overview`,
  `quick_review`, `sections[].formula`. `prompt_version` -> `"v3"`.
- `mindmap_svg.py`: XOÁ (không còn nơi nào dùng).
- `main.py`: `CONTENT_VERSION = 3` (cache cũ cần `--redo-from 3`).
- `gemini.py`, `test_render.py`: cập nhật mock/fixture theo schema mới.
- `main.py`: thêm cờ `--redo-images` — CHỈ xoá cache + thư mục ảnh (stage 4)
  rồi sinh lại, GIỮ NGUYÊN content/câu hỏi đã có (0 token stage 3/5/6).
  Khác với `--redo-from 4` (xoá luôn cả câu hỏi + review từ stage 4 trở đi).
  Tiện khi bật/tắt `--book-images` hoặc đổi bộ lọc ảnh mà không muốn sinh
  lại cả bài học:
  ```bash
  python3 main.py sach.pdf --toc-file work/01_toc.json --book-images --redo-images
  ```

Cache cũ (v1/v2) không đọc được nữa — pipeline sẽ báo lỗi và yêu cầu:

```bash
python3 main.py sach.pdf --redo-from 3
```

---

## Cập nhật 5: chỉ giữ mindmap SVG + hậu xử lý CSV có sẵn

Ảnh trang sách (.jpg trích từ PDF) ít giá trị trên giao diện học và làm bài dài.
Từ nay MẶC ĐỊNH chỉ giữ mindmap SVG (code vẽ, 0 token).

- stage_images.py: thêm tham số book_images (mặc định False). Tắt = không trích
  ảnh PDF, không gọi img_filter => tiết kiệm 1 request/topic. Bật lại bằng
  cờ main.py --book-images nếu khoá cần ảnh gốc.
- condense_csv.py (MỚI): hậu xử lý topics.csv ĐÃ XUẤT (0 token).
    python3 condense_csv.py topics.csv --out topics.clean.csv          # bỏ ảnh .jpg, giữ .svg
    python3 condense_csv.py topics.csv --out topics.clean.csv --trim   # + bỏ bullet trùng, cap 4/mục
  --trim chỉ BỎ NGUYÊN bullet trùng/dư, KHÔNG cắt cụt giữa câu => không sai ý.

Đo trên topics.csv thật (55 bài): bỏ 184 ảnh trang sách, giữ 55 SVG.
Rút gọn text bằng code chỉ giảm 3-6% (phần dài là câu dài dòng, không phải
bullet trùng) — muốn giảm ~60% như viết tay phải --redo-from 3 (prompt v2).

Khoá SAU chạy sạch từ đầu, 0 xử lý thêm:
    python3 main.py sach.pdf --toc-file work/01_toc.json --redo-from 3
    # content ngắn (prompt v2) + chỉ SVG (mặc định) tự động.

---

## Cập nhật 4: giảm độ dài content (bài học ngắn gọn hơn)

Đo thực tế topics.csv (55 bài): median 1043 từ (~8 phút đọc), dài nhất 1273 từ
— GẤP ĐÔI mức hợp lý cho learning object lớp 6 (~500 từ / 4 phút). Thủ phạm:
"Nội dung chính" + "Từ khoá" chiếm ~60% chữ, point phình 36-54 từ (2-3 dòng)
do prompt cũ bảo "tóm tắt CHI TIẾT".

Hai lớp giải pháp:

A) PROMPT (root-cause, cần --redo-from 3): CONTENT_PROMPT thêm QUY TẮC ĐỘ DÀI —
   point <= 20 từ, sections <= ~350 từ, 2-4 mục, mỗi mục 2-4 point. key_points
   KHÔNG bị giới hạn (dữ liệu nội bộ). Đây là cách cho câu ngắn mà vẫn TRỌN ý.

B) RENDER density (0 token, dùng ngay không sinh lại): cờ --density
     full    : như cũ
     compact : 3 point/mục, cắt point dài còn 22 từ, bỏ ví dụ key_terms
     minimal : chỉ Mục tiêu + Nội dung chính (2 point/18 từ) + Mindmap
   Đo trên 1 bài: full 791 từ -> minimal 218 từ (~1.7 phút).
   CẢNH BÁO: density cắt bằng code (chặt cụt câu + "…"), tốt để xem nhanh /
   ôn tập, KHÔNG thay được việc AI viết lại gọn (Hướng A) cho bản phát hành.

Khuyến nghị: chạy 1-2 bài với prompt mới (--redo-from 3) xem độ dài đã ổn chưa;
đồng thời để bibeli render --density minimal cho chế độ "xem nhanh", full cho
"đọc kỹ" — cùng một cache, 0 token.

Gợi ý trực quan thêm (phía bibeli, không thuộc pipeline): đưa Liên hệ/Dễ nhầm/
Mẹo nhớ vào khối gập (progressive disclosure); bỏ bớt emoji header cho đỡ rối.

---

## Cập nhật 3: toc_from_images.py — OCR ảnh chụp trang mục lục (mới)

Quy trình: `toc_images/ten-sach/hinh*.png` → 1 request AI OCR → `toc.txt`
(ĐIỂM DỪNG để người duyệt/sửa) → `build_toc.py` (thuần code) → `01_toc.json`
→ `main.py --toc-file`. Ảnh sort theo natural order (hinh1, hinh2, hinh10);
ảnh > 1600px tự shrink trước khi gửi để giảm token; `--json-out` gộp 2 bước
khi đã biết `--offset`/`--last-page`. Mock tag `toc_ocr` cho `--dry-run`.
(Cập nhật 6 mở rộng nguồn nhận vào cho cả file PDF, không chỉ ảnh.)

```bash
python3 toc_from_images.py toc_images/ten-sach --out ten-sach.toc.txt   # duyệt tay
python3 build_toc.py ten-sach.toc.txt --offset 2 --last-page 197 --out runs/ten-sach/work/01_toc.json
# hoặc gộp: toc_from_images.py toc_images/ten-sach --offset 2 --last-page 197 --json-out ...
```

## Cập nhật 2: xuất đúng FORMAT JSON ĐÍCH (theo mẫu lich_su_la_gi_learning_object.json)

File mới `export_json.py` (thuần code, 0 token) map dữ liệu nội bộ -> JSON đích:
`title/subject/grade/prompt_version` + `objectives/hook/key_terms/sections(icon_hint)/
real_life/memory_hooks/misconceptions` + `mindmap_mermaid` (code sinh bằng
`to_mermaid()` từ cây — không bao giờ lỗi cú pháp) + `quiz` (options + answer_index
+ bloom `nho|hieu|van_dung` + difficulty `de|trung_binh|kho`, map từ difficulty 1-3
nội bộ). `key_points` giữ nội bộ, không xuất.

Cờ mới:
```bash
--export-json                 # ghi output/json/{topic_slug}.json (pretty) mỗi topic
--subject "Lịch sử và Địa lí" # metadata; --grade tự rút từ --level nếu bỏ trống
--content-format json         # cột content trong topics.csv = chính JSON đích (compact)
```
Cả 3 đều 0 token — sinh lại từ cache; đổi format chỉ cần chạy lại lệnh.

Nghiệm thu đã pass: cấu trúc key khớp 1:1 file mẫu (không thiếu/không thừa,
cả cấp quiz item lẫn section), answer_index hợp lệ, JSON sống sót CSV round-trip.

Lưu ý mapping: bloom và difficulty trong file mẫu là 2 trục ĐỘC LẬP (mẫu có cặp
`van_dung + trung_binh`), nhưng nội bộ chỉ có 1 trục difficulty 1-3 nên hiện map
1:1 (nho↔de, hieu↔trung_binh, van_dung↔kho). Muốn AI chấm 2 trục riêng: thêm
"bloom" enum vào QUESTIONS_SCHEMA + 1 dòng prompt — không tốn thêm request.

---

Nguyên tắc thiết kế: **AI chỉ trả về DỮ LIỆU (data), CODE sinh cú pháp (syntax)**.
Đổi format từ nay là việc của code (0 token) — muốn markdown hay JSON trong
`topics.csv` chỉ là một cờ export, cache AI giữ nguyên.

## File thay đổi

| File | Thay đổi |
|---|---|
| `stage_content.py` | `CONTENT_SCHEMA` + prompt v2: AI trả về Learning Object JSON (objectives, hook, key_terms, sections, mindmap, real_life, memory_hooks, misconceptions, key_points). Prompt tách rõ nhóm field *phải bám tài liệu* và nhóm *được bổ sung* (chống hallucination giữ nguyên chiến thuật cắt sub-PDF theo page range). |
| `render_markdown.py` | Thêm `content_markdown(entry)` — điểm vào duy nhất cho mọi stage cần text của topic; tự nhận cache v1 (blob) lẫn v2 (LO JSON). |
| `stage_export.py` | `_compose_content()` render bằng code; thêm tham số `content_format="markdown"|"json"`. Dạng `json`: đổ Learning Object (kèm list `images`) thành JSON compact 1 dòng, đã test sống sót CSV round-trip. |
| `stage_images.py` | **Xoá `_gen_svg` + `SVG_PROMPT`** (AI sinh SVG — hay lỗi cú pháp, tốn 1 request/topic). Thay bằng `mindmap_svg.to_svg()` từ field `mindmap` của LO: 0 token, không bao giờ lỗi parse. Mindmap giờ được vẽ THÊM kể cả khi topic có ảnh gốc. Dọn `if True:` thừa. |
| `stage_questions.py`, `stage_review.py` | Dùng `content_markdown(entry)` thay vì đọc thẳng `entry["content_markdown"]`. |
| `gemini.py` | `MockGemini` tag `content` trả mock v2 (đúng PATCH_gemini_mock.md, có bẫy `\|` và `\n` để dry-run kiểm tra escape). |
| `main.py` | `CONTENT_VERSION = 2` + guard cache cũ (báo `--redo-from 3`). Cờ mới: `--content-format`, `--toc-file` (dùng TOC dựng sẵn từ `build_toc.py`, 0 token), `--yes`. Guard xác nhận mục lục trước khi đốt quota (bước 3 trong patch). |
| `utils.py` | ⚠️ CHỈ là bản dựng lại để test trong sandbox (file gốc không có trong bộ upload). **Repo của bạn giữ bản gốc, đừng ghi đè.** |

Không đổi: `mindmap_svg.py`, `test_render.py`, `build_toc.py`, `quality_checks.py`, `stage_toc.py`.

## Nghiệm thu (0 token)

```bash
python3 test_render.py                 # 15 check renderer — đã pass
python3 main.py sample.pdf --dry-run   # toàn pipeline với MockGemini — đã pass
python3 main.py sample.pdf --dry-run --content-format json   # content = JSON — đã pass
```

Đã test thêm: guard cache v1 báo đúng thông điệp `--redo-from 3`;
JSON trong cột content parse lại được sau CSV round-trip (UTF-8 BOM).

## Chạy thật

```bash
# TOC gõ tay (khuyên dùng cho sách scan) — 0 token, chính xác 100%:
python3 build_toc.py toc.txt --offset 2 --last-page 197 --out /tmp/toc.json
python3 main.py sach.pdf --level "Lớp 6" --toc-file /tmp/toc.json --dpi 110

# Cache cũ v1 -> bắt buộc sinh lại content:
python3 main.py sach.pdf --redo-from 3

# Đổi format cột content về sau KHÔNG tốn token:
python3 main.py sach.pdf --content-format json    # chỉ re-render + export lại
```

Lưu ý vận hành: trên Colab/CI thêm `--yes` (không có TTY để Enter xác nhận).
Batch cũ (batch-01…) giữ format tại thời điểm export; snapshot FULL ở gốc
luôn theo `--content-format` của lần chạy gần nhất.

## Token: trước / sau (mỗi topic)

| Request | v1 | v2 |
|---|---|---|
| content | 1 (PDF + prompt) | 1 (như cũ, output JSON ~ tương đương) |
| svg_diagram (fallback) | 0-1 | **0** — code vẽ mindmap |
| img_filter | 0-1 | 0-1 (giữ nguyên) |
| questions + validate | 2 | 2 |
| **Format lại content** | sinh lại content (≈ đắt nhất pipeline) | **0 token** |
