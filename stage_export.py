# -*- coding: utf-8 -*-
"""Stage 6: Export package cuối cùng.

output/
├── topics.csv        (UTF-8 BOM, đúng cột template)
├── multichoice.csv   (UTF-8 BOM, đúng cột template)
├── images/           (đã tạo ở Stage 4)
├── essay.csv         (UTF-8 BOM, câu hỏi tự luận — khi bật stage essay)
├── import-payload.json (topics + câu hỏi tự luận — khi bật stage essay)
└── manifest.json     (bản đồ đối soát cho người upload ảnh + QC)

Checklist validate:
- correct_answer ∈ {A,B,C,D}
- referential integrity: mọi topic_slug trong multichoice tồn tại trong topics
- cảnh báo topic có < MIN_QUESTIONS câu hỏi
"""
import csv
import datetime
import json

from export_json import compose_learning_object, dumps
from render_markdown import render
from utils import log, warn

TOPIC_COLS = ["module_slug", "module_title", "topic_slug", "topic_title",
              "order", "level", "page_start", "content"]
QUESTION_COLS = ["topic_slug", "question", "A", "B", "C", "D",
                 "correct_answer", "explanation_vi", "difficulty"]
MIN_QUESTIONS = 3
ESSAY_COLS = ["topic_slug", "question", "correct_answer", "explanation_vi",
              "difficulty"]
ESSAY_CSV_FILE = "essay.csv"
IMPORT_PAYLOAD_FILE = "import-payload.json"
DEFAULT_TEACHER_ID = "00000000-0000-0000-0000-000000000000"


def build_import_payload(structure: list, topic_contents: dict, essays: dict,
                         teacher_id: str = DEFAULT_TEACHER_ID) -> dict:
    """Payload import (topics + exercises tự luận) — khớp import-payload.sample.json.

    topic_contents: {topic_slug: giá trị cột content đã compose (giống topics.csv)}.
    Thứ tự key cố định theo file mẫu (deterministic, diff được giữa 2 lần chạy)."""
    topics, exercises = [], []
    for row in structure:
        slug = row["topic_slug"]
        topics.append({
            "module_slug": row["module_slug"],
            "module_title": row["module_title"],
            "topic_slug": slug,
            "topic_title": row["topic_title"],
            "order": row["order"],
            "level": row["level"],
            "content": topic_contents.get(slug, ""),
            "page_start": row.get("page_start"),
        })
        for q in essays.get(slug, []):
            exercises.append({
                "type": "essay",
                "topic_slug": slug,
                "question": q["question"],
                "correct_answer": q["correct_answer"],
                "explanation_vi": q.get("explanation_vi", ""),
                "difficulty": min(3, max(1, int(q.get("difficulty", 1)))),
            })
    return {"teacher_id": teacher_id, "topics": topics, "exercises": exercises}


def _compose_content(row: dict, entry: dict, images: list, questions: list,
                     content_format: str = "markdown",
                     subject: str = "", grade: str = "", density: str = "full") -> str:
    """Sinh giá trị cột `content` từ Learning Object (hoặc blob v1).

    content_format:
      - "markdown": render bằng code (render_markdown.py) — mặc định, cho
        frontend markdown-it/marked. Ảnh gắn ở section 🖼️, filename trần.
      - "json"    : JSON bài học theo format đích (export_json.py), NHÚNG quiz
        — compact 1 dòng để sống sót CSV round-trip.
    """
    if content_format == "json":
        lo = compose_learning_object(row, entry, questions,
                                     subject=subject, grade=grade)
        return dumps(lo, compact=True)
    if entry and "content_markdown" in entry:      # cache v1: giữ hành vi cũ
        md = entry["content_markdown"]
        if not images:
            return md
        lines = ["", "## Hình minh hoạ"]
        for img in images:
            lines.append("![{}]({})".format(img["caption"], img["file"]))
        return md.rstrip() + "\n" + "\n".join(lines)
    return render(entry or {}, images=images, density=density)


def export(structure: list, content: dict, images: dict, questions: dict,
           out_dir, pdf_name: str, model: str, only_slugs=None, label="",
           extra_warnings=None, content_format: str = "markdown",
           subject: str = "", grade: str = "", export_json: bool = False,
           density: str = "full", essays: dict = None,
           teacher_id: str = DEFAULT_TEACHER_ID):
    """only_slugs: nếu khác None, chỉ xuất các topic trong tập này (batch/delta export).
    content_format: "markdown" (mặc định) | "json" — xem _compose_content.
    export_json: ghi thêm json/{topic_slug}.json (format đích, pretty) cho mỗi topic.
    essays: {topic_slug: [câu tự luận]} — khác None thì ghi import-payload.json."""
    if only_slugs is not None:
        structure = [r for r in structure if r["topic_slug"] in only_slugs]
    out_dir.mkdir(parents=True, exist_ok=True)
    topic_slugs = set()
    topic_contents = {}
    problems = []

    # ---- topics.csv ----
    topics_path = out_dir / "topics.csv"
    with open(topics_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TOPIC_COLS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for row in structure:
            slug = row["topic_slug"]
            topic_slugs.add(slug)
            topic_contents[slug] = _compose_content(
                row, content.get(slug, {}), images.get(slug, []),
                questions.get(slug, []), content_format=content_format,
                subject=subject, grade=grade, density=density)
            w.writerow({
                "module_slug": row["module_slug"],
                "module_title": row["module_title"],
                "topic_slug": slug,
                "topic_title": row["topic_title"],
                "order": row["order"],
                "level": row["level"],
                "page_start": row["page_start"],
                "content": topic_contents[slug],
            })
            if export_json:
                lo = compose_learning_object(row, content.get(slug, {}),
                                             questions.get(slug, []),
                                             subject=subject, grade=grade)
                jdir = out_dir / "json"
                jdir.mkdir(parents=True, exist_ok=True)
                (jdir / f"{slug}.json").write_text(dumps(lo), encoding="utf-8")

    # ---- multichoice.csv ----
    mc_path = out_dir / "multichoice.csv"
    n_questions = 0
    with open(mc_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=QUESTION_COLS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for row in structure:
            slug = row["topic_slug"]
            qs = questions.get(slug, [])
            if len(qs) < MIN_QUESTIONS:
                problems.append(f"{slug}: chỉ có {len(qs)} câu hỏi (< {MIN_QUESTIONS})")
            for q in qs:
                if q["correct_answer"] not in "ABCD":
                    problems.append(f"{slug}: correct_answer không hợp lệ "
                                    f"({q['correct_answer']}) -> bỏ câu này")
                    continue
                if slug not in topic_slugs:
                    problems.append(f"multichoice tham chiếu slug lạ: {slug} -> bỏ")
                    continue
                w.writerow({"topic_slug": slug, "question": q["question"],
                            "A": q["A"], "B": q["B"], "C": q["C"], "D": q["D"],
                            "correct_answer": q["correct_answer"],
                            "explanation_vi": q["explanation_vi"],
                            "difficulty": q["difficulty"]})
                n_questions += 1

    # ---- import-payload.json (topics + câu hỏi tự luận) ----
    n_essays = 0
    if essays is not None:
        payload = build_import_payload(structure, topic_contents, essays,
                                       teacher_id=teacher_id)
        n_essays = len(payload["exercises"])
        for row in structure:
            if not essays.get(row["topic_slug"]):
                problems.append(f"{row['topic_slug']}: chưa có câu hỏi tự luận")
        (out_dir / IMPORT_PAYLOAD_FILE).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        # essay.csv — cùng định dạng multichoice.csv (UTF-8 BOM), 1 dòng / câu
        with open(out_dir / ESSAY_CSV_FILE, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=ESSAY_COLS, quoting=csv.QUOTE_MINIMAL)
            w.writeheader()
            for ex in payload["exercises"]:
                w.writerow({k: ex[k] for k in ESSAY_COLS})

    # ---- manifest.json ----
    manifest = {
        "source_pdf": pdf_name,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "stats": {"modules": len({r["module_slug"] for r in structure}),
                  "topics": len(structure),
                  "questions": n_questions,
                  "essays": n_essays,
                  "images": sum(len(v) for v in images.values())},
        "topics": [{
            "topic_slug": r["topic_slug"],
            "topic_title": r["topic_title"],
            "pages": f"{r['page_start']}-{r['page_end']}",
            "n_questions": len(questions.get(r["topic_slug"], [])),
            "n_essays": len((essays or {}).get(r["topic_slug"], [])),
            "images": images.get(r["topic_slug"], []),
        } for r in structure],
        "warnings": problems + list(extra_warnings or []),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- báo cáo ----
    log(f"\n📦 Package{label}: {out_dir}")
    log(f"   topics.csv       : {len(structure)} topics")
    log(f"   multichoice.csv  : {n_questions} câu hỏi")
    log(f"   images/          : {manifest['stats']['images']} hình")
    if essays is not None:
        log(f"   {ESSAY_CSV_FILE:<17}: {n_essays} câu tự luận")
        log(f"   {IMPORT_PAYLOAD_FILE}: topics + câu tự luận (JSON)")
    if export_json:
        log(f"   json/            : {len(structure)} file bài học (format đích)")
    log(f"   manifest.json    : bản đồ đối soát")
    for p in problems:
        warn(p)
    return manifest
