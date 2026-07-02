# -*- coding: utf-8 -*-
"""Stage 6: Export package cuối cùng.

output/
├── topics.csv        (UTF-8 BOM, đúng cột template)
├── multichoice.csv   (UTF-8 BOM, đúng cột template)
├── images/           (đã tạo ở Stage 4)
└── manifest.json     (bản đồ đối soát cho người upload ảnh + QC)

Checklist validate:
- correct_answer ∈ {A,B,C,D}
- referential integrity: mọi topic_slug trong multichoice tồn tại trong topics
- cảnh báo topic có < MIN_QUESTIONS câu hỏi
"""
import csv
import datetime
import json

from utils import log, warn

TOPIC_COLS = ["module_slug", "module_title", "topic_slug", "topic_title",
              "order", "level", "content"]
QUESTION_COLS = ["topic_slug", "question", "A", "B", "C", "D",
                 "correct_answer", "explanation_vi", "difficulty"]
MIN_QUESTIONS = 3


def _compose_content(markdown: str, images: list) -> str:
    """Ghép section hình minh hoạ vào cuối content. Ảnh tham chiếu bằng
    filename trần (ảnh được upload riêng vào hệ thống)."""
    if not images:
        return markdown
    lines = ["", "## Hình minh hoạ"]
    for img in images:
        lines.append(f"![{img['caption']}]({img['file']})")
    return markdown.rstrip() + "\n" + "\n".join(lines)


def export(structure: list, content: dict, images: dict, questions: dict,
           out_dir, pdf_name: str, model: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    topic_slugs = set()
    problems = []

    # ---- topics.csv ----
    topics_path = out_dir / "topics.csv"
    with open(topics_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TOPIC_COLS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for row in structure:
            slug = row["topic_slug"]
            topic_slugs.add(slug)
            c = content.get(slug, {})
            w.writerow({
                "module_slug": row["module_slug"],
                "module_title": row["module_title"],
                "topic_slug": slug,
                "topic_title": row["topic_title"],
                "order": row["order"],
                "level": row["level"],
                "content": _compose_content(c.get("content_markdown", ""),
                                            images.get(slug, [])),
            })

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

    # ---- manifest.json ----
    manifest = {
        "source_pdf": pdf_name,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "stats": {"modules": len({r["module_slug"] for r in structure}),
                  "topics": len(structure),
                  "questions": n_questions,
                  "images": sum(len(v) for v in images.values())},
        "topics": [{
            "topic_slug": r["topic_slug"],
            "topic_title": r["topic_title"],
            "pages": f"{r['page_start']}-{r['page_end']}",
            "n_questions": len(questions.get(r["topic_slug"], [])),
            "images": images.get(r["topic_slug"], []),
        } for r in structure],
        "warnings": problems,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- báo cáo ----
    log(f"\n📦 Package: {out_dir}")
    log(f"   topics.csv       : {len(structure)} topics")
    log(f"   multichoice.csv  : {n_questions} câu hỏi")
    log(f"   images/          : {manifest['stats']['images']} hình")
    log(f"   manifest.json    : bản đồ đối soát")
    for p in problems:
        warn(p)
    return manifest
