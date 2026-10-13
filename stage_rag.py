# -*- coding: utf-8 -*-
"""Stage 8 (tuỳ chọn, --rag / --rag-only): chunk + embed nội dung bài giảng
vào kho vector PostgreSQL + pgvector để làm RAG.

Luồng (0 token AI — chỉ chạy model embedding cục bộ):
  1. CHUNK   : mỗi topic -> các chunk theo 2 nguồn
                 - "lesson": Learning Object đã soạn (stage 3) — tách theo nhóm
                   ngữ nghĩa: tổng quan / từ khoá / từng mục nội dung / ý chính.
                 - "book"  : text layer gốc của PDF theo từng trang (PDF scan
                   không có text layer -> tự bỏ qua, chỉ còn nguồn lesson).
               Đo độ dài bằng CHÍNH tokenizer của model (gte-small: tối đa 512
               token, vượt là bị cắt câm) -> chunk ~300 token, overlap ~40.
               Mỗi chunk được embed kèm header ngữ cảnh "Bài: … › Mục: …"
               (contextual chunk header) để chunk ngắn vẫn mang đủ ngữ cảnh.
  2. EMBED   : sentence-transformers, model mặc định thenlper/gte-small
               (384 chiều), normalize L2 -> dùng cosine distance.
  3. STORE   : bảng rag_chunks (sql/rag_schema.sql), index HNSW cosine.
               Idempotent theo topic: hash toàn bộ chunk của topic; trùng hash
               trong DB -> bỏ qua (không embed lại); khác -> xoá + ghi lại trong
               1 transaction.

Đầu ra file (luôn có, kể cả khi không có DB):
  output/rag_chunks.csv : mỗi dòng 1 chunk, cột = cột bảng rag_chunks, cột
                          embedding là literal pgvector '[...]' -> import thẳng.
  output/rag_schema.sql : schema (số chiều đã điền) để tạo bảng trước khi import.
Vector được cache ở work/08_rag_vectors.json -> chạy lại không embed lại.
"""
import hashlib
import json
import re
from pathlib import Path

from utils import log, warn

DEFAULT_MODEL = "thenlper/gte-small"
DEFAULT_CHUNK_TOKENS = 300
DEFAULT_OVERLAP_TOKENS = 40
MIN_BOOK_PAGE_CHARS = 80        # trang ít chữ hơn => coi như scan/ảnh, bỏ qua
SCHEMA_FILE = Path(__file__).with_name("sql") / "rag_schema.sql"
SOURCES = ("lesson", "book")

# Tiền tố query/passage theo model. gte-* KHÔNG cần tiền tố; e5 thì bắt buộc.
MODEL_PREFIXES = {
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
}


class RagError(RuntimeError):
    pass


# ───────────────────────────── Embedder ─────────────────────────────

class Embedder:
    """Bọc sentence-transformers. Lazy import để pipeline chính không cần torch."""

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RagError("Thiếu thư viện RAG. Cài: pip install -r requirements-rag.txt")
        self.model_name = model_name
        try:   # lần đầu tải ~70MB từ HuggingFace, sau đó dùng cache ~/.cache/huggingface
            self.model = SentenceTransformer(model_name, device=device)
        except Exception as e:
            raise RagError(f"Không tải được model embedding '{model_name}' "
                           f"({e.__class__.__name__}: {str(e)[:200]}). Kiểm tra mạng "
                           "tới huggingface.co hoặc trỏ --rag-model tới thư mục model "
                           "đã tải sẵn.")
        # sentence-transformers >= 5 đổi tên hàm; giữ tương thích bản cũ
        get_dim = (getattr(self.model, "get_embedding_dimension", None)
                   or self.model.get_sentence_embedding_dimension)
        self.dim = get_dim()
        self.max_tokens = int(self.model.max_seq_length or 512)
        self.query_prefix, self.passage_prefix = MODEL_PREFIXES.get(model_name, ("", ""))

    def count_tokens(self, text: str) -> int:
        # không tính [CLS]/[SEP]; pack_units đã chừa phần đó
        return len(self.model.tokenizer.tokenize(text))

    def embed_passages(self, texts: list) -> list:
        return self._encode([self.passage_prefix + t for t in texts])

    def embed_query(self, text: str):
        return self._encode([self.query_prefix + text])[0]

    def _encode(self, texts):
        return self.model.encode(texts, batch_size=32, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False)


class MockEmbedder:
    """Embedder giả (deterministic, 0 phụ thuộc) cho --dry-run và test."""

    def __init__(self, model_name: str = "mock", dim: int = 384):
        self.model_name, self.dim, self.max_tokens = model_name, dim, 512
        self.query_prefix = self.passage_prefix = ""

    def count_tokens(self, text: str) -> int:
        return len(re.findall(r"\w+|[^\w\s]", text))

    def _vec(self, text):
        import numpy as np
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
        v = np.random.default_rng(seed).standard_normal(self.dim).astype("float32")
        return v / np.linalg.norm(v)

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


# ───────────────────────────── Chunking ─────────────────────────────

_SENT_SPLIT = re.compile(r"(?<=[.!?…;:])\s+")


def split_units(text: str) -> list:
    """Tách text thành đơn vị nhỏ (dòng -> câu) — ranh giới tự nhiên để cắt chunk."""
    units = []
    for line in str(text).splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            units.extend(s for s in _SENT_SPLIT.split(line) if s.strip())
    return units


def _split_long(unit: str, budget: int, count) -> list:
    """Câu dài hơn budget -> cắt theo từ (hiếm, nhưng tránh bị model truncate câm)."""
    out, cur = [], []
    for w in unit.split():
        if cur and count(" ".join(cur + [w])) > budget:
            out.append(" ".join(cur))
            cur = []
        cur.append(w)
    if cur:
        out.append(" ".join(cur))
    return out


def pack_units(units: list, budget: int, overlap: int, count) -> list:
    """Gom units thành chunk <= budget token (đo bằng `count`), chồng lấn
    ~overlap token câu cuối sang chunk sau để không mất ngữ cảnh ở ranh giới."""
    flat = []
    for u in units:
        flat.extend(_split_long(u, budget, count) if count(u) > budget else [u])
    chunks, cur, cur_tok = [], [], 0
    for u in flat:
        t = count(u)
        if cur and cur_tok + t > budget:
            chunks.append(" ".join(cur))
            tail, tail_tok = [], 0
            for x in reversed(cur):
                tx = count(x)
                if tail_tok + tx > overlap or tail_tok + tx + t > budget:
                    break
                tail.insert(0, x)
                tail_tok += tx
            cur, cur_tok = tail, tail_tok
        cur.append(u)
        cur_tok += t
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def _lesson_groups(entry: dict) -> list:
    """Learning Object -> [(section_label, [units])] theo nhóm ngữ nghĩa."""
    if not entry:
        return []
    if "content_markdown" in entry:                       # cache v1
        return [("Nội dung bài học", split_units(entry["content_markdown"]))]
    groups = []
    overview = []
    if entry.get("objectives"):
        overview.append("Mục tiêu: " + "; ".join(entry["objectives"]))
    if entry.get("hook"):
        overview.append("Câu hỏi khởi động: " + entry["hook"])
    if entry.get("hook_answer"):
        overview.append("Trả lời: " + entry["hook_answer"])
    for r in entry.get("real_life") or []:
        overview.append("Liên hệ thực tế: " + r)
    if overview:
        groups.append(("Tổng quan", overview))
    terms = []
    for t in entry.get("key_terms") or []:
        if isinstance(t, dict) and t.get("term"):
            s = f"{t['term']}: {t.get('definition', '')}".strip()
            if t.get("example"):
                s += f" (Ví dụ: {t['example']})"
            terms.append(s)
    if terms:
        groups.append(("Từ khoá", terms))
    for sec in entry.get("sections") or []:
        pts = [p for p in sec.get("points") or [] if p]
        if pts:
            groups.append((sec.get("heading") or "Nội dung", pts))
    if entry.get("key_points"):
        groups.append(("Ý chính", list(entry["key_points"])))
    return groups


def _book_pages(doc, row: dict) -> list:
    """[(page_no, text)] các trang có text layer trong page range của topic."""
    pages = []
    if doc is None:
        return pages
    for pno in range(row["page_start"], row["page_end"] + 1):
        if not 1 <= pno <= len(doc):
            continue
        text = doc[pno - 1].get_text("text") or ""
        if len(re.sub(r"\s+", "", text)) >= MIN_BOOK_PAGE_CHARS:
            pages.append((pno, text))
    return pages


def header_for(row: dict, section: str) -> str:
    return f"Bài: {row['topic_title']} › Mục: {section}"


def chunk_topic(row: dict, entry: dict, doc, count, sources=SOURCES,
                chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
                overlap_tokens: int = DEFAULT_OVERLAP_TOKENS) -> list:
    """Sinh danh sách chunk (dict) cho MỘT topic. Thuần code, deterministic."""
    out = []

    def add(source, section, body, page_start, page_end):
        head = header_for(row, section)
        out.append({
            "source": source, "section": section,
            "page_start": page_start, "page_end": page_end,
            "content": body, "embed_text": f"{head}\n{body}",
        })

    for section, units in (_lesson_groups(entry) if "lesson" in sources else []):
        budget = max(32, chunk_tokens - count(header_for(row, section)))
        for body in pack_units(units, budget, overlap_tokens, count):
            add("lesson", section, body, row["page_start"], row["page_end"])
    for pno, text in (_book_pages(doc, row) if "book" in sources else []):
        section = f"Trang {pno}"
        budget = max(32, chunk_tokens - count(header_for(row, section)))
        for body in pack_units(split_units(text), budget, overlap_tokens, count):
            add("book", section, body, pno, pno)

    for i, c in enumerate(out):
        c["chunk_index"] = i
        c["token_count"] = count(c["embed_text"])
    return out


def topic_hash(chunks: list, model_name: str) -> str:
    h = hashlib.sha256(model_name.encode("utf-8"))
    for c in chunks:
        h.update(b"\x00" + c["embed_text"].encode("utf-8"))
    return h.hexdigest()[:16]


# ───────────────────────────── Store (pgvector) ─────────────────────────────

class VectorStore:
    """Kho rag_chunks trên PostgreSQL + pgvector (psycopg 3)."""

    def __init__(self, dsn: str, dim: int):
        try:
            import psycopg
            from pgvector.psycopg import register_vector
        except ImportError:
            raise RagError("Thiếu thư viện RAG. Cài: pip install -r requirements-rag.txt")
        try:
            self.conn = psycopg.connect(dsn, autocommit=True)
        except Exception as e:
            raise RagError(f"Không kết nối được Postgres ({e.__class__.__name__}): {e}")
        self.dim = dim
        self._init_schema()
        register_vector(self.conn)

    def _init_schema(self):
        """Bật pgvector + tạo bảng/index/hàm (idempotent). Kiểm tra số chiều khớp model."""
        cur = self.conn.cursor()
        try:
            cur.execute("create extension if not exists vector")
        except Exception as e:
            raise RagError(
                "Không bật được extension pgvector: " + str(e).strip() +
                "\n  - Supabase: Dashboard → Database → Extensions → bật 'vector'."
                "\n  - Postgres tự host: cài gói pgvector (vd apt install "
                "postgresql-16-pgvector) và dùng user có quyền CREATE EXTENSION.")
        cur.execute("""select format_type(a.atttypid, a.atttypmod)
                       from pg_attribute a
                       where a.attrelid = to_regclass('rag_chunks')
                         and a.attname = 'embedding' and not a.attisdropped""")
        row = cur.fetchone()
        if row and row[0] != f"vector({self.dim})":
            raise RagError(
                f"Bảng rag_chunks đang dùng {row[0]} nhưng model mới ra vector({self.dim}). "
                "Mỗi DB chỉ 1 số chiều: dùng lại model cũ, hoặc dùng database/schema khác.")
        cur.execute(schema_sql(self.dim))

    def existing_hash(self, book, slug, model):
        cur = self.conn.execute(
            "select distinct topic_hash from rag_chunks "
            "where book=%s and topic_slug=%s and embedding_model=%s",
            (book, slug, model))
        rows = cur.fetchall()
        return rows[0][0] if len(rows) == 1 else None

    def replace_topic(self, book, row, model, thash, chunks, vectors):
        with self.conn.transaction():
            self.conn.execute(
                "delete from rag_chunks where book=%s and topic_slug=%s "
                "and embedding_model=%s", (book, row["topic_slug"], model))
            with self.conn.cursor() as cur:
                cur.executemany(
                    """insert into rag_chunks (book, module_slug, module_title,
                         topic_slug, topic_title, level, source, section,
                         page_start, page_end, chunk_index, content, token_count,
                         topic_hash, embedding_model, embedding)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [(book, row["module_slug"], row.get("module_title"),
                      row["topic_slug"], row.get("topic_title"), row.get("level"),
                      c["source"], c["section"], c["page_start"], c["page_end"],
                      c["chunk_index"], c["content"], c["token_count"],
                      thash, model, v)
                     for c, v in zip(chunks, vectors)])

    def search(self, qvec, k=5, book=None, topic=None, model=None):
        cur = self.conn.execute(
            "select * from match_rag_chunks(%s, %s, %s, %s, %s)",
            (qvec, k, book, topic, model))
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def close(self):
        self.conn.close()


# ───────────────────────────── Stage entry ─────────────────────────────

# Cột rag_chunks.csv = cột bảng rag_chunks (trừ id/created_at) -> import thẳng bằng
# \copy rag_chunks(<RAG_CSV_COLS>) from 'rag_chunks.csv' with (format csv, header true)
RAG_CSV_COLS = ["book", "module_slug", "module_title", "topic_slug", "topic_title",
                "level", "source", "section", "page_start", "page_end", "chunk_index",
                "content", "token_count", "topic_hash", "embedding_model", "embedding"]


def vector_literal(vec) -> str:
    """Vector -> literal pgvector '[0.012345,-0.5,...]' (6 chữ số thập phân là đủ
    cho cosine; cùng dạng Postgres in ra khi SELECT embedding)."""
    return "[" + ",".join(f"{float(x):.6f}".rstrip("0").rstrip(".") or "0"
                          for x in vec) + "]"


def schema_sql(dim: int) -> str:
    return SCHEMA_FILE.read_text(encoding="utf-8").replace("{dim}", str(dim))


def run_rag(structure: list, content: dict, doc, book: str, out_dir: Path,
            embedder, store=None, sources=SOURCES,
            chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
            overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
            cache_path: Path = None) -> dict:
    """Chunk + embed mọi topic đã có content -> output/rag_chunks.csv
    (+ output/rag_schema.sql) và (nếu có store) upsert vào pgvector.

    cache_path: cache vector cục bộ {slug: {hash, vectors}} — topic không đổi thì
    dùng lại vector, KHÔNG embed lại (kể cả khi chỉ xuất CSV, không có DB)."""
    import csv

    max_ok = embedder.max_tokens - 2                     # chừa [CLS]/[SEP]
    if chunk_tokens > max_ok:
        warn(f"--rag-chunk-tokens {chunk_tokens} > giới hạn model ({max_ok}) "
             f"-> hạ xuống {max_ok} (nếu không model sẽ cắt câm phần đuôi).")
        chunk_tokens = max_ok
    overlap_tokens = min(overlap_tokens, chunk_tokens // 2)

    stats = {"topics": 0, "embedded": 0, "db_written": 0, "db_skipped": 0,
             "chunks": 0, "by_source": {s: 0 for s in SOURCES}}
    cache = {}
    if cache_path and Path(cache_path).exists():
        cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rag_schema.sql").write_text(schema_sql(embedder.dim), encoding="utf-8")
    # UTF-8 KHÔNG BOM (khác topics.csv): BOM làm hỏng tên cột đầu khi import vào DB.
    with open(out_dir / "rag_chunks.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RAG_CSV_COLS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for row in structure:
            slug = row["topic_slug"]
            if slug not in content:
                continue
            chunks = chunk_topic(row, content[slug], doc, embedder.count_tokens,
                                 sources, chunk_tokens, overlap_tokens)
            if not chunks:
                warn(f"[rag] {slug}: không có chunk nào (content rỗng?) — bỏ qua.")
                continue
            stats["topics"] += 1
            stats["chunks"] += len(chunks)
            thash = topic_hash(chunks, embedder.model_name)
            hit = cache.get(slug)
            if hit and hit.get("hash") == thash and len(hit["vectors"]) == len(chunks):
                vectors = hit["vectors"]
            else:
                vectors = [[round(float(x), 6) for x in v] for v in
                           embedder.embed_passages([c["embed_text"] for c in chunks])]
                cache[slug] = {"hash": thash, "vectors": vectors}
                stats["embedded"] += 1
                log(f"   [rag     ] {slug}: embed {len(chunks)} chunk")
            for c, v in zip(chunks, vectors):
                stats["by_source"][c["source"]] += 1
                w.writerow({
                    "book": book, "module_slug": row["module_slug"],
                    "module_title": row.get("module_title"), "topic_slug": slug,
                    "topic_title": row.get("topic_title"), "level": row.get("level"),
                    "source": c["source"], "section": c["section"],
                    "page_start": c["page_start"], "page_end": c["page_end"],
                    "chunk_index": c["chunk_index"], "content": c["content"],
                    "token_count": c["token_count"], "topic_hash": thash,
                    "embedding_model": embedder.model_name,
                    "embedding": vector_literal(v)})
            if store is not None:
                if store.existing_hash(book, slug, embedder.model_name) == thash:
                    stats["db_skipped"] += 1
                else:
                    import numpy as np
                    store.replace_topic(book, row, embedder.model_name, thash, chunks,
                                        [np.asarray(v, dtype="float32") for v in vectors])
                    stats["db_written"] += 1
            if cache_path:     # lưu sau mỗi topic: đứt giữa chừng vẫn giữ phần đã embed
                Path(cache_path).write_text(json.dumps(cache), encoding="utf-8")
    return stats
