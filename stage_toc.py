# -*- coding: utf-8 -*-
"""Stage 1: Trích mục lục (TOC).
Nguyên tắc: bookmark có sẵn trong PDF -> dùng code (chính xác 100%, 0 token AI);
không có -> nhờ Gemini đọc PDF suy ra mục lục kèm page range.

Stage 2: Chuẩn hoá cấu trúc + sinh slug bằng code (deterministic).
"""
import fitz

from utils import log, module_slug, topic_slug, uniquify, warn

TOC_SCHEMA = {
    "type": "object",
    "properties": {
        "modules": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "topics": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "page_start": {"type": "integer"},
                        "page_end": {"type": "integer"},
                    },
                    "required": ["title", "page_start", "page_end"],
                }},
            },
            "required": ["title", "topics"],
        }},
    },
    "required": ["modules"],
}

TOC_PROMPT = """Bạn nhận được một tài liệu PDF mang tính giáo dục/đào tạo.
Nhiệm vụ: xác định cấu trúc mục lục gồm các MODULE (chương/phần lớn) và bên trong mỗi module là các TOPIC (bài học/mục con).

Yêu cầu:
- page_start, page_end là SỐ TRANG TRONG FILE PDF, tính từ 1 (không phải số trang in trên giấy).
- Page range của các topic phải bao phủ toàn bộ nội dung chính, không chồng lấn nhau.
- Bỏ qua: trang bìa, lời nói đầu, trang mục lục, phụ lục, đáp án.
- Giữ nguyên tiêu đề theo ngôn ngữ gốc của tài liệu.
- Nếu tài liệu không chia chương, tạo 1 module duy nhất mang tên tài liệu."""


def extract_toc(pdf_path, client, force_ai: bool = False, dpi: int = 0,
                smart: bool = False, front: int = 13, tail: int = 0,
                cover_offset: int = 1, auto_offset: bool = False,
                toc_dpi: int = 200, max_offset: int = 30) -> dict:
    """dpi>0: nén từng trang về grayscale ở độ phân giải đó TRƯỚC khi gửi AI
    (giữ nguyên SỐ TRANG nên page range vẫn đúng). Cần cho sách scan nặng: PDF
    scan độ phân giải cao dễ bị Gemini trả HTTP 400 INVALID_ARGUMENT vì ảnh quá
    lớn — nén xuống ~110 dpi vừa lọt giới hạn vừa đủ nét để OCR.

    smart=True (rule mục lục): chỉ đọc `front` TRANG ĐẦU (mặc định 13) ở độ phân
    giải cao `toc_dpi` để OCR mục lục -> lấy tiêu đề + SỐ TRANG IN của từng bài.
    page_start = trang_in + cover_offset (mặc định +1 cho trang bìa);
    page_end = trang_start của bài kế - 1 (bài cuối = hết PDF). Dựng deterministic.
    auto_offset=True: thay cover_offset cố định bằng 1 lần dò offset qua AI."""
    doc = fitz.open(pdf_path)
    n_pages = doc.page_count

    if not force_ai:
        toc = doc.get_toc()  # [[level, title, page], ...]
        if toc:
            log(f"   Bookmark có sẵn ({len(toc)} mục) -> dùng code, không tốn AI.")
            return _toc_from_bookmarks(toc, n_pages)
        log("   PDF không có bookmark -> nhờ AI suy ra mục lục.")
    else:
        log("   --force-ai-toc: bỏ qua bookmark, dùng AI.")

    if smart:
        smart_toc = _extract_toc_smart(doc, pdf_path, client, front=front,
                                       tail=tail, cover_offset=cover_offset,
                                       auto_offset=auto_offset, toc_dpi=toc_dpi,
                                       max_offset=max_offset)
        if smart_toc is not None:
            return smart_toc
        warn("   [smart] Không tìm thấy mục lục -> fallback đọc cả cuốn.")

    if dpi and dpi > 0:
        from stage_content import cut_pages
        log(f"   Nén trang scan về {dpi} dpi grayscale trước khi gửi AI "
            f"({n_pages} trang)...")
        pdf_bytes = cut_pages(doc, 1, n_pages, dpi=dpi)
        log(f"   -> {len(pdf_bytes)/1e6:.1f}MB sau khi nén.")
    else:
        pdf_bytes = pdf_path.read_bytes()
    result = client.generate_json(
        [client.pdf_part(pdf_bytes, pdf_path.name), {"text": TOC_PROMPT}],
        TOC_SCHEMA, tag="toc")
    # kẹp page range vào [1, n_pages]
    for m in result["modules"]:
        for t in m["topics"]:
            t["page_start"] = max(1, min(int(t["page_start"]), n_pages))
            t["page_end"] = max(t["page_start"], min(int(t["page_end"]), n_pages))
    return result


# ======================================================================
# SMART TOC (chế độ ②): đọc TRANG MỤC LỤC + tự dò offset, dựng deterministic.
# Chính xác hơn cách đọc cả cuốn vì mỗi request chỉ nhìn vài trang.
# ======================================================================
TOC_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "modules": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "topics": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "page_printed": {"type": "integer"},
                    },
                    "required": ["title", "page_printed"],
                }},
            },
            "required": ["title", "topics"],
        }},
    },
    "required": ["modules"],
}

_OFFSET_SCHEMA = {
    "type": "object",
    "properties": {"page_pdf": {"type": "integer"}},
    "required": ["page_pdf"],
}

_TOC_PAGES_SCHEMA = {
    "type": "object",
    "properties": {"toc_pages": {"type": "array", "items": {"type": "integer"}}},
    "required": ["toc_pages"],
}

# Prompt đọc RIÊNG 1 trang mục lục — AI chỉ nhìn đúng 1 trang nên không bỏ sót
# cột số trang (lỗi hay gặp khi gộp nhiều trang: trang thứ 2 bị điền lặp 1 số).
TOC_PAGE_PROMPT = """Ảnh dưới đây là MỘT trang MỤC LỤC của sách.

CẤU TRÚC TRANG: trang này CÓ THỂ chia làm NHIỀU CỘT (trái sang phải). Hãy đọc HẾT cột bên TRÁI từ trên xuống dưới, RỒI MỚI sang cột bên PHẢI từ trên xuống dưới — trả kết quả theo đúng thứ tự đọc đó.

Trích MỌI dòng:
- modules = chương/phần/chủ đề/unit (dòng tiêu đề lớn, thường có màu nền đậm).
- topics = bài/mục con; mỗi topic có page_printed = SỐ TRANG IN ở cột "Trang" của ĐÚNG dòng đó.

QUY TẮC SỐ TRANG (RẤT QUAN TRỌNG):
- Đọc CHÍNH XÁC con số của TỪNG dòng. Số trang tăng dần theo thứ tự bài. TUYỆT ĐỐI KHÔNG lặp 1 số cho nhiều dòng, KHÔNG đoán, KHÔNG bỏ sót các dòng ở NỬA DƯỚI hay ở CỘT PHẢI.
- Một tiêu đề bài dài có thể xuống 2 dòng nhưng CHỈ ứng với 1 số trang -> vẫn là 1 topic.
- Nếu 1 dòng thực sự không đọc rõ số, đặt page_printed = 0 (KHÔNG lấy số của dòng khác).

QUY TẮC KHÁC:
- Nếu trang này CHỈ có các bài (tiếp nối chương ở trang trước, không có tiêu đề chương mới), trả về modules = [{"title": "", "topics": [...]}].
- Giữ nguyên tiêu đề theo ngôn ngữ gốc.
- BỎ QUA các dòng không phải bài học: "Mục lục"/"Contents"/"Trang", "Hướng dẫn sử dụng sách", "Lời nói đầu", "Bảng giải thích thuật ngữ", "Thuật ngữ", "Nguồn ảnh", phụ lục, đáp án."""


def _subpdf(doc, page_indices, dpi: int, jpg_quality: int = 75) -> bytes:
    """Dựng 1 PDF nhỏ chỉ gồm các trang (0-based) chỉ định; dpi>0 -> nén grayscale.
    Dùng pdf_part nên chạy được cho cả backend gemini lẫn claude.
    Trang mục lục nên render dpi cao + quality cao để đọc rõ CỘT SỐ TRANG."""
    sub = fitz.open()
    for pno in page_indices:
        if dpi and dpi > 0:
            pix = doc[pno].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
            jpg = pix.tobytes("jpeg", jpg_quality=jpg_quality)
            page = sub.new_page(width=pix.width, height=pix.height)
            page.insert_image(page.rect, stream=jpg)
        else:
            sub.insert_pdf(doc, from_page=pno, to_page=pno)
    data = sub.tobytes(garbage=3, deflate=True)
    sub.close()
    return data


def _warn_bad_printed(flat: list) -> None:
    """Cảnh báo khi cột SỐ TRANG do AI đọc bị đáng ngờ (lỗi hay gặp: AI đọc sót
    nửa dưới mục lục rồi lặp lại 1 con số cho mọi bài). Không sửa, chỉ báo để
    người dùng mở .toc.txt kiểm tra."""
    pages = [t["page_printed"] for t in flat if isinstance(t.get("page_printed"), int)]
    if len(pages) < 3:
        return
    from collections import Counter
    drops = sum(1 for i in range(1, len(pages)) if pages[i] < pages[i - 1])
    dup_run = max(Counter(pages).values())
    if drops or dup_run >= 3:
        warn(f"   [smart] ⚠ Cột số trang mục lục đáng ngờ "
             f"(giảm {drops} lần, 1 số bị lặp tới {dup_run} mục) — AI có thể đã đọc "
             f"sót nửa dưới mục lục. HÃY MỞ .toc.txt kiểm tra/sửa tay!")


def _detect_offset(doc, client, anchor: dict, n_pages: int,
                   max_offset: int, dpi: int) -> int:
    """Dò offset = trang_pdf - trang_in cho 1 bài neo. Gửi cửa sổ trang PDF khả dĩ
    [P .. P+max_offset] và hỏi AI bài đó thực sự bắt đầu ở trang PDF nào."""
    P = int(anchor["page_printed"])
    title = anchor["title"]
    w_start = max(1, P)                        # 1-based; offset front-matter >= 0
    w_end = min(n_pages, P + max_offset)
    if w_end < w_start:
        return 0
    idxs = list(range(w_start - 1, w_end))     # 0-based
    win = _subpdf(doc, idxs, dpi)
    prompt = (f"Tài liệu này gồm {len(idxs)} trang, tương ứng TRANG PDF số "
              f"{w_start} đến {w_end} của cuốn sách (ảnh 1 = trang {w_start}, "
              f"ảnh 2 = trang {w_start+1}, ...).\n"
              f"Bài học cần tìm có tiêu đề: \"{title}\".\n"
              f"Hỏi: bài này BẮT ĐẦU ở TRANG PDF số mấy? Trả JSON "
              f"{{\"page_pdf\": <số nguyên trong khoảng {w_start}-{w_end}>}}; "
              f"nếu không thấy trả page_pdf = 0.")
    try:
        r = client.generate_json(
            [client.pdf_part(win, "window.pdf"), {"text": prompt}],
            _OFFSET_SCHEMA, tag="toc")
        pg = int(r.get("page_pdf", 0))
    except Exception as e:
        warn(f"   [smart] dò offset lỗi ({e}) -> tạm dùng offset=0.")
        return 0
    if pg < w_start or pg > w_end:
        warn(f"   [smart] AI không định vị được bài neo (page_pdf={pg}) -> offset=0.")
        return 0
    return pg - P


def _build_from_printed(modules, offset: int, n_pages: int) -> dict:
    """Dựng toc dict {modules:[{title,topics:[{title,page_start,page_end}]}]} từ
    danh sách trang IN + offset. KHÔNG raise (an toàn cho batch): kẹp trong
    [1, n_pages], page_end = trang bắt đầu bài kế - 1."""
    out_mods, flat = [], []
    for m in modules:
        mm = {"title": str(m.get("title", "Nội dung chính")), "topics": []}
        for t in m.get("topics", []):
            pin = t.get("page_printed")
            if not isinstance(pin, int):
                continue
            ps = max(1, min(pin + offset, n_pages))
            tt = {"title": str(t.get("title", "")).strip(), "page_start": ps}
            if tt["title"]:
                mm["topics"].append(tt)
                flat.append(tt)
        if mm["topics"]:
            out_mods.append(mm)
    for i, t in enumerate(flat):
        nxt = flat[i + 1]["page_start"] if i + 1 < len(flat) else n_pages + 1
        t["page_end"] = max(t["page_start"], nxt - 1)
    return {"modules": out_mods}


def _find_toc_pages(doc, client, pages_idx, dpi: int) -> list:
    """1 call: xác định trong các trang ứng viên, trang nào là MỤC LỤC.
    Trả list chỉ số trang PDF (0-based) theo thứ tự."""
    sub = _subpdf(doc, pages_idx, dpi, jpg_quality=80)
    prompt = (f"Tài liệu gồm {len(pages_idx)} trang (ảnh 1..{len(pages_idx)}) là "
              f"các trang đầu/cuối của một cuốn sách. Ảnh nào là trang MỤC LỤC "
              f"(danh sách bài kèm số trang; thường có tiêu đề 'Mục lục'/'Contents')? "
              f"Trả JSON {{\"toc_pages\": [chỉ số ảnh 1-based]}}; nếu không có, trả [].")
    try:
        r = client.generate_json([client.pdf_part(sub, "front.pdf"),
                                  {"text": prompt}], _TOC_PAGES_SCHEMA, tag="toc")
        picked = [pages_idx[i - 1] for i in r.get("toc_pages", [])
                  if isinstance(i, int) and 1 <= i <= len(pages_idx)]
    except Exception as e:
        warn(f"   [smart] xác định trang mục lục lỗi ({e}).")
        return []
    seen, out = set(), []
    for p in picked:
        if p not in seen:
            seen.add(p); out.append(p)
    return out


def _read_toc_page(doc, client, pno: int, dpi: int) -> list:
    """Đọc RIÊNG 1 trang mục lục -> list module (mỗi module có topics + page_printed)."""
    sub = _subpdf(doc, [pno], dpi, jpg_quality=88)
    r = client.generate_json([client.pdf_part(sub, f"toc-p{pno+1}.pdf"),
                              {"text": TOC_PAGE_PROMPT}], TOC_LIST_SCHEMA, tag="toc")
    return [m for m in r.get("modules", []) if m.get("topics")]


def _merge_modules(acc: list, incoming: list) -> None:
    """Ghép module đọc từ trang sau vào danh sách tích luỹ. Module không có tiêu đề
    (tiếp nối chương trang trước) hoặc trùng tên chương cuối -> gộp topics."""
    for m in incoming:
        title = str(m.get("title", "")).strip()
        if acc and (not title or title == acc[-1]["title"]):
            acc[-1]["topics"].extend(m["topics"])
        else:
            acc.append({"title": title or "Nội dung chính",
                        "topics": list(m["topics"])})


def _extract_toc_smart(doc, pdf_path, client, front: int, tail: int,
                       cover_offset: int, auto_offset: bool, toc_dpi: int,
                       max_offset: int):
    """Rule mục lục: xác định các trang mục lục trong `front` trang đầu (+`tail`
    trang cuối nếu >0), rồi đọc TỪNG trang mục lục RIÊNG (tránh lỗi AI bỏ cột số
    trang ở trang thứ 2), ghép lại -> áp offset -> dựng deterministic.
    Trả None nếu không thấy mục lục (để caller fallback)."""
    n = doc.page_count
    front_idx = list(range(0, min(front, n)))
    tail_idx = [p for p in range(max(0, n - tail), n) if p not in front_idx] if tail else []
    pages_idx = front_idx + tail_idx
    log(f"   [smart] Tìm trang mục lục trong {len(front_idx)} trang đầu"
        + (f" + {len(tail_idx)} trang cuối" if tail_idx else "")
        + f" (thay vì cả {n} trang).")

    toc_pages = _find_toc_pages(doc, client, pages_idx, toc_dpi)
    if not toc_pages:
        return None
    log(f"   [smart] Trang mục lục: {[p+1 for p in toc_pages]} "
        f"-> đọc RIÊNG từng trang ở {toc_dpi} dpi.")

    modules = []
    for pno in toc_pages:
        _merge_modules(modules, _read_toc_page(doc, client, pno, toc_dpi))
    modules = [m for m in modules if m.get("topics")]
    if not modules:
        return None

    flat_in = [t for m in modules for t in m["topics"]
               if isinstance(t.get("page_printed"), int) and t["page_printed"] > 0]
    if not flat_in:
        # AI đọc được mục lục nhưng không kèm SỐ TRANG IN nào -> fallback.
        return None
    _warn_bad_printed(flat_in)

    if auto_offset:
        offset = _detect_offset(doc, client, flat_in[0], n, max_offset, toc_dpi)
        log(f"   [smart] offset (auto) = {offset} (trang_pdf = trang_in + {offset}).")
    else:
        offset = cover_offset
        log(f"   [smart] offset (cover cố định) = +{offset} "
            f"(trang_pdf = trang_in + {offset}).")

    toc = _build_from_printed(modules, offset, n)
    n_top = sum(len(m["topics"]) for m in toc["modules"])
    if n_top == 0:
        return None
    log(f"   [smart] -> {len(toc['modules'])} module, {n_top} bài (dựng deterministic).")
    return toc


def _toc_from_bookmarks(toc: list, n_pages: int) -> dict:
    """level 1 = module, level 2 = topic. Nếu outline phẳng (chỉ level 1):
    coi mỗi mục là topic trong 1 module chung."""
    has_level2 = any(lvl >= 2 for lvl, _, _ in toc)
    entries = []  # (is_module, title, page)
    if has_level2:
        for lvl, title, page in toc:
            if lvl == 1:
                entries.append(("module", title.strip(), page))
            elif lvl == 2:
                entries.append(("topic", title.strip(), page))
            # level >= 3: bỏ qua (mục quá nhỏ)
    else:
        entries.append(("module", "Nội dung chính", 1))
        for lvl, title, page in toc:
            entries.append(("topic", title.strip(), page))

    # page_end của topic = page_start của mục kế tiếp - 1
    modules, cur = [], None
    flat_topics = []
    for kind, title, page in entries:
        if kind == "module":
            cur = {"title": title, "topics": []}
            modules.append(cur)
        else:
            if cur is None:
                cur = {"title": "Nội dung chính", "topics": []}
                modules.append(cur)
            t = {"title": title, "page_start": max(1, page)}
            cur["topics"].append(t)
            flat_topics.append(t)
    for i, t in enumerate(flat_topics):
        nxt = flat_topics[i + 1]["page_start"] if i + 1 < len(flat_topics) else n_pages + 1
        t["page_end"] = max(t["page_start"], nxt - 1)
    return {"modules": [m for m in modules if m["topics"]]}


def build_structure(toc: dict, level: str) -> list:
    """Stage 2: sinh slug + order bằng code. Output: list topic phẳng, đủ cột topics.csv."""
    taken_mod, taken_topic = set(), set()
    rows, order = [], 0
    for m in toc["modules"]:
        m_slug = uniquify(module_slug(m["title"]), taken_mod)
        for t in m["topics"]:
            order += 1
            rows.append({
                "module_slug": m_slug,
                "module_title": m["title"],
                "topic_slug": uniquify(topic_slug(m_slug, t["title"]), taken_topic),
                "topic_title": t["title"],
                "order": order,
                "level": level,
                "page_start": t["page_start"],
                "page_end": t["page_end"],
            })
    return rows
