# -*- coding: utf-8 -*-
"""test_claude_cli.py — Nghiệm thu backend Claude CLI KHÔNG cần lệnh `claude` thật.
Monkeypatch subprocess.run để giả lập envelope của `claude -p --output-format json`.
Chạy: python3 test_claude_cli.py   (0 chi phí)
"""
import json
import sys
import types

import claude_cli
from claude_cli import ClaudeCLI, ClaudeError, ClaudeLimitError

fails = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def fake_proc(stdout="", stderr="", rc=0):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)


def patch_run(fn):
    """Thay claude_cli.subprocess.run bằng fn(cmd, input=..., ...)."""
    claude_cli.subprocess.run = fn


# --- 1. generate_json parse envelope + ghi usage ---
captured = {}


def run_ok(cmd, input=None, capture_output=True, text=True, timeout=None):
    captured["prompt"] = input
    captured["cmd"] = cmd
    env = {"type": "result", "is_error": False,
           "result": '{"a": 1, "b": ["x", "y"]}',
           "usage": {"input_tokens": 123, "output_tokens": 45}}
    return fake_proc(stdout=json.dumps(env))


patch_run(run_ok)
c = ClaudeCLI(model="sonnet")
parts = [c.pdf_part(b"%PDF-1.4 fake", "bai-1.pdf"), {"text": "Sinh bài học."}]
res = c.generate_json(parts, {"type": "object"}, tag="content")
check("generate_json trả dict đã parse", res == {"a": 1, "b": ["x", "y"]}, str(res))
check("usage ghi nhận input/output tokens",
      c.usage.get("content") == {"calls": 1, "in": 123, "out": 45}, str(c.usage))
check("prompt có chèn đường dẫn file để Read", "bai-1.pdf" in captured["prompt"])
check("prompt có chèn schema JSON", '"type": "object"' in captured["prompt"]
      or '"type":"object"' in captured["prompt"])
check("cmd gọi claude -p --output-format json",
      captured["cmd"][:4] == ["claude", "-p", "--output-format", "json"], str(captured["cmd"]))
check("cmd có --add-dir (cấp quyền đọc thư mục tạm)", "--add-dir" in captured["cmd"])


# --- 2. strip ```-fence ---
def run_fenced(cmd, input=None, **kw):
    env = {"is_error": False, "result": '```json\n{"ok": true}\n```',
           "usage": {"input_tokens": 1, "output_tokens": 1}}
    return fake_proc(stdout=json.dumps(env))


patch_run(run_fenced)
check("parse được JSON dù bị bọc ```json",
      ClaudeCLI().generate_json([{"text": "x"}], {}, "t") == {"ok": True})


# --- 3. HẾT HẠN MỨC -> ClaudeLimitError ---
def run_limit(cmd, input=None, **kw):
    return fake_proc(stderr="Error: usage limit reached; resets at 1893456000", rc=1)


patch_run(run_limit)
try:
    ClaudeCLI(max_retries=1).generate_json([{"text": "x"}], {}, "content")
    check("hết hạn mức raise ClaudeLimitError", False, "không raise")
except ClaudeLimitError as e:
    check("hết hạn mức raise ClaudeLimitError", True)
    check("rút được reset_at từ thông báo", e.reset_at == 1893456000, str(e.reset_at))
except Exception as e:
    check("hết hạn mức raise ClaudeLimitError", False, f"raise {type(e).__name__}")


# --- 4. lỗi thật (rc!=0, không phải limit) -> ClaudeError, có retry ---
tries = {"n": 0}


def run_err(cmd, input=None, **kw):
    tries["n"] += 1
    return fake_proc(stderr="boom internal", rc=1)


patch_run(run_err)
claude_cli.time.sleep = lambda *_: None       # bỏ chờ backoff cho test nhanh
try:
    ClaudeCLI(max_retries=3).generate_json([{"text": "x"}], {}, "content")
    check("lỗi thật cuối cùng raise ClaudeError", False)
except ClaudeLimitError:
    check("lỗi thật KHÔNG bị nhầm thành limit", False)
except ClaudeError:
    check("lỗi thật cuối cùng raise ClaudeError", True)
    check("có retry đúng số lần (3)", tries["n"] == 3, f"{tries['n']} lần")


# --- 5. JSON hỏng -> thử sửa 1 lần rồi parse được ---
state = {"n": 0}


def run_repair(cmd, input=None, **kw):
    state["n"] += 1
    body = 'không phải json' if state["n"] == 1 else '{"fixed": 1}'
    return fake_proc(stdout=json.dumps({"is_error": False, "result": body,
                                        "usage": {"input_tokens": 1, "output_tokens": 1}}))


patch_run(run_repair)
check("JSON hỏng -> sửa 1 lần rồi parse được",
      ClaudeCLI().generate_json([{"text": "x"}], {}, "content") == {"fixed": 1})

print()
if fails:
    print(f"❌ {len(fails)} check thất bại: {fails}")
    sys.exit(1)
print("✅ Tất cả check đã qua. 0 chi phí (không gọi `claude` thật).")
