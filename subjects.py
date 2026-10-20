# -*- coding: utf-8 -*-
"""Nhận diện MÔN HỌC + hướng dẫn prompt riêng theo môn (thuần code, 0 token).

Vì sao cần: prompt chung (định nghĩa / liệt kê / giải thích) hợp với môn "học
thuộc" như KHTN, Lịch sử... nhưng lệch với Toán (cần bài tập tính toán có lời
giải), Ngữ văn (đọc hiểu, biện pháp tu từ), Tiếng Anh (ngữ pháp, từ vựng)...
Mỗi môn có 1 SubjectProfile gồm từ khoá nhận diện + 3 đoạn hướng dẫn chèn vào
cuối prompt content / trắc nghiệm / tự luận (+ gợi ý cho pass giải lại đáp án).

Thứ tự nhận diện (detect_subject):
  1. --subject-profile <key> chỉ định thẳng (khác "auto")
  2. --subject "Toán"           (tên môn người dùng khai báo)
  3. tên file PDF               (vd sgk-toan-4.pdf, khtn-lop6.pdf)
  4. tên chương/bài trong mục lục (chấm điểm theo từ khoá chuyên môn)
  Không nhận ra -> profile "general": KHÔNG chèn gì, giữ nguyên prompt chung.
"""
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class SubjectProfile:
    key: str
    name: str                       # tên môn hiển thị / ghi vào JSON
    names: tuple = ()               # từ khoá TÊN MÔN (khớp --subject, tên file)
    title_keywords: tuple = ()      # từ khoá CHUYÊN MÔN (khớp tên chương/bài)
    content: str = ""               # chèn vào CONTENT_PROMPT
    mcq: str = ""                   # chèn vào QUESTIONS_PROMPT
    essay: str = ""                 # chèn vào ESSAY_PROMPT
    validate: str = ""              # chèn vào VALIDATE_PROMPT


GENERAL = SubjectProfile(key="general", name="")

PROFILES = {p.key: p for p in [
    SubjectProfile(
        key="toan", name="Toán",
        names=("toan", "toan hoc", "dai so", "hinh hoc", "giai tich", "math",
               "maths", "mathematics"),
        title_keywords=("phan so", "so thap phan", "so nguyen", "so tu nhien",
                        "phep cong", "phep tru", "phep nhan", "phep chia",
                        "phuong trinh", "bat phuong trinh", "ham so", "da thuc",
                        "tam giac", "hinh vuong", "hinh chu nhat", "hinh tron",
                        "dien tich", "the tich", "chu vi", "goc nhon", "goc vuong", "goc tu",
                        "ti so", "ti le", "luy thua", "can bac", "uoc chung",
                        "boi chung", "thong ke", "xac suat",
                        "bieu thuc", "dao ham", "tich phan", "vecto", "do dai"),
        content=(
            "- sections: nêu QUY TẮC / CÔNG THỨC / CÁC BƯỚC GIẢI; mỗi mục nên kèm 1 VÍ "
            "DỤ MẪU có số cụ thể và kết quả (vd \"3/4 + 1/4 = 4/4 = 1\").\n"
            "- Viết công thức bằng ký hiệu text thuần dễ đọc: x^2, căn(2), 3/4, ≤, ≥, ×, ÷ "
            "(không LaTeX).\n"
            "- key_terms: khái niệm/tính chất toán học kèm example là phép tính cụ thể.\n"
            "- key_points: ưu tiên các KỸ NĂNG kiểm tra được bằng bài tập (\"Muốn cộng "
            "hai phân số khác mẫu, ta quy đồng mẫu rồi cộng tử\").\n"
            "- real_life: tình huống có con số (mua bán, đo đạc, chia phần...)."),
        mcq=(
            "- Phần lớn câu hỏi là BÀI TẬP TÍNH TOÁN / VẬN DỤNG QUY TẮC với số cụ thể, "
            "chỉ ít câu hỏi lý thuyết thuần.\n"
            "- Phương án nhiễu = kết quả của LỖI TÍNH SAI THƯỜNG GẶP (quên quy đồng, "
            "nhầm dấu, nhầm thứ tự phép tính, nhầm công thức chu vi/diện tích...).\n"
            "- TỰ TÍNH LẠI đáp án đúng trước khi ghi; số liệu chọn sao cho tính nhẩm "
            "hoặc tính tay được ở trình độ này.\n"
            "- explanation_vi: trình bày các bước tính ngắn gọn dẫn tới đáp án."),
        essay=(
            "- Thay dạng định nghĩa/liệt kê bằng chủ yếu BÀI TẬP: \"Tính...\", \"Tìm x...\", "
            "\"Giải bài toán...\", \"So sánh...\", bài toán có lời văn — ưu tiên lấy từ "
            "mục Luyện tập / Vận dụng / Bài tập của sách. Chỉ 1-2 câu hỏi lý thuyết "
            "(phát biểu quy tắc, công thức).\n"
            "- correct_answer: LỜI GIẢI TỪNG BƯỚC + đáp số cuối (được phép <= 100 từ).\n"
            "- explanation_vi: hướng dẫn chấm theo bước (vd \"đúng bước quy đồng: 0,5đ; "
            "đúng kết quả: 0,5đ\").\n"
            "- BỎ QUA bài cần đọc số liệu từ hình vẽ mà không diễn đạt lại được bằng lời."),
        validate="- Với câu tính toán: TỰ TÍNH LẠI từng bước rồi mới chọn đáp án.",
    ),
    SubjectProfile(
        key="ngu-van", name="Ngữ văn",
        names=("ngu van", "van hoc", "tieng viet", "van"),
        title_keywords=("doc hieu", "van ban", "bai tho", "truyen", "tuy but", "ki su",
                        "ky su", "nghi luan", "bien phap tu tu", "an du",
                        "hoan du", "nhan hoa", "tu ghep", "tu lay", "dau cau",
                        "tap lam van", "chinh ta", "luyen tu va cau", "ke chuyen",
                        "tac gia", "nhan vat", "viet doan", "viet bai"),
        content=(
            "- Với bài ĐỌC HIỂU văn bản: sections gồm thông tin tác giả - tác phẩm, nội "
            "dung chính, đặc sắc nghệ thuật, thông điệp; trích dẫn ngắn câu thơ/câu văn "
            "tiêu biểu trong sách (không bịa trích dẫn).\n"
            "- Với bài TIẾNG VIỆT (từ, câu, biện pháp tu từ): nêu khái niệm + dấu hiệu "
            "nhận biết + ví dụ lấy từ sách.\n"
            "- Với bài VIẾT/NÓI: nêu yêu cầu, dàn ý các bước.\n"
            "- key_points: kiến thức kiểm tra được (thể loại, phương thức biểu đạt, biện "
            "pháp tu từ và tác dụng, chi tiết/nhân vật quan trọng)."),
        mcq=(
            "- Hỏi về: tác giả - tác phẩm, thể loại, phương thức biểu đạt, nhân vật, "
            "chi tiết, ý nghĩa, NHẬN DIỆN biện pháp tu từ / từ loại / kiểu câu trong ví "
            "dụ cụ thể (trích ngắn trong câu hỏi).\n"
            "- Phương án nhiễu: các biện pháp tu từ / thể loại / nhân vật dễ nhầm lẫn.\n"
            "- Không hỏi cảm nhận chủ quan không có đáp án duy nhất."),
        essay=(
            "- Dạng ưu tiên: ĐỌC HIỂU (nội dung chính, thông điệp, chi tiết), NHẬN DIỆN "
            "+ NÊU TÁC DỤNG biện pháp tu từ trong câu trích, phân tích ngắn chi tiết / "
            "nhân vật, thực hành Tiếng Việt (tìm từ, đặt câu, xác định thành phần câu).\n"
            "- Câu hỏi phải tự chứa đoạn trích cần thiết (trích ngắn, đúng nguyên văn sách).\n"
            "- correct_answer: các Ý CHÍNH cần có; câu mở/cảm nhận thì nêu định hướng.\n"
            "- explanation_vi: tiêu chí chấm (ý bắt buộc, chấp nhận diễn đạt khác)."),
    ),
    SubjectProfile(
        key="tieng-anh", name="Tiếng Anh",
        names=("tieng anh", "anh van", "english", "global success", "i learn smart",
               "friends plus", "right on", "explore english"),
        title_keywords=("unit", "grammar", "vocabulary", "pronunciation", "reading",
                        "listening", "speaking", "writing", "present simple",
                        "past simple", "present perfect", "future", "tense",
                        "comparative", "superlative", "passive", "conditional",
                        "getting started", "a closer look", "skills", "review"),
        content=(
            "- TRỌNG TÂM: MẸO làm bài NGỮ PHÁP + PHÁT ÂM cho các điểm có trong unit "
            "(từ vựng chỉ tối đa 1 mục ngắn). Giải thích bằng TIẾNG VIỆT; công thức, ví "
            "dụ bằng TIẾNG ANH; phiên âm IPA đặt trong /.../.\n"
            "- Được bổ sung mẹo / quy tắc ngữ pháp CHUẨN (kiến thức phổ thông) cho điểm "
            "ngữ pháp có trong unit, kể cả khi sách không ghi mẹo — nhưng KHÔNG dạy điểm "
            "ngữ pháp mà unit không có.\n"
            "- Mỗi điểm ngữ pháp 1 section theo khung: Công thức (khẳng định / phủ định / "
            "nghi vấn) → Cách dùng → DẤU HIỆU NHẬN BIẾT → MẸO nhớ / LỖI hay sai → ví dụ.\n"
            "- Gợi ý nội dung mẹo theo dạng bài:\n"
            "  + Phát âm -s/-es: /s/ sau âm vô thanh /p, t, k, f, θ/; /ɪz/ sau /s, z, ʃ, tʃ, "
            "ʒ, dʒ/ (chữ s, x, z, sh, ch, ge, ce); còn lại /z/. Có mẹo nhớ phổ biến (vd "
            "\"Thời phong kiến phương Tây\" cho /s/) thì nêu.\n"
            "  + Phát âm -ed: /ɪd/ sau /t, d/; /t/ sau âm vô thanh /p, k, f, s, ʃ, tʃ, θ/; "
            "còn lại /d/. Lưu ý: xét ÂM cuối, không xét chữ cái (vd laughed /t/).\n"
            "  + Các thì: công thức + dấu hiệu (always, usually → hiện tại đơn; now, at "
            "the moment, Look! → hiện tại tiếp diễn; since, for, already, yet, just → "
            "hiện tại hoàn thành; yesterday, ago, last → quá khứ đơn...) + phân biệt cặp "
            "thì dễ nhầm.\n"
            "  + Các dạng câu (bị động, câu điều kiện, câu tường thuật, mệnh đề quan hệ, "
            "so sánh, câu ước, câu hỏi đuôi, used to, V-ing / to V...): công thức + CÁC "
            "BƯỚC biến đổi câu + lỗi hay sai.\n"
            "- key_terms: tên quy tắc / cấu trúc; definition = công thức hoặc quy tắc "
            "ngắn; example = câu tiếng Anh.\n"
            "- key_points: mỗi công thức / dấu hiệu / mẹo là 1 ý kiểm tra được bằng bài tập.\n"
            "- mindmap: root = điểm ngữ pháp chính; branches kiểu Công thức / Cách dùng / "
            "Dấu hiệu / Mẹo - lỗi sai.\n"
            "- hook: một lỗi hay gặp hoặc câu đố nhỏ (vd \"Vì sao watched đọc /t/ còn "
            "wanted đọc /ɪd/?\")."),
        mcq=(
            "- 100% TIẾNG ANH, KHÔNG dùng tiếng Việt ở bất kỳ field nào: lời dẫn câu hỏi, "
            "phương án VÀ CẢ explanation_vi (bỏ quy tắc \"explanation_vi bằng tiếng Việt\" "
            "ở trên). Lời dẫn kiểu: \"Choose the word whose underlined part is pronounced "
            "differently.\", \"Choose the correct answer to complete the sentence.\"\n"
            "- explanation_vi (viết bằng tiếng Anh) PHẢI nêu MẸO / DẤU HIỆU giúp chọn "
            "đáp án (vd \"'since' + a point in time → present perfect\").\n"
            "- Dạng ưu tiên: chọn từ có phần gạch chân phát âm khác (-s/-es, -ed; phần "
            "gạch chân viết HOA, vd \"watchED\"), chia động từ theo dấu hiệu thời gian, "
            "chọn cấu trúc câu đúng (bị động, điều kiện, so sánh...), chọn câu viết lại "
            "đúng nghĩa, tìm lỗi sai.\n"
            "- Phương án nhiễu: lỗi người Việt hay mắc (sai thì, quên -s ngôi thứ ba, xét "
            "chữ cái thay vì âm cuối khi đọc -ed, sai trật tự bị động, nhầm loại câu điều "
            "kiện, sai dạng từ)."),
        essay=(
            "- Tập trung vào MẸO NGỮ PHÁP / PHÁT ÂM của unit. Trộn 2 nhóm:\n"
            "  + ~1/3 câu QUY TẮC - MẸO: \"Nêu quy tắc phát âm đuôi -ed.\", \"Nêu dấu "
            "hiệu nhận biết thì hiện tại hoàn thành.\", \"Phân biệt thì hiện tại hoàn "
            "thành và quá khứ đơn.\", \"Nêu các bước chuyển câu chủ động sang bị động.\"\n"
            "  + ~2/3 câu VẬN DỤNG: xếp từ vào nhóm theo cách đọc -s/-es hoặc -ed, chia "
            "động từ trong ngoặc theo dấu hiệu, viết lại câu (bị động, điều kiện, tường "
            "thuật, so sánh...), tìm và sửa lỗi sai.\n"
            "- NGÔN NGỮ THỐNG NHẤT cho MỌI câu (bỏ quy tắc \"ngôn ngữ của tài liệu gốc\"):\n"
            "  + LỜI ĐỀ / YÊU CẦU luôn bằng TIẾNG VIỆT; chỉ NGỮ LIỆU (từ, câu cần làm) "
            "giữ TIẾNG ANH. Vd: \"Chia động từ trong ngoặc: She (live) here since 2010.\", "
            "\"Viết lại câu sau ở dạng bị động: They built this bridge in 1990.\", "
            "\"Xếp các từ sau theo cách đọc đuôi -ed: watched, wanted, played.\"\n"
            "  + KHÔNG viết lời đề bằng tiếng Anh (không \"Put the verb...\", \"Rewrite...\").\n"
            "  + correct_answer: phần đáp án tiếng Anh (câu / từ đúng; nhiều cách đúng thì "
            "liệt kê) + 1 câu TIẾNG VIỆT nêu quy tắc áp dụng. Vd: \"She has lived here "
            "since 2010. — Có 'since' → dùng thì hiện tại hoàn thành.\" Câu quy tắc - mẹo "
            "thì trả lời bằng tiếng Việt, ví dụ tiếng Anh.\n"
            "- explanation_vi: tiếng Việt — mẹo / dấu hiệu nhận biết + lỗi hay gặp, và "
            "tiêu chí chấm.\n"
            "- BỎ QUA bài nghe (listening), bài nói tự do và bài viết đoạn văn mở."),
        validate=("- Với câu phát âm / chia thì / biến đổi câu: áp dụng đúng quy tắc (xét "
                  "ÂM cuối, dấu hiệu thời gian, công thức) rồi mới chọn đáp án."),
    ),
    SubjectProfile(
        key="khoa-hoc", name="Khoa học tự nhiên",
        names=("khoa hoc tu nhien", "khtn", "khoa hoc", "vat li", "vat ly", "hoa hoc",
               "sinh hoc", "tu nhien va xa hoi", "science", "physics", "chemistry",
               "biology"),
        title_keywords=("te bao", "chat", "nguyen tu", "phan tu", "nguyen to",
                        "hon hop", "dung dich", "phan ung", "trong luc", "luc ma sat",
                        "nang luong",
                        "chuyen dong", "toc do", "anh sang", "am thanh", "dong dien",
                        "nhiet", "tu truong", "thuc vat", "dong vat", "vi khuan",
                        "virus", "sinh vat", "he sinh thai", "co the nguoi",
                        "trao doi chat", "quang hop", "ho hap", "di truyen",
                        "khong khi", "trai dat", "bau troi", "do luong"),
        content=(
            "- sections: khái niệm → đặc điểm/tính chất → quá trình/nguyên nhân-kết quả "
            "→ ứng dụng; nêu ĐƠN VỊ đo và CÔNG THỨC (text thuần) nếu sách có.\n"
            "- Mô tả thí nghiệm trong sách bằng lời: mục đích, cách làm ngắn, kết quả, "
            "kết luận (không bịa số liệu thí nghiệm).\n"
            "- real_life: hiện tượng tự nhiên / ứng dụng kĩ thuật / bảo vệ sức khoẻ, "
            "môi trường."),
        mcq=(
            "- Trộn: nhận biết khái niệm, giải thích HIỆN TƯỢNG thực tế, dự đoán kết quả "
            "thí nghiệm, bài tập tính toán đơn giản (công thức, đổi đơn vị) nếu bài có.\n"
            "- Phương án nhiễu: quan niệm sai phổ biến (vd \"vật nặng rơi nhanh hơn\", "
            "nhầm đơn vị, nhầm nguyên nhân - kết quả)."),
        essay=(
            "- Ngoài định nghĩa/liệt kê, ưu tiên GIẢI THÍCH HIỆN TƯỢNG (\"Vì sao...?\"), "
            "nêu vai trò/ứng dụng, so sánh hai đối tượng, và bài tập tính toán ngắn (nếu "
            "bài có công thức: correct_answer ghi các bước + đơn vị).\n"
            "- Câu hỏi thí nghiệm trong sách: chuyển thành câu \"Nêu kết quả và giải thích\" "
            "nếu sách đã cho đủ thông tin; nếu cần tự làm thí nghiệm thì bỏ qua."),
        validate="- Với câu có tính toán: tính lại và kiểm tra đơn vị trước khi chọn.",
    ),
    SubjectProfile(
        key="lich-su-dia-li", name="Lịch sử và Địa lí",
        names=("lich su va dia li", "lich su va dia ly", "lich su", "dia li", "dia ly",
               "history", "geography"),
        title_keywords=("trieu dai", "khang chien", "khoi nghia", "cach mang",
                        "chien tranh", "vua", "nha nuoc", "van minh", "co dai",
                        "trung dai", "can dai", "hien dai", "nha ly", "nha tran",
                        "nha nguyen", "ban do", "kinh do", "vi do", "khi hau",
                        "dia hinh", "song ngoi", "dan cu", "vung", "chau a",
                        "chau au", "dong bang", "cao nguyen", "bien dao", "tai nguyen"),
        content=(
            "- Lịch sử: nêu rõ THỜI GIAN (năm, thế kỉ), ĐỊA ĐIỂM, NHÂN VẬT, diễn biến "
            "chính, NGUYÊN NHÂN - KẾT QUẢ - Ý NGHĨA. Mốc thời gian phải đúng y sách.\n"
            "- Địa lí: vị trí, đặc điểm tự nhiên (địa hình, khí hậu, sông ngòi...), dân "
            "cư - kinh tế, mối quan hệ giữa các yếu tố; số liệu chỉ lấy từ sách.\n"
            "- Lược đồ/bản đồ trong sách: diễn đạt bằng lời các thông tin chính.\n"
            "- mindmap nên theo trục thời gian (Lịch sử) hoặc theo yếu tố (Địa lí)."),
        mcq=(
            "- Hỏi mốc thời gian, nhân vật, sự kiện, địa danh, nguyên nhân/kết quả/ý "
            "nghĩa, đặc điểm tự nhiên - dân cư của một vùng.\n"
            "- Phương án nhiễu: mốc thời gian gần nhau, nhân vật/triều đại cùng thời, "
            "địa danh cùng vùng — tuyệt đối không dùng sự kiện bịa."),
        essay=(
            "- Dạng ưu tiên: trình bày diễn biến / nguyên nhân / kết quả / ý nghĩa sự kiện, "
            "nêu công lao nhân vật, giải thích đặc điểm tự nhiên - dân cư, so sánh hai "
            "vùng hoặc hai sự kiện, liên hệ bài học lịch sử với hiện nay.\n"
            "- correct_answer: các ý chính có mốc thời gian / địa danh cụ thể đúng sách.\n"
            "- BỎ QUA câu yêu cầu đọc lược đồ, vẽ biểu đồ, sưu tầm tư liệu."),
    ),
    SubjectProfile(
        key="gdcd", name="Giáo dục công dân",
        names=("giao duc cong dan", "gdcd", "dao duc", "giao duc kinh te va phap luat",
               "kinh te va phap luat", "hoat dong trai nghiem"),
        title_keywords=("quyen tre em", "quyen cong dan", "nghia vu", "phap luat", "trung thuc", "ton trong",
                        "trach nhiem", "ki nang song", "ky nang song", "gia dinh",
                        "cong dong", "bao ve", "tiet kiem", "tu lap", "yeu thuong",
                        "tinh huong"),
        content=(
            "- sections: khái niệm → biểu hiện → ý nghĩa / vai trò → cách rèn luyện / "
            "quy định pháp luật liên quan (chỉ nêu điều luật có trong sách).\n"
            "- real_life: tình huống gần gũi ở trường, gia đình, cộng đồng."),
        mcq=(
            "- Ưu tiên câu XỬ LÍ TÌNH HUỐNG (\"Trong tình huống..., em nên làm gì?\") và "
            "nhận diện hành vi đúng/sai, bên cạnh câu khái niệm.\n"
            "- Đáp án đúng phải là cách ứng xử đúng chuẩn mực / đúng pháp luật theo sách; "
            "phương án nhiễu là cách ứng xử phổ biến nhưng chưa đúng."),
        essay=(
            "- Dạng ưu tiên: nêu khái niệm, biểu hiện, ý nghĩa; NHẬN XÉT hành vi trong "
            "tình huống; đề xuất cách xử lí tình huống (lấy tình huống trong sách).\n"
            "- correct_answer: ý chính + cách xử lí phù hợp; chấp nhận cách xử lí khác "
            "nếu đúng chuẩn mực (ghi rõ trong explanation_vi)."),
    ),
    SubjectProfile(
        key="tin-hoc", name="Tin học",
        names=("tin hoc", "informatics", "computer science", "lap trinh"),
        title_keywords=("may tinh", "thong tin", "du lieu", "internet", "mang may tinh",
                        "phan mem", "thuat toan", "chuong trinh", "lap trinh",
                        "scratch", "python", "bang tinh", "soan thao", "trinh chieu",
                        "thu muc", "tep", "email", "an toan thong tin",
                        "vong lap", "cau lenh"),
        content=(
            "- sections: khái niệm → thao tác / các bước thực hiện (đánh số) → lưu ý an "
            "toàn, đạo đức khi dùng máy tính và Internet.\n"
            "- Lập trình: nêu cú pháp + ví dụ code ngắn bằng text thuần, đúng ngôn ngữ "
            "trong sách (Scratch mô tả bằng tên khối lệnh).\n"
            "- real_life: tình huống dùng máy tính, ứng dụng hằng ngày."),
        mcq=(
            "- Trộn: khái niệm, chọn đúng THỨ TỰ THAO TÁC / nút lệnh / phím tắt có trong "
            "sách, đọc đoạn code ngắn và đoán kết quả, xử lí tình huống an toàn mạng.\n"
            "- Phương án nhiễu: lệnh/thao tác gần giống, lỗi logic thường gặp."),
        essay=(
            "- Dạng ưu tiên: nêu khái niệm, trình bày CÁC BƯỚC thực hiện một thao tác, "
            "giải thích kết quả đoạn code/thuật toán ngắn, viết đoạn code / mô tả thuật "
            "toán đơn giản, xử lí tình huống an toàn thông tin.\n"
            "- correct_answer: các bước đánh số hoặc code mẫu ngắn.\n"
            "- BỎ QUA câu yêu cầu thực hành trực tiếp trên máy mà không có đáp án xác định."),
        validate="- Với câu đọc code: chạy nhẩm từng dòng rồi mới chọn đáp án.",
    ),
    SubjectProfile(
        key="cong-nghe", name="Công nghệ",
        names=("cong nghe", "technology", "ki thuat", "ky thuat"),
        title_keywords=("trong trot", "chan nuoi", "do dung dien", "mach dien",
                        "ban ve", "vat lieu", "lap rap", "che bien", "nau an",
                        "trang phuc", "nha o", "an toan dien", "co khi", "may moc"),
        content=(
            "- sections: khái niệm → cấu tạo / nguyên lí hoạt động → quy trình thực hiện "
            "(các bước) → sử dụng an toàn, tiết kiệm.\n"
            "- real_life: đồ dùng, công việc quen thuộc trong gia đình."),
        mcq=(
            "- Hỏi cấu tạo, chức năng bộ phận, thứ tự các bước quy trình, quy tắc an "
            "toàn, lựa chọn vật liệu/dụng cụ phù hợp."),
        essay=(
            "- Dạng ưu tiên: nêu cấu tạo / nguyên lí, trình bày quy trình theo bước, "
            "giải thích quy tắc an toàn, đề xuất cách sử dụng tiết kiệm.\n"
            "- BỎ QUA câu yêu cầu thực hành lắp ráp, làm sản phẩm."),
    ),
]}

PROFILE_KEYS = ["general"] + list(PROFILES)


def get_profile(key: str) -> SubjectProfile:
    return PROFILES.get(key, GENERAL)


def _norm(text: str) -> str:
    """Bỏ dấu tiếng Việt, lowercase, mọi ký tự không phải chữ/số thành 1 dấu cách,
    bọc 2 đầu bằng dấu cách để khớp nguyên từ (' toan ' không khớp ' toanh ')."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", text).strip() + " "


def _has(haystack: str, kw: str) -> bool:
    return f" {kw} " in haystack


def _match_name(text: str):
    """Khớp TÊN MÔN. Từ khoá dài hơn được ưu tiên (vd 'khoa hoc tu nhien' thắng
    'khoa hoc', 'lich su va dia li' thắng 'lich su')."""
    t = _norm(text)
    if not t.strip():
        return None
    best, best_len = None, 0
    for p in PROFILES.values():
        for kw in p.names:
            if len(kw) > best_len and _has(t, kw):
                best, best_len = p, len(kw)
    return best


def _score_titles(titles) -> dict:
    """Đếm số tiêu đề chứa từ khoá chuyên môn của từng môn."""
    normed = [_norm(x) for x in titles if x]
    scores = {}
    for p in PROFILES.values():
        s = sum(1 for t in normed if any(_has(t, kw) for kw in p.title_keywords))
        if s:
            scores[p.key] = s
    return scores


def detect_subject(profile_arg: str = "auto", subject: str = "",
                   pdf_name: str = "", titles=()):
    """Trả về (SubjectProfile, nguồn nhận diện dạng chuỗi để log)."""
    if profile_arg and profile_arg != "auto":
        return get_profile(profile_arg), f"--subject-profile {profile_arg}"
    p = _match_name(subject)
    if p:
        return p, f'--subject "{subject}"'
    p = _match_name(pdf_name)
    if p:
        return p, f"tên file {pdf_name}"
    scores = _score_titles(titles)
    if scores:
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        top_key, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        # cần >= 2 tiêu đề khớp và hơn hẳn môn thứ hai, tránh đoán bừa
        if top >= 2 and top > second:
            return PROFILES[top_key], f"mục lục ({top} tiêu đề khớp từ khoá)"
    return GENERAL, "không nhận diện được — dùng prompt chung"


def guide_block(profile, part: str) -> str:
    """Khối hướng dẫn riêng theo môn để nối vào cuối prompt.
    part: content | mcq | essay | validate. Profile chung -> chuỗi rỗng."""
    if not profile or profile.key == "general":
        return ""
    text = getattr(profile, part, "")
    if not text:
        return ""
    return (f"\n\nHƯỚNG DẪN RIÊNG MÔN {profile.name.upper()} "
            f"(ưu tiên hơn quy tắc chung ở trên nếu khác nhau):\n{text}")
