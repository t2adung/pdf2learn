# -*- coding: utf-8 -*-
"""html_render.py — Chụp HTML (chuỗi) thành PNG bằng headless Chromium
(Playwright). Dependency TUỲ CHỌN (không có trong requirements.txt) — pipeline
vẫn chạy bình thường không có ảnh infographic nếu chưa cài, xem
RendererUnavailable.

Cài đặt (chỉ cần nếu muốn có ảnh infographic):
    pip install playwright
    playwright install chromium

Vì sao 1 browser dùng chung cho cả lần chạy: khởi động Chromium tốn ~1-2s,
làm mỗi topic tự mở/đóng browser riêng sẽ chậm không cần thiết — main.py
tạo 1 HtmlRenderer TRƯỚC vòng lặp topic, dùng lại page cho mọi topic, đóng
SAU vòng lặp (xem finally trong main.py).
"""


class RendererUnavailable(RuntimeError):
    pass


class HtmlRenderer:
    def __init__(self, width: int = 860):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RendererUnavailable(
                "Chưa cài Playwright — bỏ qua ảnh infographic. Muốn có ảnh, cài:\n"
                "    pip install playwright && playwright install chromium\n"
                "(hoặc thêm --no-infographic để tắt hẳn, khỏi hiện cảnh báo này)")
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch()
        except Exception as e:
            self._pw.stop()
            raise RendererUnavailable(
                f"Không khởi động được Chromium ({e}).\n"
                "    Chạy: playwright install chromium")
        self._page = self._browser.new_page(viewport={"width": width, "height": 100})

    def render_png(self, html: str) -> bytes:
        """HTML -> PNG bytes, chiều cao tự co theo nội dung (full_page)."""
        self._page.set_content(html, wait_until="load")
        return self._page.screenshot(full_page=True, type="png")

    def close(self):
        try:
            self._page.close()
            self._browser.close()
        finally:
            self._pw.stop()
