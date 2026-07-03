# -*- coding: utf-8 -*-
"""Client Gemini REST API + MockGemini cho chế độ --dry-run.

Thiết kế:
- generate_json(): structured output qua responseSchema -> luôn parse được JSON
- Retry với exponential backoff khi 429/5xx (free tier hay dính rate limit)
- PDF nhỏ (<15MB) gửi inline base64; lớn hơn thì upload qua Files API
"""
import base64
import json
import random
import re
import time
from typing import Optional

import requests

from utils import log, warn

API_ROOT = "https://generativelanguage.googleapis.com"
INLINE_LIMIT = 15 * 1024 * 1024  # 15MB


class GeminiError(RuntimeError):
    pass


class Gemini:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash",
                 interval: float = 6.0, max_retries: int = 6):
        self.api_key = api_key
        self.model = model
        self.interval = interval          # giãn cách giữa các request (free tier ~10 RPM)
        self.max_retries = max_retries
        self._last_call = 0.0
        self.usage = {}  # {tag: {"calls": n, "in": tokens, "out": tokens}}

    def _record(self, tag: str, tok_in: int, tok_out: int):
        u = self.usage.setdefault(tag, {"calls": 0, "in": 0, "out": 0})
        u["calls"] += 1
        u["in"] += int(tok_in or 0)
        u["out"] += int(tok_out or 0)

    # ---------- low level ----------
    def _throttle(self):
        wait = self.interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _post(self, url: str, payload: dict, headers: Optional[dict] = None,
              raw_body: Optional[bytes] = None) -> requests.Response:
        backoff = 5.0
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            if raw_body is not None:
                resp = requests.post(url, headers=headers, data=raw_body, timeout=300)
            else:
                resp = requests.post(url, headers=headers or {"Content-Type": "application/json"},
                                     json=payload, timeout=300)
            if resp.status_code in (429, 500, 502, 503):
                retry_after = resp.headers.get("Retry-After")
                sleep = float(retry_after) if retry_after else backoff
                sleep += random.uniform(0, 2)
                hint = ""
                if resp.status_code == 429:
                    body = resp.text
                    if "PerDay" in body:
                        raise GeminiError(
                            "HẾT QUOTA NGÀY (free tier). Retry vô ích — quota reset "
                            "lúc nửa đêm giờ Pacific (~14-15h chiều giờ VN). "
                            "Chạy lại CHÍNH LỆNH NÀY sau đó, tool tự resume phần còn lại.")
                    if "PerMinute" in body:
                        hint = " [giới hạn THEO PHÚT — tăng --interval hoặc dùng --dpi 110 để giảm token]"
                    m = re.search(r'"quotaId"\s*:\s*"([^"]+)"', body)
                    if m:
                        hint += f" (quotaId: {m.group(1)})"
                warn(f"HTTP {resp.status_code}, retry {attempt}/{self.max_retries} sau {sleep:.0f}s...{hint}")
                time.sleep(sleep)
                backoff = min(backoff * 2, 120)
                continue
            if not resp.ok:
                raise GeminiError(f"HTTP {resp.status_code}: {resp.text[:500]}")
            return resp
        raise GeminiError("Hết số lần retry (rate limit / lỗi server kéo dài).")

    # ---------- parts ----------
    def pdf_part(self, data: bytes, display_name: str = "doc.pdf") -> dict:
        if len(data) <= INLINE_LIMIT:
            return {"inlineData": {"mimeType": "application/pdf",
                                   "data": base64.b64encode(data).decode()}}
        uri = self.upload_file(data, "application/pdf", display_name)
        return {"fileData": {"mimeType": "application/pdf", "fileUri": uri}}

    @staticmethod
    def image_part(data: bytes, mime: str) -> dict:
        return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}

    # ---------- Files API (cho PDF > 15MB) ----------
    def upload_file(self, data: bytes, mime: str, display_name: str) -> str:
        log(f"   ↑ Upload {display_name} ({len(data)/1e6:.1f}MB) qua Files API...")
        start = requests.post(
            f"{API_ROOT}/upload/v1beta/files?key={self.api_key}",
            headers={
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(data)),
                "X-Goog-Upload-Header-Content-Type": mime,
                "Content-Type": "application/json",
            },
            json={"file": {"display_name": display_name}}, timeout=60)
        start.raise_for_status()
        upload_url = start.headers["X-Goog-Upload-URL"]
        done = requests.post(
            upload_url,
            headers={"X-Goog-Upload-Offset": "0",
                     "X-Goog-Upload-Command": "upload, finalize"},
            data=data, timeout=600)
        done.raise_for_status()
        info = done.json()["file"]
        # chờ file ACTIVE
        name = info["name"]
        for _ in range(60):
            if info.get("state") == "ACTIVE":
                return info["uri"]
            time.sleep(2)
            info = requests.get(f"{API_ROOT}/v1beta/files/{name.split('/')[-1]}?key={self.api_key}",
                                timeout=30).json()
        raise GeminiError(f"File {name} không chuyển sang ACTIVE.")

    # ---------- generate ----------
    def _generate(self, parts: list, gen_config: dict, tag: str) -> str:
        url = f"{API_ROOT}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {"contents": [{"role": "user", "parts": parts}],
                   "generationConfig": gen_config}
        resp = self._post(url, payload)
        data = resp.json()
        um = data.get("usageMetadata", {})
        self._record(tag, um.get("promptTokenCount", 0),
                     um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0))
        try:
            cands = data["candidates"]
            texts = [p["text"] for p in cands[0]["content"]["parts"] if "text" in p]
            if not texts:
                raise KeyError("no text parts")
            return "".join(texts)
        except (KeyError, IndexError):
            reason = data.get("candidates", [{}])[0].get("finishReason") or \
                     data.get("promptFeedback", {}).get("blockReason")
            raise GeminiError(f"[{tag}] Không nhận được text (finishReason={reason}). "
                              f"Raw: {json.dumps(data)[:500]}")

    def generate_text(self, parts: list, tag: str, temperature: float = 0.4) -> str:
        return self._generate(parts, {"temperature": temperature}, tag)

    def generate_json(self, parts: list, schema: dict, tag: str,
                      temperature: float = 0.3):
        text = self._generate(parts, {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        }, tag)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # dọn code fence nếu model lỡ thêm
            cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
            return json.loads(cleaned)


# ======================================================================
# MockGemini: chạy toàn bộ pipeline KHÔNG cần API key (--dry-run)
# Dùng để kiểm tra pipeline, format CSV, naming ảnh... trước khi tốn quota.
# ======================================================================
class MockGemini(Gemini):
    def __init__(self):
        super().__init__(api_key="mock", interval=0)

    def pdf_part(self, data: bytes, display_name: str = "doc.pdf") -> dict:
        return {"mock": f"pdf:{len(data)}bytes"}

    def generate_text(self, parts, tag, temperature=0.4):
        self._record(tag, 800, 300)
        if tag == "svg_diagram":
            return ('<svg xmlns="http://www.w3.org/2000/svg" width="480" height="200">'
                    '<rect x="10" y="10" width="200" height="60" fill="#e3f2fd" stroke="#1565c0"/>'
                    '<text x="30" y="45" font-size="14">Khái niệm A</text>'
                    '<line x1="210" y1="40" x2="270" y2="40" stroke="#333" marker-end="url(#a)"/>'
                    '<rect x="270" y="10" width="200" height="60" fill="#fff3e0" stroke="#e65100"/>'
                    '<text x="290" y="45" font-size="14">Khái niệm B</text></svg>')
        return "[mock text]"

    def generate_json(self, parts, schema, tag, temperature=0.3):
        self._record(tag, 1200, 450)
        if tag == "toc":
            return {"modules": [
                {"title": "Chương I – Mở đầu", "topics": [
                    {"title": "Bài 1. Giới thiệu", "page_start": 1, "page_end": 2},
                    {"title": "Bài 2. An toàn trong phòng thực hành", "page_start": 3, "page_end": 4},
                ]},
                {"title": "Chương II – Chất quanh ta", "topics": [
                    {"title": "Bài 3. Sự đa dạng của chất", "page_start": 5, "page_end": 6},
                ]},
            ]}
        if tag == "content":
            return {
                "content_markdown": (
                    "## Mục tiêu\n- Hiểu khái niệm cơ bản của bài học\n- Vận dụng vào ví dụ thực tế\n\n"
                    "## Nội dung chính\nĐây là nội dung tóm tắt (mock) được sinh từ các trang PDF của topic.\n\n"
                    "## Liên hệ thực tế\nVí dụ đời sống minh hoạ khái niệm.\n\n"
                    "## Ghi nhớ\n- Ý chính 1\n- Ý chính 2\n- Ý chính 3"),
                "key_points": [
                    "Khái niệm X là nền tảng của chủ đề",
                    "Tính chất Y phân biệt X với Z",
                    "Ứng dụng thực tế của X trong đời sống",
                ],
            }
        if tag == "content_fused":
            base = self.generate_json(parts, schema, "content")
            base["questions"] = self.generate_json(parts, schema, "questions")["questions"]
            return base
        if tag == "img_filter":
            return {"keep": [{"index": 0, "caption": "Hình minh hoạ khái niệm chính (mock)"}]}
        if tag == "questions":
            qs = []
            for i, kp in enumerate(["Khái niệm X", "Tính chất Y", "Ứng dụng X"], 1):
                qs.append({"question": f"Câu hỏi mock {i}: {kp} là gì?",
                           "A": "Phương án nhiễu 1", "B": "Phương án nhiễu 2",
                           "C": "Đáp án đúng (mock)", "D": "Phương án nhiễu 3",
                           "correct_answer": "C",
                           "explanation_vi": f"Giải thích vì sao đáp án đúng cho {kp}.",
                           "difficulty": (i % 3) + 1})
            return {"questions": qs}
        if tag == "review":
            return {"overall_score": 8,
                    "content_issues": [{"severity": "low",
                        "issue": "Phần Liên hệ thực tế hơi ngắn (mock)",
                        "suggestion": "Bổ sung 1 ví dụ gần gũi hơn"}],
                    "question_issues": [{"index": 1, "severity": "high",
                        "issue": "Đáp án khai báo C nhưng theo nội dung phải là B (mock)",
                        "suggestion": "Sửa correct_answer hoặc viết lại câu hỏi"}],
                    "coverage_gaps": ["Ứng dụng thực tế của X (mock)"]}
        if tag == "validate":
            # trả về đúng hết để pipeline đi tiếp
            n = 0
            for p in parts:
                if "text" in p:
                    n = p["text"].count("Câu ")
            return {"answers": [{"index": i, "answer": "C"} for i in range(max(n, 3))]}
        raise ValueError(f"MockGemini: tag không hỗ trợ: {tag}")


# ======================================================================
# OpenAICompatClient: gọi các API free khác (Groq, OpenRouter) làm reviewer.
# Cùng interface generate_json(parts, schema, tag) để stage code không phải
# biết đang nói chuyện với nhà cung cấp nào (adapter pattern).
# ======================================================================
class OpenAICompatClient:
    PRESETS = {
        # name: (base_url, default_model, env_key)
        "groq": ("https://api.groq.com/openai/v1",
                 "llama-3.3-70b-versatile", "GROQ_API_KEY"),
        "openrouter": ("https://openrouter.ai/api/v1",
                       "deepseek/deepseek-r1:free", "OPENROUTER_API_KEY"),
    }

    def __init__(self, preset: str, api_key: str, model: Optional[str] = None,
                 interval: float = 3.0, max_retries: int = 6):
        base_url, default_model, _ = self.PRESETS[preset]
        self.base_url = base_url
        self.model = model or default_model
        self.api_key = api_key
        self.interval = interval
        self.max_retries = max_retries
        self._last_call = 0.0
        self.usage = {}

    def _record(self, tag, tok_in, tok_out):
        u = self.usage.setdefault(tag, {"calls": 0, "in": 0, "out": 0})
        u["calls"] += 1
        u["in"] += int(tok_in or 0)
        u["out"] += int(tok_out or 0)

    def generate_json(self, parts: list, schema: dict, tag: str,
                      temperature: float = 0.2):
        texts = []
        for p in parts:
            if "text" not in p:
                raise GeminiError(f"[{tag}] Reviewer này chỉ nhận text, "
                                  "không đọc được PDF/ảnh (dùng --reviewer gemini-pro).")
            texts.append(p["text"])
        prompt = ("\n\n".join(texts)
                  + "\n\nCHỈ trả về một object JSON hợp lệ đúng cấu trúc sau, "
                    "không kèm giải thích, không markdown:\n"
                  + json.dumps(schema, ensure_ascii=False))
        backoff = 5.0
        for attempt in range(1, self.max_retries + 1):
            wait = self.interval - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model,
                      "messages": [{"role": "user", "content": prompt}],
                      "temperature": temperature},
                timeout=300)
            if resp.status_code in (429, 500, 502, 503):
                sleep = float(resp.headers.get("Retry-After") or backoff) + random.uniform(0, 2)
                warn(f"[reviewer] HTTP {resp.status_code}, retry {attempt}/{self.max_retries} sau {sleep:.0f}s...")
                time.sleep(sleep)
                backoff = min(backoff * 2, 120)
                continue
            if not resp.ok:
                raise GeminiError(f"[reviewer] HTTP {resp.status_code}: {resp.text[:500]}")
            body = resp.json()
            u = body.get("usage", {})
            self._record(tag, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
            text = body["choices"][0]["message"]["content"]
            return _parse_loose_json(text, tag)
        raise GeminiError("[reviewer] Hết số lần retry.")


def _parse_loose_json(text: str, tag: str):
    """Model không có structured output có thể kèm rác quanh JSON -> bóc tách."""
    text = text.strip()
    # bỏ khối <think>...</think> của model reasoning (DeepSeek R1)
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    for candidate in (text,
                      text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    raise GeminiError(f"[{tag}] Không bóc được JSON từ phản hồi reviewer: {text[:300]}")
