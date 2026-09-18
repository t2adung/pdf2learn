# -*- coding: utf-8 -*-
"""Backend AI dùng SUBSCRIPTION Claude qua Claude Code CLI (`claude -p`).

Cùng interface với gemini.Gemini nên các stage KHÔNG phải sửa:
    generate_json(parts, schema, tag) -> dict
    generate_text(parts, tag) -> str
    pdf_part(bytes, name) / image_part(bytes, mime)
    usage (dict) + _record()

Cơ chế: mỗi lời gọi = 1 lần shell ra `claude -p --output-format json`. CLI dùng
đúng login Claude Max/Pro (subscription) trên máy — KHÔNG cần API key, KHÔNG tính
tiền theo token (chỉ ăn hạn mức subscription). PDF/ảnh được ghi ra file tạm rồi
để Claude đọc bằng công cụ Read (hỗ trợ PDF + ảnh).

Điều kiện: đã cài Claude Code và `claude login` bằng tài khoản Max/Pro.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from utils import log, warn

CLAUDE_DEFAULT_MODEL = "sonnet"      # đổi bằng --model opus nếu muốn
# Dấu hiệu HẾT HẠN MỨC subscription trong output/stderr của CLI.
_LIMIT_SIGNS = (
    "usage limit", "rate limit", "hết hạn mức", "limit reached",
    "resets at", "reset at", "please try again later", "429",
)


class ClaudeError(RuntimeError):
    """Lỗi chung khi gọi Claude CLI."""


class ClaudeLimitError(ClaudeError):
    """Hết hạn mức subscription (session) — nên dừng và chạy lại khi cửa sổ reset."""

    def __init__(self, msg, reset_at=None):
        super().__init__(msg)
        self.reset_at = reset_at          # epoch giây hoặc None


def _find_reset_at(text: str):
    """Cố rút mốc reset (epoch) từ thông báo lỗi CLI, nếu có. Best-effort."""
    if not text:
        return None
    # epoch (giây/mili) cạnh chữ "reset" — chấp nhận "resets_at": 1..., "resets at 1..."
    m = re.search(r'reset[s_ ]*at["\s:=]*(\d{9,13})', text, re.IGNORECASE)
    if m:
        v = int(m.group(1))
        return v / 1000 if v > 10**12 else v
    return None


class ClaudeCLI:
    def __init__(self, model: str = CLAUDE_DEFAULT_MODEL, interval: float = 0.0,
                 max_retries: int = 4, timeout: int = 600):
        self.model = model
        self.interval = interval
        self.max_retries = max_retries
        self.timeout = timeout
        self.api_key = ""                 # để _build_reviewer/khác không lỗi
        self.usage = {}
        self._last_call = 0.0
        self._tmp = tempfile.mkdtemp(prefix="pdf2learn_claude_")
        self._n = 0
        if shutil.which("claude") is None:
            warn("Không tìm thấy lệnh `claude` trong PATH. Cài Claude Code và "
                 "`claude login` (Max/Pro) trước khi dùng --backend claude.")

    # ---------- usage ----------
    def _record(self, tag: str, tok_in: int, tok_out: int):
        u = self.usage.setdefault(tag, {"calls": 0, "in": 0, "out": 0})
        u["calls"] += 1
        u["in"] += int(tok_in or 0)
        u["out"] += int(tok_out or 0)

    def _throttle(self):
        if self.interval <= 0:
            return
        wait = self.interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    # ---------- parts (ghi file tạm để Claude đọc bằng Read) ----------
    def pdf_part(self, data: bytes, display_name: str = "doc.pdf") -> dict:
        self._n += 1
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", display_name) or "doc.pdf"
        p = os.path.join(self._tmp, f"part{self._n:03d}_{safe}")
        with open(p, "wb") as f:
            f.write(data)
        return {"_file": p, "_mime": "application/pdf"}

    def image_part(self, data: bytes, mime: str) -> dict:
        self._n += 1
        ext = "png" if "png" in (mime or "") else "jpg"
        p = os.path.join(self._tmp, f"part{self._n:03d}.{ext}")
        with open(p, "wb") as f:
            f.write(data)
        return {"_file": p, "_mime": mime}

    # ---------- dựng prompt ----------
    @staticmethod
    def _split_parts(parts: list):
        texts, files = [], []
        for pt in (parts or []):
            if isinstance(pt, dict) and "_file" in pt:
                files.append(pt["_file"])
            elif isinstance(pt, dict) and "text" in pt:
                texts.append(pt["text"])
        return texts, files

    def _build_prompt(self, parts: list, schema: dict = None) -> str:
        texts, files = self._split_parts(parts)
        out = []
        if files:
            out.append("Đọc kỹ (các) file đính kèm bằng công cụ Read:")
            out += [f"- {f}" for f in files]
            out.append("")
        out.append("\n".join(texts).strip())
        if schema is not None:
            out.append("")
            out.append("TRẢ VỀ DUY NHẤT một JSON hợp lệ, KHỚP CHÍNH XÁC schema dưới đây. "
                       "KHÔNG kèm giải thích, KHÔNG dùng ``` bao quanh:")
            out.append(json.dumps(schema, ensure_ascii=False))
        return "\n".join(out).strip()

    # ---------- gọi CLI ----------
    def _run(self, prompt: str) -> dict:
        # Prompt truyền LÀM THAM SỐ (claude -p "<prompt>") — ổn định hơn stdin và
        # khớp cách test tay. Prompt chỉ có text + đường dẫn file + schema (PDF là
        # file tham chiếu, KHÔNG nhúng) nên luôn nhỏ, không lo giới hạn độ dài argv.
        cmd = ["claude", "-p", prompt, "--output-format", "json",
               "--model", self.model,
               "--allowedTools", "Read",
               "--add-dir", self._tmp]
        try:
            proc = subprocess.run(cmd, capture_output=True,
                                  text=True, timeout=self.timeout)
        except FileNotFoundError:
            raise ClaudeError("Không chạy được lệnh `claude` (chưa cài Claude Code?).")
        except subprocess.TimeoutExpired:
            raise ClaudeError(f"`claude` quá thời gian ({self.timeout}s).")
        blob = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        # nhận diện hết hạn mức trước
        hay = f"{blob}\n{stderr}".lower()
        if proc.returncode != 0 and any(s in hay for s in _LIMIT_SIGNS):
            raise ClaudeLimitError(
                "Hết hạn mức Claude subscription. Chạy lại lệnh cũ khi cửa sổ reset "
                "— pipeline tự resume topic còn thiếu.",
                reset_at=_find_reset_at(f"{blob}\n{stderr}"))
        if proc.returncode != 0:
            raise ClaudeError(f"claude lỗi (rc={proc.returncode}): {stderr[:400] or blob[:400]}")
        try:
            env = json.loads(blob)
        except json.JSONDecodeError:
            raise ClaudeError(f"Không parse được output CLI: {blob[:300]}")
        if env.get("is_error"):
            res = str(env.get("result", ""))
            if any(s in res.lower() for s in _LIMIT_SIGNS):
                raise ClaudeLimitError("Hết hạn mức Claude subscription.",
                                       reset_at=_find_reset_at(res))
            raise ClaudeError(f"claude trả is_error: {res[:400]}")
        u = env.get("usage") or {}
        self._record_env(u)
        return env

    def _record_env(self, u: dict):
        # ghi tạm vào tag hiện tại qua closure không tiện -> để caller record.
        self._last_usage = (int(u.get("input_tokens", 0) or 0),
                            int(u.get("output_tokens", 0) or 0))

    # ---------- generate ----------
    def _generate(self, parts: list, schema, tag: str) -> str:
        prompt = self._build_prompt(parts, schema)
        backoff = 5.0
        last = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                env = self._run(prompt)
            except ClaudeLimitError:
                raise                      # hết hạn mức -> để pipeline dừng & resume
            except ClaudeError as e:
                last = e
                warn(f"[{tag}] claude lỗi, retry {attempt}/{self.max_retries} "
                     f"sau {backoff:.0f}s... ({e})")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            self._record(tag, *getattr(self, "_last_usage", (0, 0)))
            return env.get("result", "") or ""
        raise last or ClaudeError(f"[{tag}] hết số lần retry.")

    def generate_text(self, parts: list, tag: str, temperature: float = 0.4) -> str:
        return self._generate(parts, None, tag)

    def generate_json(self, parts: list, schema: dict, tag: str,
                      temperature: float = 0.3):
        text = self._generate(parts, schema, tag)
        return self._parse_json(text, parts, schema, tag)

    def _parse_json(self, text: str, parts, schema, tag: str):
        for candidate in (text, self._strip_fence(text)):
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue
        # thử 1 lần sửa: yêu cầu model chỉ trả JSON hợp lệ
        warn(f"[{tag}] output không phải JSON, thử sửa 1 lần...")
        fix_prompt = ("Đoạn dưới đây LẼ RA phải là JSON hợp lệ khớp schema nhưng bị "
                      "lỗi cú pháp. Trả về DUY NHẤT JSON hợp lệ, không giải thích, "
                      "không ```:\n\n" + text)
        fixed = self._generate([{"text": fix_prompt}], schema, tag + "_fix")
        try:
            return json.loads(self._strip_fence(fixed))
        except json.JSONDecodeError as e:
            raise ClaudeError(f"[{tag}] không parse được JSON kể cả sau khi sửa: {e}")

    @staticmethod
    def _strip_fence(text: str) -> str:
        t = (text or "").strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[-1] if "\n" in t else t
            t = t.removeprefix("json").removeprefix("JSON").strip()
            if t.endswith("```"):
                t = t[: t.rfind("```")]
        return t.strip()
