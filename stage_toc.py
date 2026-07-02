# -*- coding: utf-8 -*-
"""Stage 1: Trích mục lục (TOC).
Nguyên tắc: bookmark có sẵn trong PDF -> dùng code (chính xác 100%, 0 token AI);
không có -> nhờ Gemini đọc PDF suy ra mục lục kèm page range.

Stage 2: Chuẩn hoá cấu trúc + sinh slug bằng code (deterministic).
"""
import fitz

from utils import log, module_slug, topic_slug, uniquify

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


def extract_toc(pdf_path, client, force_ai: bool = False) -> dict:
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
