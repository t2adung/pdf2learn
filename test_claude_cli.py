# -*- coding: utf-8 -*-
"""test_claude_cli.py — Nghiệm thu backend Claude CLI KHÔNG cần lệnh `claude` thật.
Monkeypatch subprocess.run để giả lập envelope của `claude -p --output-format json`.
Chạy: python3 test_claude_cli.py   (0 chi phí)
"""
import json
import os
import sys
import tempfile
import types

import claude_cli
from claude_cli import ClaudeCLI, ClaudeError, ClaudeLimitError
from utils import load_env

# Thư mục cấu hình giả cho tài khoản Claude riêng + biến API key "rò rỉ" từ shell
CFG = tempfile.mkdtemp(prefix="claude_cfg_")
os.environ["CLAUDE_CONFIG_DIR"] = CFG
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-should-be-stripped"

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


def run_ok(cmd, input=None, capture_output=True, text=True, timeout=None, env=None):
    captured["cmd"] = cmd
    captured["env"] = env
    captured["prompt"] = cmd[2] if len(cmd) > 2 else ""   # prompt là tham số sau -p
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
check("prompt truyền LÀM THAM SỐ (claude -p <prompt>)",
      captured["cmd"][:2] == ["claude", "-p"] and captured["prompt"],
      str(captured["cmd"][:3]))
check("prompt có chèn đường dẫn file để Read", "bai-1.pdf" in captured["prompt"])
check("prompt có chèn schema JSON", '"type": "object"' in captured["prompt"]
      or '"type":"object"' in captured["prompt"])
check("cmd có --output-format json",
      "--output-format" in captured["cmd"] and "json" in captured["cmd"], str(captured["cmd"]))
check("cmd có --add-dir (cấp quyền đọc thư mục tạm)", "--add-dir" in captured["cmd"])
check("`claude -p` nhận CLAUDE_CONFIG_DIR", captured["env"].get("CLAUDE_CONFIG_DIR") == CFG)
check("`claude -p` KHÔNG nhận ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY" not in captured["env"])


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


# --- 6. check_account: in tài khoản, chặn API key / chưa đăng nhập ---
def auth_run(payload, rc=0):
    def run(cmd, input=None, **kw):
        assert cmd[:3] == ["claude", "auth", "status"], cmd
        return fake_proc(stdout=json.dumps(payload), rc=rc)
    return run


patch_run(auth_run({"loggedIn": True, "authMethod": "claude.ai",
                    "email": "phu@example.com", "configDirectory": CFG}))
info = ClaudeCLI().check_account()
check("check_account trả về thông tin subscription", info.get("email") == "phu@example.com")

for method, rc in (("api_key", 0), ("api_key_helper", 0), ("none", 1)):
    patch_run(auth_run({"authMethod": method}, rc=rc))
    try:
        ClaudeCLI().check_account()
        check(f"check_account chặn authMethod={method}", False, "không raise")
    except ClaudeError:
        check(f"check_account chặn authMethod={method}", True)


patch_run(auth_run({"authMethod": "claude.ai", "configDirectory": "/khac/.claude"}))
try:
    ClaudeCLI().check_account()
    check("check_account chặn khi CLI dùng thư mục cấu hình khác", False, "không raise")
except ClaudeError:
    check("check_account chặn khi CLI dùng thư mục cấu hình khác", True)

patch_run(auth_run({"authMethod": "claude.ai"}))
for val, name in (("", "thiếu CLAUDE_CONFIG_DIR"), (CFG + "-chua-co", "thư mục chưa tồn tại")):
    os.environ["CLAUDE_CONFIG_DIR"] = val
    try:
        ClaudeCLI().check_account()
        check(f"check_account chặn khi {name}", False, "không raise")
    except ClaudeError:
        check(f"check_account chặn khi {name}", True)
os.environ["CLAUDE_CONFIG_DIR"] = CFG

home = os.path.expanduser("~")
os.environ["CLAUDE_CONFIG_DIR"] = "~/.claude-pdf2learn"
check("CLAUDE_CONFIG_DIR dạng ~ được đổi thành đường dẫn tuyệt đối",
      claude_cli.claude_env()["CLAUDE_CONFIG_DIR"] == os.path.join(home, ".claude-pdf2learn"))
os.environ["CLAUDE_CONFIG_DIR"] = CFG


def run_old_cli(cmd, input=None, **kw):
    return fake_proc(stdout="Unknown command: auth", rc=1)


patch_run(run_old_cli)
check("CLI cũ không có `auth status` -> chỉ cảnh báo, không dừng",
      ClaudeCLI().check_account() == {})


# --- 7. utils.load_env: .env thắng shell với CLAUDE_CONFIG_DIR, không ghi đè biến khác ---
envdir = tempfile.mkdtemp()
envfile = os.path.join(envdir, ".env")
with open(envfile, "w", encoding="utf-8") as f:
    f.write('# comment\nCLAUDE_CONFIG_DIR="/tu/env/.claude-pdf2learn"\n'
            "export GEMINI_API_KEY=tu-env\n")
os.environ["CLAUDE_CONFIG_DIR"] = "/tu/shell/.claude"
os.environ["GEMINI_API_KEY"] = "tu-shell"
load_env(envfile)
check("load_env: CLAUDE_CONFIG_DIR lấy từ .env (thắng shell)",
      os.environ["CLAUDE_CONFIG_DIR"] == "/tu/env/.claude-pdf2learn")
check("load_env: biến khác giữ giá trị shell", os.environ["GEMINI_API_KEY"] == "tu-shell")
import utils
from pathlib import Path
check("load_env: parser dự phòng (không có python-dotenv) đọc đúng",
      utils._parse_env_file(Path(envfile)) == {"CLAUDE_CONFIG_DIR": "/tu/env/.claude-pdf2learn",
                                                "GEMINI_API_KEY": "tu-env"})

print()
if fails:
    print(f"❌ {len(fails)} check thất bại: {fails}")
    sys.exit(1)
print("✅ Tất cả check đã qua. 0 chi phí (không gọi `claude` thật).")
