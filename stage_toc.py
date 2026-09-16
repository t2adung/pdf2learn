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

TOC_LIST_PROMPT = """Các ảnh dưới đây là những TRANG ĐẦU của một cuốn sách giáo dục — trong đó CÓ trang MỤC LỤC (Contents / Mục lục).
Nhiệm vụ: đọc TRANG MỤC LỤC và trích ra cấu trúc:
- modules = chương/phần/unit lớn; mỗi module có topics = các bài học/mục con.
- page_printed = SỐ TRANG IN ghi cạnh mỗi mục trong mục lục (con số ở CỘT BÊN PHẢI mỗi dòng).

QUY TẮC ĐỌC SỐ TRANG (CỰC KỲ QUAN TRỌNG):
- Đọc CHÍNH XÁC con số ở cuối MỖI dòng. Mỗi mục thường có số trang KHÁC nhau và TĂNG DẦN từ trên xuống.
- TUYỆT ĐỐI KHÔNG lặp lại cùng một số cho nhiều mục, KHÔNG đoán, KHÔNG bỏ sót các mục ở NỬA DƯỚI mục lục.
- Nếu mục lục dài quá 1 trang, đọc HẾT tất cả các trang mục lục có trong ảnh.
- Nếu một dòng thật sự không có số trang / đọc không rõ, đặt page_printed = 0 (KHÔNG được điền số của dòng khác).

QUY TẮC KHÁC:
- CHỈ lấy bài học/mục chính. Bỏ qua: bìa, lời nói đầu, chính trang mục lục, phụ lục, đáp án, bảng tra cứu, giải thích thuật ngữ.
- Giữ nguyên tiêu đề theo đúng ngôn ngữ gốc.
- Nếu sách không chia chương, tạo 1 module duy nhất mang tên tài liệu.
- Nếu trong các ảnh KHÔNG có trang mục lục, trả về {"modules": []}."""

_OFFSET_SCHEMA = {
    "type": "object",
    "properties": {"page_pdf": {"type": "integer"}},
    "required": ["page_pdf"],
}


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


def _extract_toc_smart(doc, pdf_path, client, front: int, tail: int,
                       cover_offset: int, auto_offset: bool, toc_dpi: int,
                       max_offset: int):
    """Rule mục lục: đọc `front` trang đầu (+`tail` trang cuối nếu >0) ở độ phân
    giải cao -> list bài + SỐ TRANG IN -> áp offset (cover cố định hoặc tự dò) ->
    dựng deterministic. Trả None nếu không thấy mục lục (để caller fallback)."""
    n = doc.page_count
    front_idx = list(range(0, min(front, n)))
    tail_idx = [p for p in range(max(0, n - tail), n) if p not in front_idx] if tail else []
    pages_idx = front_idx + tail_idx
    log(f"   [smart] Đọc {len(front_idx)} trang đầu"
        + (f" + {len(tail_idx)} trang cuối" if tail_idx else "")
        + f" ở {toc_dpi} dpi để đọc mục lục (thay vì cả {n} trang).")
    toc_pdf = _subpdf(doc, pages_idx, toc_dpi, jpg_quality=85)
    listing = client.generate_json(
        [client.pdf_part(toc_pdf, f"{pdf_path.stem}-mucluc.pdf"),
         {"text": TOC_LIST_PROMPT}], TOC_LIST_SCHEMA, tag="toc")
    modules = [m for m in listing.get("modules", []) if m.get("topics")]
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
