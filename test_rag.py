# -*- coding: utf-8 -*-
"""test_rag.py — Nghiệm thu bước RAG (chunk + embed + pgvector).
Chạy: python3 test_rag.py — KHÔNG gọi API, KHÔNG tải model (MockEmbedder). 0 token.

Phần DB chỉ chạy khi có biến RAG_TEST_DSN trỏ tới Postgres có pgvector
(dùng 1 database TEST riêng — test sẽ xoá dữ liệu của book "__test_rag__").
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import fitz

from stage_rag import (MockEmbedder, chunk_topic, pack_units, run_rag,
                       split_units, topic_hash)

ROW = {"module_slug": "chuong-1", "module_title": "Chương 1",
       "topic_slug": "chuong-1-te-bao", "topic_title": "Tế bào",
       "order": 1, "level": "Lớp 6", "page_start": 1, "page_end": 2}
LO = {"objectives": ["Nêu được khái niệm tế bào."],
      "hook": "Vì sao cơ thể lớn lên?", "hook_answer": "Vì tế bào phân chia.",
      "key_terms": [{"term": "Tế bào", "definition": "đơn vị cấu tạo của sự sống",
                     "example": "tế bào trứng"}],
      "sections": [{"heading": "Cấu tạo", "points": [f"Ý thứ {i} về màng, chất tế bào và nhân."
                                                     for i in range(40)]},
                   {"heading": "Rỗng", "points": []}],
      "real_life": ["Vết thương tự lành nhờ tế bào mới."],
      "key_points": ["Tế bào là đơn vị cơ bản của sự sống."]}


def main():
    fails = []

    def check(cond, msg):
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            fails.append(msg)

    emb = MockEmbedder()
    count = emb.count_tokens

    # --- split / pack ---
    check(split_units("Câu một. Câu hai?\n\n  Dòng  ba") == ["Câu một.", "Câu hai?", "Dòng ba"],
          "split_units tách theo dòng + câu, gộp khoảng trắng")
    units = [f"câu số {i} ." for i in range(50)]                # 4 token/câu
    chunks = pack_units(units, budget=40, overlap=8, count=count)
    check(all(count(c) <= 40 for c in chunks), "mọi chunk <= budget")
    check(len(chunks) > 1 and chunks[1].startswith("câu số 8 . câu số 9 ."),
          "chunk sau chồng lấn ~overlap token cuối chunk trước")
    check(all(f"câu số {i} ." in " ".join(chunks) for i in range(50)), "không mất câu nào")
    long = pack_units(["từ " * 100], budget=30, overlap=0, count=count)
    check(len(long) >= 4 and all(count(c) <= 30 for c in long), "câu quá dài bị cắt theo từ")

    # --- chunk_topic ---
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Trang sach co text layer. " * 10)
    doc.new_page()                                               # trang "scan" trống
    cs = chunk_topic(ROW, LO, doc, count, chunk_tokens=80, overlap_tokens=10)
    secs = [c["section"] for c in cs]
    check(secs[:2] == ["Tổng quan", "Từ khoá"] and "Ý chính" in secs,
          "nhóm lesson: Tổng quan → Từ khoá → các mục → Ý chính")
    check(secs.count("Cấu tạo") >= 2 and "Rỗng" not in secs, "mục dài tách nhiều chunk, mục rỗng bỏ")
    book = [c for c in cs if c["source"] == "book"]
    check(len(book) == 1 and book[0]["page_start"] == 1, "chỉ trang có text layer thành chunk book")
    check(all(c["token_count"] <= 80 for c in cs), "token_count (gồm header) <= chunk_tokens")
    check(all(c["embed_text"].startswith("Bài: Tế bào › Mục: ") for c in cs),
          "embed_text có header ngữ cảnh")
    check([c["chunk_index"] for c in cs] == list(range(len(cs))), "chunk_index liên tục")
    only_lesson = chunk_topic(ROW, LO, doc, count, sources=("lesson",))
    check(all(c["source"] == "lesson" for c in only_lesson), "sources=('lesson',) bỏ chunk book")
    check(topic_hash(cs, "m") == topic_hash(chunk_topic(ROW, LO, doc, count, chunk_tokens=80,
                                                        overlap_tokens=10), "m")
          and topic_hash(cs, "m") != topic_hash(cs, "m2"), "topic_hash deterministic, phụ thuộc model")
    v1 = chunk_topic(ROW, {"content_markdown": "## A\n- ý một.\n- ý hai."}, None, count)
    check(len(v1) == 1 and "ý hai." in v1[0]["content"], "đọc được cache content v1 (markdown)")

    # --- run_rag không DB: chỉ ghi chunks.jsonl ---
    with tempfile.TemporaryDirectory() as td:
        st = run_rag([ROW, {**ROW, "topic_slug": "chua-gen"}], {ROW["topic_slug"]: LO}, doc,
                     "__test_rag__", Path(td), emb, store=None, chunk_tokens=9999)
        lines = (Path(td) / "rag" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        check(st["topics"] == 1 and len(lines) == st["chunks"], "chunks.jsonl đủ dòng, bỏ topic chưa gen")
        check(max(json.loads(x)["token_count"] for x in lines) <= emb.max_tokens - 2,
              "chunk_tokens vượt giới hạn model bị hạ xuống")

    # --- pgvector (tuỳ chọn) ---
    dsn = os.environ.get("RAG_TEST_DSN", "").strip()
    if not dsn:
        print("  - bỏ qua phần DB (đặt RAG_TEST_DSN để chạy)")
    else:
        from stage_rag import VectorStore
        store = VectorStore(dsn, emb.dim)
        store.conn.execute("delete from rag_chunks where book='__test_rag__'")
        with tempfile.TemporaryDirectory() as td:
            st1 = run_rag([ROW], {ROW["topic_slug"]: LO}, doc, "__test_rag__", Path(td), emb, store)
            st2 = run_rag([ROW], {ROW["topic_slug"]: LO}, doc, "__test_rag__", Path(td), emb, store)
            n = store.conn.execute("select count(*) from rag_chunks where book='__test_rag__'"
                                   ).fetchone()[0]
            check(st1["embedded"] == 1 and st2["skipped"] == 1 and n == st1["chunks"],
                  "upsert idempotent: chạy lần 2 bỏ qua, không nhân đôi dòng")
            lo2 = {**LO, "key_points": ["Ý mới thay đổi."]}
            st3 = run_rag([ROW], {ROW["topic_slug"]: lo2}, doc, "__test_rag__", Path(td), emb, store)
            n3 = store.conn.execute("select count(*) from rag_chunks where book='__test_rag__'"
                                    ).fetchone()[0]
            check(st3["embedded"] == 1 and n3 == st3["chunks"], "content đổi -> thay toàn bộ chunk topic")
            target = chunk_topic(ROW, lo2, doc, count)[0]
            hits = store.search(emb.embed_query(target["embed_text"]), k=3, book="__test_rag__")
            check(hits and hits[0]["content"] == target["content"]
                  and abs(hits[0]["similarity"] - 1) < 1e-4, "match_rag_chunks trả đúng chunk top-1")
        store.conn.execute("delete from rag_chunks where book='__test_rag__'")
        store.close()

    print(f"\n{'❌ FAIL' if fails else '✅ PASS'} ({len(fails)} lỗi)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
