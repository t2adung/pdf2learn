Chuyển lên cloud miễn phí thì có 3 con đường thực tế — chọn theo mức độ "tự động hoá" bạn muốn, và tin vui là con đường dễ nhất lại khớp hoàn hảo với flow Google Drive inbox/outbox đã thiết kế cho Cowork:

| Giải pháp | Free thật không? | Hợp với | Điểm yếu |
|---|---|---|---|
| **Google Colab** (khuyên dùng) | Có, vô thời hạn | Chạy thủ công mỗi khi có sách mới | Phiên ngắt khi treo lâu (resume của tool xử đẹp) |
| **GitHub Actions** | 2.000 phút/tháng private repo | Tự động hoá: đẩy PDF lên là chạy | Setup nhiều hơn, phải lo lưu cache `runs/` |
| **Oracle Cloud Always Free VM** | Có (ARM 4 CPU/24GB) | Server 24/7 — chính là chỗ đặt bot Telegram/Zalo đã bàn, khỏi cần Mac ở nhà | Phải tự quản server, đăng ký hơi khó |

## Con đường 1 — Google Colab (làm được trong 15 phút)

Điểm ăn tiền của Colab với bài toán này: **mount được Google Drive làm ổ đĩa**, nghĩa là thư mục `runs/` (toàn bộ cache/tiến độ) sống trên Drive — phiên Colab chết, quota Gemini hết ngày, mai mở notebook chạy lại là resume tiếp, đúng nhịp "mỗi ngày một ít quota" bạn đang theo. Máy Mac từ nay khỏi liên quan.

**Setup một lần:**

1. Upload thư mục `pdf2learn` (code) lên Drive, ví dụ `MyDrive/pdf2learn`. PDF cần xử lý bỏ vào `MyDrive/pdf2learn-inbox`.
2. Vào [colab.research.google.com](https://colab.research.google.com) → New notebook.
3. Lưu API key đúng cách: bấm **icon chìa khoá 🔑 (Secrets) ở sidebar trái** → Add secret, tên `GEMINI_API_KEY`, dán key, bật "Notebook access". Đây là cách chuẩn — **tuyệt đối không dán key thẳng vào cell**, vì notebook hay được share/copy và key sẽ đi theo.

**Notebook 3 cell:**

```python
# Cell 1 — mount Drive + cài dependency (chạy lại mỗi phiên, ~30 giây)
from google.colab import drive
drive.mount('/content/drive')
%pip -q install pymupdf requests
```

```python
# Cell 2 — nạp API key từ Secrets
import os
from google.colab import userdata
os.environ['GEMINI_API_KEY'] = userdata.get('GEMINI_API_KEY')
# nếu dùng --review: os.environ['GROQ_API_KEY'] = userdata.get('GROQ_API_KEY')
```

```python
# Cell 3 — chạy pipeline; runs/ nằm trên Drive nên tiến độ bất tử
%cd /content/drive/MyDrive/pdf2learn
!python3 main.py "/content/drive/MyDrive/pdf2learn-inbox/lsdl-lop6.pdf" --level "Lớp 6" --no-images
```

Output nằm luôn trên Drive tại `MyDrive/pdf2learn/runs/lsdl-lop6/output/` — mở từ điện thoại, tải batch về test, không cần bước copy nào. Hết quota giữa chừng? Đóng tab đi ngủ, mai mở notebook bấm Runtime → Run all, 3 topic đã xong tự bỏ qua.

Hai lưu ý vận hành: Colab ngắt phiên nếu treo không tương tác (~90 phút) — sách 200 trang chạy ~30 phút nên thường thoát trước, nhưng nếu bị ngắt thì cũng chỉ là một lần resume; và môi trường Colab là Python 3.10+ ổn định có sẵn wheel pymupdf — nghĩa là **cả chuỗi lỗi venv/3.9/3.14 bạn vật lộn mấy hôm nay biến mất sạch**, đó mới là lợi ích lớn nhất của cloud ở đây.

## Con đường 2 — GitHub Actions (khi muốn "đẩy PDF là tự chạy")

Phác kiến trúc để bạn hình dung: repo private chứa code, key để trong **Repository Secrets**, một workflow `workflow_dispatch` (bấm nút chạy tay, nhận input tên file) hoặc trigger khi push PDF vào thư mục `inbox/`. Job: checkout → `pip install` → chạy `main.py` → upload `output/` làm **artifact** (tải về từ tab Actions) → commit `runs/work/` ngược lại repo để giữ resume. Giới hạn free: 2.000 phút/tháng và job tối đa 6 giờ — dư dả cho vài cuốn sách/tháng. Đáng làm khi quy trình đã ổn định và bạn muốn hands-off; còn đang giai đoạn tinh chỉnh prompt như hiện tại thì Colab lợi hơn vì thấy log tức thì.

## Con đường 3 — Oracle Always Free VM (nối lại giấc mơ bot chat)

Nhắc lại flow B hôm trước: bot Telegram/Zalo nhận PDF → chạy pipeline → trả kết quả. Rào cản khi đó là phải để Mac ở nhà chạy 24/7 + tunnel. VM always-free của Oracle xoá rào cản đó: server ARM chạy vĩnh viễn không tốn đồng nào, đặt cả pipeline lẫn bot listener lên đấy, webhook public sẵn không cần tunnel. Đây là bước "sản phẩm hoá" — khi nào bạn muốn người khác cũng gửi sách được thì quay lại đây, mình dựng chi tiết.

**Chốt:** bắt đầu bằng Colab ngay hôm nay (nhất là khi máy bạn còn đang kẹt lỗi cài đặt), GitHub Actions khi quy trình đã đóng băng, Oracle VM khi mở rộng cho nhiều người dùng.
