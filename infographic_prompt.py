# -*- coding: utf-8 -*-
"""infographic_prompt.py — Dựng PROMPT MÔ TẢ ẢNH (tiếng Việt) cho model sinh
ảnh (vd gemini-2.5-flash-image) từ Learning Object. THUẦN CODE, 0 token AI.

Khác pipeline tham khảo 2 bước (đọc tài liệu -> tóm tắt JSON -> dựng prompt
ảnh): ở đây bước "tóm tắt" đã có sẵn — chính là Learning Object do
stage_content.py sinh ra (concept_overview/sections/quick_review...), với
prompt đã được tinh chỉnh chống hallucination + cắt sub-PDF theo page range.
Module này chỉ làm nốt việc còn lại: Learning Object -> mô tả ảnh chi tiết.

Vì sao không còn vẽ SVG bằng code: SVG hình học không tái tạo được phong
cách minh hoạ tay (nhân vật, hoạ tiết) như các tờ tổng hợp kiến thức mẫu.
Đánh đổi khi chuyển sang model sinh ảnh: tốn 1 request ảnh/topic (không còn
0 token), kết quả không deterministic, và chữ tiếng Việt trong ảnh AI sinh
đôi khi sai chính tả — nên xem ảnh trước khi dùng chính thức.
"""

COLOR_THEMES = ["blue", "green", "pink", "yellow", "purple"]


def _poster_sections(lo: dict) -> list:
    """Learning Object -> list khối nội dung cho poster: mỗi khối có
    heading/icon_hint/bullets (chưa gán number/color_theme, xem build_prompt)."""
    out = []

    overview = str(lo.get("concept_overview", "")).strip()
    objectives = [str(o).strip() for o in (lo.get("objectives") or []) if str(o).strip()]
    if overview or objectives:
        bullets = ([overview] if overview else []) + objectives
        out.append({"heading": "Khái niệm trọng tâm",
                    "icon_hint": "quyển sách mở và bóng đèn ý tưởng",
                    "bullets": bullets[:4]})

    for s in (lo.get("sections") or []):
        heading = str(s.get("heading", "")).strip()
        points = [str(p).strip() for p in (s.get("points") or []) if str(p).strip()]
        if not heading and not points:
            continue
        bullets = list(points)
        formula = s.get("formula") or {}
        expr = str(formula.get("expression", "")).strip()
        if expr:
            variables = ", ".join(
                f"{v.get('symbol', '')} là {v.get('meaning', '')}"
                for v in (formula.get("variables") or []) if v.get("symbol"))
            bullets.insert(0, f"Công thức: {expr}" +
                           (f" (trong đó {variables})" if variables else ""))
        icon = str(s.get("icon_hint", "")).strip() or "một biểu tượng nhỏ phù hợp nội dung"
        out.append({"heading": heading or "Nội dung", "icon_hint": icon,
                    "bullets": bullets[:4]})

    key_terms = lo.get("key_terms") or []
    if key_terms:
        bullets = [f"{t.get('term', '')}: {t.get('definition', '')}" for t in key_terms
                   if t.get("term")]
        out.append({"heading": "Từ khoá cần nhớ", "icon_hint": "chiếc chìa khoá vàng",
                    "bullets": bullets[:4]})

    notes = []
    notes += [str(x).strip() for x in (lo.get("real_life") or []) if str(x).strip()]
    notes += [f"{m.get('wrong', '')} — thực ra: {m.get('correct', '')}"
              for m in (lo.get("misconceptions") or [])]
    notes += [str(x).strip() for x in (lo.get("memory_hooks") or []) if str(x).strip()]
    if notes:
        out.append({"heading": "Lưu ý & mẹo nhớ", "icon_hint": "bóng đèn sáng và dấu chấm than",
                    "bullets": notes[:4]})

    for i, sec in enumerate(out):
        sec["number"] = i + 1
        sec["color_theme"] = COLOR_THEMES[i % len(COLOR_THEMES)]
    return out


def build_prompt(lo: dict, title: str, subject_tag: str = "") -> str:
    """Learning Object -> prompt mô tả ảnh (tiếng Việt) cho model sinh ảnh.
    Ném ValueError nếu không có field nào để mô tả (caller nên bắt và bỏ
    qua ảnh cho topic đó)."""
    lo = lo or {}
    sections = _poster_sections(lo)
    quick_review = [str(x).strip() for x in (lo.get("quick_review") or []) if str(x).strip()]
    if not sections and not quick_review:
        raise ValueError("Learning Object rỗng — không có nội dung để dựng prompt ảnh.")

    sections_text = ""
    for sec in sections:
        bullets_joined = "; ".join(sec["bullets"]) or "(không có ý chi tiết)"
        sections_text += (
            f'\n- Khối số {sec["number"]} (màu {sec["color_theme"]}), '
            f'tiêu đề "{sec["heading"]}", minh hoạ nhỏ hình {sec["icon_hint"]}, '
            f'nội dung gạch đầu dòng: {bullets_joined}.')

    final_number = len(sections) + 1
    final_bullets_joined = "; ".join(quick_review) if quick_review else "Ôn lại các ý chính ở trên."
    subject_line = f'\n   Góc trên có nhãn nhỏ: "{subject_tag}".' if subject_tag else ""

    return f"""Vẽ một tấm poster/infographic học tập khổ dọc (tỉ lệ A4 đứng), phong cách hoạt hình
dễ thương vẽ tay (hand-drawn doodle), bảng màu pastel nhẹ nhàng (be, xanh mint,
xanh dương nhạt, hồng phấn, vàng nhạt), nền giấy kẻ ngang mờ màu kem.

BỐ CỤC (giữ đúng thứ tự từ trên xuống dưới):
1. Trên cùng: tiêu đề lớn "{title}" viết chữ in đậm màu đỏ cam, đặt trong
   khung bong bóng mây (cloud speech bubble) viền zigzag đỏ đứt nét. Ngay dưới là
   dòng phụ đề nhỏ hơn "Tổng hợp kiến thức" trong 1 khung băng giấy (ribbon) màu vàng nhạt.{subject_line}
   Xung quanh tiêu đề trang trí thêm vài icon liên quan chủ đề bài học (dụng cụ thí nghiệm,
   sách vở, ngôi sao, trái tim nhỏ) theo phong cách sticker vẽ tay.

2. Bên dưới là các khối nội dung, MỖI khối là 1 hình chữ nhật bo góc lớn, viền màu
   đứt nét theo đúng màu được liệt kê, có 1 hình tròn số thứ tự (badge số)
   ở góc trên bên trái khối. Bên trong khối gồm: tiêu đề khối viết đậm, danh sách
   gạch đầu dòng (dùng dấu chấm tròn nhỏ màu), và 1 hình minh hoạ doodle nhỏ đặt bên
   cạnh hoặc bên dưới chữ. Danh sách các khối cần vẽ:{sections_text}

3. Khối cuối cùng (số {final_number}), nằm ngang hết chiều rộng poster,
   viền màu vàng cam, có icon bóng đèn sáng ở bên trái, tiêu đề
   "Ghi nhớ nhanh", nội dung: {final_bullets_joined}.
   Trang trí thêm ngôi sao, trái tim nhỏ ở 2 bên.

YÊU CẦU CHỮ VIẾT:
- Toàn bộ chữ trong ảnh là TIẾNG VIỆT có dấu, viết ĐÚNG CHÍNH TẢ theo nội dung đã cho ở trên,
  không được thay đổi, rút gọn sai nghĩa hay thêm chữ nước ngoài.
- Chữ tiêu đề khối và số thứ tự phải rõ ràng, dễ đọc, cỡ chữ đủ lớn.

PHONG CÁCH VẼ: hoạt hình phẳng (flat illustration), nét viền đen mảnh, tô màu pastel,
ánh sáng đều, không đổ bóng gắt, tổng thể vui tươi, thân thiện với học sinh THCS,
KHÔNG chứa logo thương hiệu, KHÔNG chứa nhân vật hoạt hình bản quyền có sẵn."""
