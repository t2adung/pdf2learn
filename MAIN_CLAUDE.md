# Nhánh `main_claude` — pdf2learn dùng SUBSCRIPTION Claude + CLOUD (không cần máy local)

Đây là **nhánh chính** cho hướng vận hành:
- **AI = subscription Claude Max/Pro** (không dùng API key trả phí, 0đ phụ trội) qua
  Claude Code CLI `claude -p` — cờ `--backend claude`.
- **Chạy trên CLOUD, không cần bật máy local**: đọc PDF từ Google Drive, chạy
  pipeline trong môi trường Claude Code (web/remote), up kết quả lên Drive, lập lịch
  bằng Routine; hết hạn mức thì dừng, tới cửa sổ sau tự chạy tiếp.

## Cách chạy nhanh (thủ công)
```bash
# cần: đã cài Claude Code + `claude login` (Max/Pro)
python3 main.py sach.pdf --level "Lớp 6" --backend claude --toc-file toc/sach.toc.json
```
Hết hạn mức → dừng + export phần hoàn chỉnh (thoát mã 42); chạy lại chính lệnh khi
cửa sổ reset để resume theo topic.

## Lộ trình (theo kế hoạch)
- [x] **Phần A — backend Claude CLI** (`claude_cli.py`, `--backend claude`, thoát mã 42
      khi hết hạn mức). Test: `test_claude_cli.py`.
- [ ] **Phần C — tổ chức thư mục + trạng thái**: `runs/<stem>/work/STATUS.json`,
      `runs/INDEX.md`, `status.py` (suy trạng thái từ filesystem: chưa làm / đang chạy /
      tạm dừng hết hạn mức / xong / lỗi).
- [ ] **Phần D — chạy cloud không cần máy**: đọc/ghi Google Drive qua MCP; state nhỏ
      (cache + STATUS) commit vào git để resume qua các session ephemeral; lập lịch
      bằng Routine (mỗi lần fire = 1 cửa sổ hạn mức); ảnh lớn đẩy thẳng lên Drive.
- [ ] (tuỳ chọn) **Phần B — watcher local** cho ai muốn chạy trên máy nhà.

## Nguyên tắc tối ưu (subscription + tự động)
- TOC luôn dùng **bookmark / `--toc-file`** (0 token, tránh giới hạn số trang Read).
- Giữ **ảnh 0-token** (đính nguyên trang bằng code) và **tắt `--review`** trừ khi cần.
- Nhịp thực tế ~**1 cuốn / cửa sổ hạn mức 5h**; resume theo topic lo phần đứt quãng.

> Điểm cần kiểm chứng cho Phần D: `claude -p` (subscription) có gọi lồng được trong
> môi trường cloud không. Nếu không → cloud cần `ANTHROPIC_API_KEY` (trả phí) hoặc
> `--backend gemini`; còn chạy local thì `claude -p` chắc chắn hoạt động.
