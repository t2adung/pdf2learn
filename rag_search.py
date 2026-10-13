#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rag_search.py — Truy vấn thử kho vector (bước RETRIEVE của RAG).

Dùng để nghiệm thu chất lượng chunk/embedding sau khi chạy main.py --rag:

  python3 rag_search.py "Tế bào là gì?" --book sach --k 5
  python3 rag_search.py "quang hợp" --book sach --topic bai-3-quang-hop --json

Cần DATABASE_URL (hoặc --dsn) và CÙNG model đã dùng lúc embed (--model).
"""
import argparse
import json
import os
import sys

from stage_rag import DEFAULT_MODEL, Embedder, RagError, VectorStore


def main():
    ap = argparse.ArgumentParser(description="Tìm top-k chunk bài giảng (pgvector)")
    ap.add_argument("query", help="câu hỏi / truy vấn")
    ap.add_argument("--book", default=None, help="lọc theo sách (tên PDF không đuôi)")
    ap.add_argument("--topic", default=None, help="lọc theo topic_slug")
    ap.add_argument("--k", type=int, default=5, help="số chunk trả về")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="model embedding — PHẢI trùng model lúc embed")
    ap.add_argument("--dsn", default=None, help="Postgres DSN (mặc định $DATABASE_URL)")
    ap.add_argument("--json", action="store_true", help="in JSON (để ghép vào prompt)")
    args = ap.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    dsn = args.dsn or os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        sys.exit("Thiếu DATABASE_URL (hoặc --dsn).")
    try:
        emb = Embedder(args.model)
        store = VectorStore(dsn, emb.dim)
        hits = store.search(emb.embed_query(args.query), k=args.k, book=args.book,
                            topic=args.topic, model=args.model)
        store.close()
    except RagError as e:
        sys.exit(f"❌ {e}")
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return
    if not hits:
        print("(không có kết quả — đã chạy main.py --rag chưa? --book/--model đúng chưa?)")
    for i, h in enumerate(hits, 1):
        pages = (f"tr.{h['page_start']}" if h["page_start"] == h["page_end"]
                 else f"tr.{h['page_start']}-{h['page_end']}")
        print(f"#{i} sim={h['similarity']:.3f} [{h['source']}] {h['topic_slug']} "
              f"› {h['section']} ({pages})")
        print("   " + h["content"][:300].replace("\n", " "))


if __name__ == "__main__":
    main()
