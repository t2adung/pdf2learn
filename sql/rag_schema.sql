-- pdf2learn — kho vector cho RAG (PostgreSQL + pgvector >= 0.5, chạy được trên Supabase).
-- stage_rag.py tự chạy file này (idempotent) khi bật --rag / --rag-only.
-- {dim} = số chiều embedding của model (gte-small = 384); code tự thay trước khi
-- chạy. Muốn chạy tay (vd SQL editor của Supabase): thay {dim} bằng 384 rồi chạy.

create extension if not exists vector;

create table if not exists rag_chunks (
    id              bigserial primary key,
    book            text        not null,  -- tên PDF (stem), = thư mục runs/<book>
    module_slug     text        not null,
    module_title    text,
    topic_slug      text        not null,
    topic_title     text,
    level           text,
    source          text        not null check (source in ('lesson', 'book')),
    section         text,                  -- heading mục bài học / "Trang N"
    page_start      int,
    page_end        int,
    chunk_index     int         not null,  -- thứ tự chunk trong topic
    content         text        not null,  -- text chunk (không gồm header ngữ cảnh)
    token_count     int,                   -- token theo tokenizer của model (gồm header)
    topic_hash      text        not null,  -- hash toàn bộ chunk của topic -> bỏ qua nếu không đổi
    embedding_model text        not null,
    embedding       vector({dim}) not null,
    created_at      timestamptz not null default now(),
    unique (book, topic_slug, embedding_model, chunk_index)
);

-- HNSW + cosine: embedding đã normalize nên cosine ~ inner product; HNSW
-- không cần "train" như IVFFlat => thêm dữ liệu dần (resume theo topic) vẫn tốt.
create index if not exists rag_chunks_embedding_hnsw
    on rag_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists rag_chunks_book_topic
    on rag_chunks (book, topic_slug, embedding_model);

-- Truy vấn top-k cho RAG (gọi được từ SQL, Supabase RPC, hoặc rag_search.py).
create or replace function match_rag_chunks(
    query_embedding vector({dim}),
    match_count     int  default 5,
    filter_book     text default null,
    filter_topic    text default null,
    filter_model    text default null
) returns table (
    id bigint, book text, module_slug text, topic_slug text, topic_title text,
    source text, section text, page_start int, page_end int,
    content text, similarity float
)
language sql stable as $$
    select c.id, c.book, c.module_slug, c.topic_slug, c.topic_title,
           c.source, c.section, c.page_start, c.page_end, c.content,
           1 - (c.embedding <=> query_embedding) as similarity
    from rag_chunks c
    where (filter_book  is null or c.book = filter_book)
      and (filter_topic is null or c.topic_slug = filter_topic)
      and (filter_model is null or c.embedding_model = filter_model)
    order by c.embedding <=> query_embedding
    limit match_count;
$$;
