from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import date
from textwrap import dedent

_project_site = Path(__file__).resolve().parents[1] / ".venv" / "Lib" / "site-packages"
if _project_site.exists():
    sys.path.append(str(_project_site))

import yaml
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "user-manual"
ASSET = OUT / "assets"
DOCX_OUT = OUT / "Huong_dan_su_dung_ESG_Tracker_BSR_2023_2025.docx"

NAVY = "102A43"
BLUE = "1F5A7A"
GREEN = "16856B"
TEAL = "2A9D8F"
GOLD = "E9A23B"
RED = "C94C4C"
LIGHT = "EEF4F8"
MID = "D9E4EC"
GRAY = "5C6B73"
WHITE = "FFFFFF"
BLACK = "111111"


def set_cell_shading(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color="D9D9D9", size="4"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        el = borders.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def add_field(run, instruction: str):
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, separate, end])


def keep_with_next(paragraph):
    p_pr = paragraph._p.get_or_add_pPr()
    keep = OxmlElement("w:keepNext")
    p_pr.append(keep)


def configure_document(doc: Document):
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
    sec.left_margin, sec.right_margin = Cm(2.1), Cm(1.8)
    sec.header_distance, sec.footer_distance = Cm(0.8), Cm(0.8)

    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    normal.font.size = Pt(10.2)
    normal.font.color.rgb = RGBColor.from_string(BLACK)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.13

    for name, size, color in [("Title", 30, BLACK), ("Heading 1", 20, BLACK), ("Heading 2", 14, NAVY), ("Heading 3", 11.5, BLUE)]:
        st = doc.styles[name]
        st.font.name = "Arial"
        st._element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = RGBColor.from_string(color)
        st.paragraph_format.space_before = Pt(9)
        st.paragraph_format.space_after = Pt(5)

    if "Code Block" not in [s.name for s in doc.styles]:
        code = doc.styles.add_style("Code Block", WD_STYLE_TYPE.PARAGRAPH)
        code.font.name = "Consolas"
        code._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
        code.font.size = Pt(8.7)
        code.paragraph_format.left_indent = Cm(0.5)
        code.paragraph_format.right_indent = Cm(0.3)
        code.paragraph_format.space_before = Pt(3)
        code.paragraph_format.space_after = Pt(5)

    header = sec.header.paragraphs[0]
    header.text = "ESG TRACKER BSR  |  HƯỚNG DẪN SỬ DỤNG PROTOTYPE"
    header.style = doc.styles["Normal"]
    header.runs[0].font.size = Pt(7.5)
    header.runs[0].font.bold = True
    header.runs[0].font.color.rgb = RGBColor.from_string(GRAY)
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Tài liệu học thuật • Không phải ý kiến kiểm toán  |  ")
    add_field(footer.add_run(), "PAGE")


def add_part(doc: Document, roman: str, title: str):
    doc.add_page_break()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(100)
    r = p.add_run(f"PHẦN {roman}")
    r.bold = True; r.font.size = Pt(16); r.font.color.rgb = RGBColor.from_string(GREEN)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run(title.upper())
    r2.bold = True; r2.font.size = Pt(26); r2.font.color.rgb = RGBColor.from_string(BLACK)
    p3 = doc.add_paragraph("Tài liệu hướng dẫn ESG Tracker BSR")
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.runs[0].font.color.rgb = RGBColor.from_string(GRAY)


def add_chapter(doc: Document, number: int, title: str, lead: str = ""):
    p = doc.add_paragraph(style="Heading 1")
    p.paragraph_format.page_break_before = True
    p.add_run(f"Chương {number}. {title}")
    if lead:
        p2 = doc.add_paragraph(lead)
        p2.paragraph_format.space_after = Pt(9)
        p2.runs[0].italic = True
        p2.runs[0].font.color.rgb = RGBColor.from_string(GRAY)


def add_h2(doc: Document, text: str):
    p = doc.add_paragraph(text, style="Heading 2")
    keep_with_next(p)
    return p


def add_h3(doc: Document, text: str):
    p = doc.add_paragraph(text, style="Heading 3")
    keep_with_next(p)
    return p


def add_bullets(doc: Document, items, numbered=False):
    style = "List Number" if numbered else "List Bullet"
    for item in items:
        p = doc.add_paragraph(style=style)
        p.add_run(str(item))


def add_code(doc: Document, code: str):
    p = doc.add_paragraph(style="Code Block")
    p.paragraph_format.keep_together = True
    p.add_run(dedent(code).strip())
    p_pr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), "F4F6F8"); p_pr.append(shd)
    return p


def add_callout(doc: Document, kind: str, text: str):
    palette = {"LƯU Ý": (BLUE, "EAF3F8"), "CẢNH BÁO": (RED, "FCECEC"), "VÍ DỤ": (GREEN, "EAF7F3")}
    accent, fill = palette.get(kind, (GOLD, "FFF8E7"))
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width, table.columns[1].width = Cm(2.4), Cm(14.0)
    table.cell(0, 0).text = kind
    table.cell(0, 1).text = text
    set_cell_shading(table.cell(0, 0), accent)
    set_cell_shading(table.cell(0, 1), fill)
    for run in table.cell(0, 0).paragraphs[0].runs:
        run.font.bold = True; run.font.color.rgb = RGBColor.from_string(WHITE); run.font.size = Pt(8.5)
    for cell in table.rows[0].cells:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_border(cell, "FFFFFF", "0")
    return table


TABLE_CAPTIONS = []
FIGURE_CAPTIONS = []


def add_table(doc: Document, title: str, headers, rows, widths=None, font_size=8.2):
    number = len(TABLE_CAPTIONS) + 1
    TABLE_CAPTIONS.append(f"Bảng {number}. {title}")
    pcap = doc.add_paragraph()
    pcap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = pcap.add_run(TABLE_CAPTIONS[-1]); run.bold = True; run.font.size = Pt(8.5); run.font.color.rgb = RGBColor.from_string(GRAY)
    keep_with_next(pcap)
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = widths is None
    hdr = table.rows[0]
    set_repeat_table_header(hdr)
    for i, h in enumerate(headers):
        c = hdr.cells[i]; c.text = str(h); set_cell_shading(c, NAVY); set_cell_border(c)
        for r in c.paragraphs[0].runs:
            r.font.bold = True; r.font.color.rgb = RGBColor.from_string(WHITE); r.font.size = Pt(font_size)
        if widths: c.width = Cm(widths[i])
    for ri, row in enumerate(rows):
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val)
            set_cell_border(cells[i])
            if ri % 2: set_cell_shading(cells[i], "F6F9FB")
            for p in cells[i].paragraphs:
                p.paragraph_format.space_after = Pt(1)
                for r in p.runs: r.font.size = Pt(font_size)
            if widths: cells[i].width = Cm(widths[i])
            cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def add_figure(doc: Document, path: Path, caption: str, width_cm=16.0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    number = len(FIGURE_CAPTIONS) + 1
    FIGURE_CAPTIONS.append(f"Hình {number}. {caption}")
    cap = doc.add_paragraph(FIGURE_CAPTIONS[-1])
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.runs[0].italic = True; cap.runs[0].font.size = Pt(8.5); cap.runs[0].font.color.rgb = RGBColor.from_string(GRAY)


def add_summary(doc: Document, items):
    add_h2(doc, "Tóm tắt chương")
    add_callout(doc, "LƯU Ý", " ".join(items))


def get_font(size=30, bold=False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for p in candidates:
        if p.exists(): return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def diagram_pipeline(path: Path, technical=False):
    w, h = 1800, 620 if technical else 430
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    title = "PIPELINE KỸ THUẬT VÀ ĐIỂM KIỂM SOÁT" if technical else "TỪ BÁO CÁO ĐẾN KẾT QUẢ SÀNG LỌC"
    d.text((60, 35), title, font=get_font(34, True), fill="#102A43")
    labels = ["Báo cáo\nPDF/JSON", "Trích xuất\nvăn bản", "Claim &\nmetric", "Chuẩn hóa", "Tìm bằng\nchứng", "Kiểm tra\nkhả năng so sánh", "Rule\nEngine", "Chấm điểm", "Dashboard\n& rà soát"]
    colors = ["#EAF3F8", "#EAF3F8", "#EAF7F3", "#EAF7F3", "#FFF8E7", "#FFF8E7", "#FCECEC", "#FCECEC", "#EAF3F8"]
    x, y, bw, bh, gap = 45, 135, 170, 115, 22
    for i, label in enumerate(labels):
        left = x + i*(bw+gap)
        d.rounded_rectangle((left, y, left+bw, y+bh), radius=18, fill=colors[i], outline="#8AA4B5", width=3)
        lines = label.split("\n")
        for j, line in enumerate(lines):
            bbox = d.textbbox((0,0), line, font=get_font(23, True))
            d.text((left+(bw-(bbox[2]-bbox[0]))/2, y+25+j*32), line, font=get_font(23, True), fill="#102A43")
        if i < len(labels)-1:
            ax = left+bw+3
            d.line((ax, y+bh/2, ax+gap-4, y+bh/2), fill="#2A9D8F", width=5)
            d.polygon([(ax+gap-4,y+bh/2),(ax+gap-15,y+bh/2-8),(ax+gap-15,y+bh/2+8)], fill="#2A9D8F")
    if technical:
        notes = [
            (65, 325, 520, "Provenance: document, năm, loại báo cáo, trang, nguyên văn, phương pháp, confidence"),
            (625, 325, 1110, "Comparability gate: metric • kỳ • đơn vị • scope • boundary • định nghĩa • absolute/intensity"),
            (1200, 325, 1715, "Đầu ra: relationship • rule result • score • evidence coverage • giải thích"),
        ]
        for left, top, right, txt in notes:
            d.rounded_rectangle((left, top, right, top+150), radius=15, fill="#F6F9FB", outline="#D9E4EC", width=3)
            words, lines, line = txt.split(), [], ""
            for word in words:
                test = (line+" "+word).strip()
                if d.textbbox((0,0), test, font=get_font(21))[2] < (right-left-35): line=test
                else: lines.append(line); line=word
            lines.append(line)
            for j, ln in enumerate(lines): d.text((left+18, top+25+j*30), ln, font=get_font(21), fill="#334E68")
    im.save(path, quality=95)


def diagram_gri(path: Path):
    im = Image.new("RGB", (1500, 650), "white"); d = ImageDraw.Draw(im)
    d.text((55, 35), "HỆ THỐNG CHUẨN GRI TRONG PHẠM VI PROTOTYPE", font=get_font(32, True), fill="#102A43")
    cols = [
        ("UNIVERSAL", "GRI 1 • Nền tảng\nGRI 2 • Công bố chung\nGRI 3 • Chủ đề trọng yếu", "#EAF3F8"),
        ("SECTOR", "GRI 11\nOil and Gas Sector", "#EAF7F3"),
        ("TOPIC", "GRI 201, 207, 302, 303\n305, 306, 403, 404…", "#FFF8E7"),
    ]
    for i,(head,body,color) in enumerate(cols):
        x=75+i*480
        d.rounded_rectangle((x,145,x+390,430), radius=22, fill=color, outline="#8AA4B5", width=4)
        d.text((x+25,175),head,font=get_font(26,True),fill="#102A43")
        for j,line in enumerate(body.split("\n")): d.text((x+25,245+j*46),line,font=get_font(24),fill="#334E68")
        if i<2:
            d.line((x+400,285,x+465,285),fill="#2A9D8F",width=6)
            d.polygon([(x+465,285),(x+448,274),(x+448,296)],fill="#2A9D8F")
    d.text((76,500), "Dashboard hiển thị GRI reference từ metrics.yml; đây là tham chiếu hỗ trợ rà soát, không phải xác nhận báo cáo 'in accordance with GRI'.", font=get_font(22), fill="#5C6B73")
    im.save(path, quality=95)


def diagram_reading(path: Path):
    im = Image.new("RGB", (1500, 590), "white"); d=ImageDraw.Draw(im)
    d.text((55,35),"CÁCH ĐỌC MỘT CẢNH BÁO AN TOÀN",font=get_font(32,True),fill="#102A43")
    steps=[("1","Đọc nguyên văn\nclaim"),("2","Đọc evidence\nvà provenance"),("3","Kiểm tra năm,\nđơn vị, scope, boundary"),("4","Xem relationship\nvà rule"),("5","Đánh giá thủ công,\nkhông kết luận vội")]
    for i,(num,txt) in enumerate(steps):
        x=65+i*285
        d.ellipse((x,155,x+64,219),fill="#16856B")
        d.text((x+21,166),num,font=get_font(27,True),fill="white")
        d.rounded_rectangle((x,245,x+235,420),radius=18,fill="#F6F9FB",outline="#D9E4EC",width=3)
        for j,line in enumerate(txt.split("\n")): d.text((x+18,285+j*42),line,font=get_font(22,True),fill="#102A43")
        if i<4:
            d.line((x+240,332,x+275,332),fill="#E9A23B",width=5)
    d.text((70,490),"MISSING ≠ CONTRADICTS  •  AMBIGUOUS = chưa đủ dữ kiện  •  NOT_COMPARABLE = không đáp ứng điều kiện đối chiếu",font=get_font(22,True),fill="#C46B18")
    im.save(path, quality=95)


def diagram_ui(path: Path):
    im = Image.new("RGB", (1700, 980), "#F2F6FA"); d=ImageDraw.Draw(im)
    d.rounded_rectangle((55,45,1645,220),radius=28,fill="#102A43")
    d.text((95,85),"ESG Tracker BSR",font=get_font(48,True),fill="white")
    d.text((95,150),"Prototype sàng lọc rủi ro • GRI 11 • dữ liệu Demo / Nguồn BSR",font=get_font(25),fill="#BFE8DD")
    d.rounded_rectangle((55,245,1645,450),radius=22,fill="white",outline="#D9E4EC",width=3)
    d.text((90,275),"1  BỘ LỌC ĐA CHIỀU",font=get_font(27,True),fill="#102A43")
    filters=["Chế độ dữ liệu","Năm","Loại tài liệu","Trụ cột","Chủ đề","Metric","Rule","Severity","Relationship"]
    for i,f in enumerate(filters):
        x=85+(i%5)*305; y=330+(i//5)*70
        d.rounded_rectangle((x,y,x+270,y+48),radius=9,fill="#F6F9FB",outline="#AFC5D3",width=2)
        d.text((x+12,y+12),f,font=get_font(18),fill="#334E68")
    tabs=["2  Tổng quan","3  Ma trận chủ đề","4  Xu hướng metric","5  Đối chiếu","6  Truy xuất nguồn"]
    for i,t in enumerate(tabs):
        x=55+i*318
        d.rounded_rectangle((x,480,x+300,550),radius=13,fill="#FFFFFF" if i==0 else "#DDE7EF",outline="#D9E4EC",width=2)
        d.text((x+18,502),t,font=get_font(20,True),fill="#102A43")
    d.rounded_rectangle((55,585,1645,915),radius=22,fill="white",outline="#D9E4EC",width=3)
    cards=[("7","Risk Score"),("8","Mức rủi ro"),("9","Tổng claim"),("10","Cảnh báo"),("11","Evidence coverage"),("12","Confidence")]
    for i,(n,t) in enumerate(cards):
        x=85+i*250
        d.rounded_rectangle((x,630,x+220,750),radius=15,fill="#EAF3F8",outline="#AFC5D3",width=2)
        d.text((x+15,650),n,font=get_font(23,True),fill="#16856B")
        d.text((x+15,700),t,font=get_font(18,True),fill="#102A43")
    d.text((90,810),"13  Bảng claim ưu tiên • có sắp xếp, phân trang và drill-down",font=get_font(25,True),fill="#102A43")
    im.save(path, quality=95)


def load_configs():
    metrics = yaml.safe_load((ROOT / "config" / "metrics.yml").read_text(encoding="utf-8"))["metrics"]
    rules = yaml.safe_load((ROOT / "config" / "rules.yml").read_text(encoding="utf-8"))["rules"]
    scoring = yaml.safe_load((ROOT / "config" / "scoring.yml").read_text(encoding="utf-8"))
    return metrics, rules, scoring


def front_matter(doc: Document):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(35)
    r = p.add_run("ESG TRACKER BSR")
    r.bold = True; r.font.size = Pt(17); r.font.color.rgb = RGBColor.from_string(GREEN)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER; p2.paragraph_format.space_before = Pt(34)
    r2 = p2.add_run("HƯỚNG DẪN SỬ DỤNG\nVÀ GIẢI THÍCH HỆ THỐNG")
    r2.bold = True; r2.font.size = Pt(29); r2.font.color.rgb = RGBColor.from_string(BLACK)
    p3 = doc.add_paragraph("Hệ thống đánh giá tín hiệu rủi ro tẩy xanh trong báo cáo phát triển bền vững\nTrường hợp nghiên cứu BSR 2023–2025")
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r in p3.runs: r.font.size = Pt(15); r.font.color.rgb = RGBColor.from_string(NAVY)
    doc.add_paragraph("\n")
    add_callout(doc, "LƯU Ý", "Prototype học thuật phục vụ sàng lọc. Tài liệu và hệ thống không phải công cụ kiểm toán, không đưa ra kết luận pháp lý và không khẳng định BSR thực hiện greenwashing.")
    p4 = doc.add_paragraph("Phiên bản 1.0  •  Ngày phát hành: 12/09/2026\nNgôn ngữ: Tiếng Việt  •  Trạng thái: Bàn giao prototype")
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r in p4.runs: r.font.size = Pt(10); r.font.color.rgb = RGBColor.from_string(GRAY)

    doc.add_page_break()
    doc.add_heading("Thông tin tài liệu", level=1)
    add_table(doc, "Thông tin kiểm soát tài liệu", ["Thuộc tính", "Nội dung"], [
        ("Tên tài liệu", "Hướng dẫn sử dụng và giải thích hệ thống ESG Tracker BSR 2023–2025"),
        ("Mục đích", "Hướng dẫn người mới cài đặt, vận hành, đọc kết quả và hiểu giới hạn của prototype"),
        ("Đối tượng", "Sinh viên, giảng viên, người nghiên cứu ESG/GRI, người tiếp nhận bàn giao sản phẩm"),
        ("Nguồn kiểm chứng", "Source code, README, YAML, SQLite, dữ liệu Phase 1, tài liệu đặc tả, tài liệu GRI và dashboard chạy tại localhost"),
        ("Phạm vi dữ liệu", "Nguồn BSR thực tế trong batch: 2023–2025; dữ liệu minh họa: 2022–2025, luôn gắn is_demo_data=true"),
        ("Chủ sở hữu", "Nhóm thực hiện đồ án [CẦN NGƯỜI PHÁT TRIỂN XÁC NHẬN]"),
        ("Liên hệ hỗ trợ", "[CẦN NGƯỜI PHÁT TRIỂN XÁC NHẬN]"),
    ], widths=[4.2, 12.0], font_size=8.8)
    add_h2(doc, "Lịch sử phiên bản")
    add_table(doc, "Lịch sử phiên bản", ["Phiên bản", "Ngày", "Người thực hiện", "Nội dung"], [
        ("1.0", "12/09/2026", "Tài liệu bàn giao prototype", "Tạo mới; đối chiếu 5 tab, 15 luật, 16 metric, công thức scoring và lệnh chạy"),
    ], widths=[2.1,2.7,4.2,7.4])
    add_h2(doc, "Quy ước đọc")
    add_bullets(doc, [
        "Lý thuyết chung được trình bày trước; phần 'Trong prototype' mô tả đúng hành vi source code hiện tại.",
        "Mọi con số trong ví dụ đều là dữ liệu minh họa, không phải kết quả thực tế của BSR.",
        "Nhãn [CẦN NGƯỜI PHÁT TRIỂN XÁC NHẬN] đánh dấu thông tin quản trị hoặc hành vi chưa chứng minh được từ mã nguồn.",
        "Nhãn [CHÈN ẢNH: …] là vị trí cần thay bằng ảnh chụp tương ứng khi bàn giao bản giao diện ổn định.",
    ])

    doc.add_page_break()
    doc.add_heading("Mục lục", level=1)
    p = doc.add_paragraph()
    add_field(p.add_run(), 'TOC \\o "1-3" \\h \\z \\u')
    toc_items = [
        ("Phần I – Giới thiệu hệ thống", "5"), ("Chương 1. Tổng quan", "6"),
        ("Chương 2. Phạm vi và giới hạn", "7"), ("Phần II – Kiến thức nền tảng", "8"),
        ("Chương 3. ESG là gì?", "9"), ("Chương 4. Greenwashing là gì?", "10"),
        ("Chương 5. Tổng quan về GRI", "11"), ("Chương 6. Thuật ngữ Oil and Gas", "13"),
        ("Phần III – Cơ sở kỹ thuật", "14"), ("Chương 7. Information Extraction", "15"),
        ("Chương 8. Chuẩn hóa dữ liệu", "17"), ("Chương 9. Phân loại claim", "18"),
        ("Chương 10. Evidence Matching", "19"), ("Chương 11. Rule Engine", "20"),
        ("Chương 12. Tính điểm rủi ro", "22"), ("Chương 13. Thuật toán tổng thể", "23"),
        ("Phần IV – Hướng dẫn sử dụng", "25"), ("Chương 14. Yêu cầu hệ thống", "26"),
        ("Chương 15. Cài đặt và khởi động", "27"), ("Chương 16. Làm quen giao diện", "28"),
        ("Chương 17. Hướng dẫn từng màn hình", "30"), ("Chương 18. Các kịch bản sử dụng", "34"),
        ("Chương 19. Cách đọc kết quả đúng", "36"), ("Phần V – Quản trị và khắc phục", "37"),
        ("Chương 20. Nhập/cập nhật dữ liệu", "38"), ("Chương 21. Cấu hình", "39"),
        ("Chương 22. Lỗi thường gặp", "40"), ("Chương 23. FAQ", "41"),
        ("Phần VI – Phụ lục", "42"), ("Phụ lục A–F", "43–48"),
    ]
    grid = doc.add_table(rows=0, cols=4)
    grid.alignment = WD_TABLE_ALIGNMENT.CENTER
    half = (len(toc_items) + 1) // 2
    for i in range(half):
        cells = grid.add_row().cells
        pairs = [toc_items[i], toc_items[i+half] if i+half < len(toc_items) else ("","")]
        for side,(label,page) in enumerate(pairs):
            cells[side*2].text = label; cells[side*2+1].text = page
            cells[side*2+1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            for c in (cells[side*2],cells[side*2+1]):
                set_cell_border(c,"E6EDF2","2")
                for rr in c.paragraphs[0].runs: rr.font.size = Pt(7.6)
    add_callout(doc, "LƯU Ý", "Trong Microsoft Word, nhấn Ctrl+A rồi F9 nếu số trang trong mục lục chưa được cập nhật tự động.")
    doc.add_page_break()
    doc.add_heading("Danh mục hình và bảng", level=1)
    add_h2(doc, "Danh mục hình")
    for text in [
        "Hình 1. Quy trình tổng quan từ báo cáo đến người dùng rà soát",
        "Hình 2. Quan hệ giữa Universal, Sector và Topic Standards",
        "Hình 3. Pipeline kỹ thuật và các điểm kiểm soát",
        "Hình 4. Cách đọc một cảnh báo an toàn",
        "Hình 5. Sơ đồ đánh số các thành phần giao diện prototype",
    ]: doc.add_paragraph(text, style="List Bullet")
    add_h2(doc, "Danh mục bảng")
    doc.add_paragraph("Danh mục bảng được đánh số liên tục trong toàn tài liệu. Khi mở bằng Word, có thể dùng References → Insert Table of Figures → Caption label: Bảng để sinh danh mục động.")


def part_i_ii(doc: Document, assets: dict):
    add_part(doc, "I", "Giới thiệu hệ thống")
    add_chapter(doc, 1, "Tổng quan", "Từ nhu cầu đọc báo cáo ESG đến một quy trình sàng lọc có thể truy vết.")
    add_h2(doc, "1.1. Tên, bối cảnh và vấn đề")
    doc.add_paragraph("ESG Tracker BSR là prototype web dùng để tổ chức claim (tuyên bố ESG), metric (chỉ số), bằng chứng và cảnh báo cần rà soát trong báo cáo công khai của Công ty Cổ phần Lọc hóa dầu Bình Sơn (BSR). Báo cáo phát triển bền vững thường dài, thuật ngữ không đồng nhất và cùng một thông tin có thể xuất hiện ở báo cáo thường niên, ESG hoặc tài chính. Việc đọc thủ công dễ bỏ sót khác biệt về năm, đơn vị, Scope hoặc boundary.")
    doc.add_paragraph("Hệ thống không thay người phân tích. Nó thu hẹp vùng cần đọc bằng cách tìm mệnh đề, chuẩn hóa dữ liệu, xếp hạng bằng chứng ứng viên, loại các cặp không so sánh được và chấm điểm tín hiệu rủi ro. Người dùng vẫn phải đọc nguyên văn và kiểm tra trang nguồn.")
    add_h2(doc, "1.2. Mục tiêu, người dùng và phạm vi")
    add_bullets(doc, [
        "Quản lý dữ liệu BSR theo năm và loại báo cáo; trường hợp nghiên cứu thực tế hiện có 2023–2025.",
        "Hiển thị dữ liệu demo 2022–2025 trong một chế độ tách biệt để trình diễn đầy đủ trạng thái.",
        "Hỗ trợ sinh viên, giảng viên và nhà nghiên cứu rà soát claim, evidence, metric và provenance.",
        "Trình bày điểm theo claim, chủ đề, trụ cột và bộ lọc; điểm tổng hợp trên giao diện hiện dùng phép trung bình trong tập lọc.",
    ])
    add_h2(doc, "1.3. Chức năng chính và chức năng không có")
    add_table(doc, "Phạm vi chức năng prototype", ["Có trong prototype", "Không phải chức năng của prototype"], [
        ("5 tab phân tích; bộ lọc đa chiều; KPI; heatmap; trend; explorer; viewer", "Kiểm toán độc lập, xác minh tại hiện trường hoặc kết luận vi phạm"),
        ("Rule-based NLP, RapidFuzz, normalization và comparability gate", "Mô hình AI trả phí, LLM có khóa bí mật hoặc học máy tự huấn luyện"),
        ("Truy vết tài liệu, năm, loại báo cáo, trang và nguyên văn", "Bảo đảm PDF/OCR luôn chính xác hoặc tự sửa dữ liệu nguồn"),
        ("Dữ liệu nguồn và demo có cờ phân biệt", "Trộn số demo vào kết quả BSR thực tế"),
    ], widths=[8.1,8.1])
    add_h2(doc, "1.4. Quy trình tổng quan")
    add_figure(doc, assets["overview"], "Quy trình tổng quan từ báo cáo đến người dùng rà soát")
    add_callout(doc, "VÍ DỤ", "Một câu 'Công ty giảm đáng kể phát thải trong năm 2024' được tách thành claim. Hệ thống tìm metric phát thải cùng năm, kiểm tra đơn vị/Scope/boundary, sau đó chỉ gắn CONTRADICTS nếu dữ liệu thực sự so sánh được và diễn biến trái chiều.")
    add_summary(doc, ["ESG Tracker là công cụ hỗ trợ sàng lọc.", "Mỗi cảnh báo cần được kiểm tra bằng nguồn gốc và điều kiện so sánh."])

    add_chapter(doc, 2, "Phạm vi và giới hạn")
    add_h2(doc, "2.1. Phạm vi nghiên cứu")
    doc.add_paragraph("Prototype được thiết kế cho BSR, ngành lọc hóa dầu, với chuẩn ngành chính là GRI 11. Dữ liệu đầu vào là báo cáo công khai và các tệp trích xuất Phase 1. Source code hỗ trợ 2022–2025; tuy nhiên batch nguồn thực tế hiện không có record BSR 2022. Năm 2022 trong chế độ Demo chỉ dùng để thử giao diện và luật.")
    add_h2(doc, "2.2. Các giới hạn phải ghi nhớ")
    add_bullets(doc, [
        "Chất lượng đầu ra phụ thuộc cấu trúc PDF, bảng biểu, font nhúng và độ chính xác của OCR/trích xuất.",
        "GRI reference là ánh xạ hỗ trợ tìm kiếm; không phải xác nhận doanh nghiệp báo cáo phù hợp GRI.",
        "Điểm rủi ro không phải bằng chứng pháp lý, không chứng minh ý định và không đo thiệt hại.",
        "Thiếu dữ liệu có thể do tài liệu ngoài phạm vi, cách gọi khác, lỗi OCR hoặc báo cáo chưa công bố.",
        "Tương quan thời gian không đồng nghĩa quan hệ nhân quả; biến động vận hành cần bối cảnh sản lượng, sự cố và phạm vi hợp nhất.",
        "Cơ chế tổng hợp điểm doanh nghiệp có trọng số materiality chính thức chưa có trong source: [CẦN NGƯỜI PHÁT TRIỂN XÁC NHẬN].",
    ])
    add_callout(doc, "CẢNH BÁO", "Không viết 'BSR tẩy xanh' chỉ dựa trên Risk Score, relationship hoặc một luật. Cách diễn đạt phù hợp là 'hệ thống phát hiện tín hiệu cần rà soát trong dữ liệu đang có'.")
    add_summary(doc, ["Prototype chỉ bao phủ dữ liệu đã nhập.", "Khác phạm vi, khác phương pháp hoặc thiếu dữ liệu phải được tách khỏi mâu thuẫn."])

    add_part(doc, "II", "Kiến thức nền tảng")
    add_chapter(doc, 3, "ESG là gì?", "Giải thích các khái niệm tối thiểu trước khi đọc dashboard.")
    concepts = [
        ("ESG", "Environmental, Social and Governance: ba nhóm vấn đề môi trường, xã hội và quản trị. Ví dụ: phát thải, an toàn lao động, minh bạch thuế."),
        ("Environmental – Môi trường", "Tác động đến khí hậu, nước, năng lượng, chất thải và đa dạng sinh học. Ví dụ: tCO2e Scope 1."),
        ("Social – Xã hội", "Tác động đến người lao động và cộng đồng. Ví dụ: LTIFR và giờ đào tạo."),
        ("Governance – Quản trị", "Cách tổ chức ra quyết định, tuân thủ và công khai. Ví dụ: tiền phạt môi trường và thuế."),
        ("Báo cáo phát triển bền vững", "Tài liệu công bố tác động, chính sách, mục tiêu và kết quả bền vững trong một kỳ."),
        ("Claim", "Một mệnh đề có nội dung ESG cần kiểm tra. Ví dụ: 'giảm 5% cường độ phát thải so với 2023'."),
        ("Evidence", "Thông tin hỗ trợ hoặc đối chiếu claim: bảng metric, đoạn phương pháp hoặc giải trình."),
        ("Định tính / định lượng", "Định tính mô tả chính sách; định lượng có số và đơn vị. 'Có quy trình ứng phó' khác '0 vụ tràn dầu'."),
        ("Tuyệt đối / cường độ", "Giá trị tuyệt đối là tổng lượng; cường độ chia cho mẫu số. 1 triệu tCO2e khác 0,2 tCO2e/tấn sản phẩm."),
        ("Năm báo cáo / cơ sở / mục tiêu", "Năm được báo cáo; mốc so sánh; và thời điểm cần đạt. Ví dụ: giảm 10% vào 2025 so với 2022."),
        ("Scope", "Phạm vi nguồn phát thải. Scope 1 là trực tiếp; Scope 2 là gián tiếp từ năng lượng mua."),
        ("Boundary", "Ranh giới tổ chức hoặc hoạt động được tính. Ví dụ: hợp nhất toàn tập đoàn khác riêng công ty mẹ."),
        ("Material topic", "Chủ đề trọng yếu: tác động đáng kể cần ưu tiên xác định và báo cáo."),
    ]
    add_table(doc, "Khái niệm ESG cho người mới", ["Khái niệm", "Giải thích và ví dụ"], concepts, widths=[4.1,12.1], font_size=8.4)
    add_h2(doc, "3.1. ESG, CSR và phát triển bền vững")
    doc.add_paragraph("Phát triển bền vững là mục tiêu cân bằng kinh tế, xã hội và môi trường trong dài hạn. CSR (Corporate Social Responsibility – trách nhiệm xã hội doanh nghiệp) thường nhấn mạnh cam kết và hoạt động với xã hội. ESG là cách nhóm hóa các vấn đề để quản trị, công bố và phân tích. Ba khái niệm có vùng giao nhau nhưng không đồng nhất.")
    add_callout(doc, "VÍ DỤ", "Một chương trình trồng cây có thể là hoạt động CSR. Khi phân tích ESG, cần hỏi thêm diện tích, thời gian, tỷ lệ sống, boundary, chi phí và tác động so với phát thải từ hoạt động chính.")
    add_summary(doc, ["Đừng so sánh số tuyệt đối với cường độ.", "Scope và boundary là điều kiện bắt buộc trước khi kết luận hai số khác nhau."])

    add_chapter(doc, 4, "Greenwashing là gì?", "Phân biệt hành vi đã được xác nhận với tín hiệu rủi ro do hệ thống phát hiện.")
    doc.add_paragraph("Greenwashing (tẩy xanh) là cách truyền thông tạo ấn tượng môi trường tích cực hơn thực tế hoặc che khuất tác động đáng kể. Nghiên cứu cho thấy hiện tượng này có nhiều hình thức và động lực; vì vậy một công cụ tự động không thể suy ra ý định chỉ từ văn bản [11]–[13].")
    add_h2(doc, "4.1. Các biểu hiện thường gặp")
    add_table(doc, "Biểu hiện rủi ro thường gặp", ["Biểu hiện", "Ví dụ đơn giản ngành Oil and Gas", "Câu hỏi rà soát"], [
        ("Tuyên bố mơ hồ", "'Thân thiện hơn với môi trường'", "Hơn theo chỉ số nào, năm nào, phạm vi nào?"),
        ("Thiếu bằng chứng", "Nói giảm phát thải nhưng không có bảng số", "Có metric, trang hoặc phương pháp không?"),
        ("Chọn lọc tích cực", "Chỉ nêu tái chế nhưng bỏ qua chất thải phát sinh", "Tổng lượng và phần chưa xử lý là bao nhiêu?"),
        ("Thay năm cơ sở", "Đổi baseline từ 2020 sang 2022", "Có tái tính và giải trình không?"),
        ("Thay phạm vi", "Năm sau loại một cơ sở khỏi boundary", "Chuỗi số đã restate chưa?"),
        ("Absolute/intensity mix", "Tổng phát thải tăng nhưng cường độ giảm", "Claim nói tổng lượng hay hiệu suất?"),
        ("Future only", "Chỉ cam kết 2030", "Có tiến độ năm hiện tại không?"),
        ("Cross-document inconsistency", "ESG report và annual report ghi khác", "Cùng định nghĩa/kỳ/scope không?"),
    ], widths=[3.0,7.1,6.1], font_size=8.0)
    add_h2(doc, "4.2. Sáu kết luận cần phân biệt")
    add_table(doc, "Phân biệt bản chất kết quả", ["Trường hợp", "Cách hiểu đúng"], [
        ("Greenwashing đã được xác nhận", "Đòi hỏi quy trình điều tra/xác minh có thẩm quyền; prototype không thực hiện."),
        ("Tín hiệu rủi ro", "Một hoặc nhiều điều kiện rule-based kích hoạt; cần rà soát."),
        ("Sai sót dữ liệu", "Có thể do nhập liệu, OCR, dấu phân cách hoặc mapping."),
        ("Thiếu dữ liệu", "Không thấy bằng chứng trong tập dữ liệu đang có."),
        ("Khác phương pháp", "Công thức, hệ số, ranh giới hoặc cách phân bổ khác."),
        ("Không thể so sánh", "Không đạt comparability gate; không được nâng thành mâu thuẫn."),
    ], widths=[4.4,11.8])
    add_callout(doc, "CẢNH BÁO", "Tên tab 'Phân tích & Đối chiếu mâu thuẫn' là tên giao diện. Người dùng vẫn phải xem cột Relationship và comparability; tab có thể chứa cả trường hợp không so sánh được hoặc mơ hồ.")
    add_summary(doc, ["Hệ thống nhận diện tín hiệu, không xác nhận hành vi.", "MISSING, AMBIGUOUS và NOT_COMPARABLE phải được hiểu khác CONTRADICTS."])

    add_chapter(doc, 5, "Tổng quan về GRI", "GRI là khung tham chiếu cho công bố tác động, không phải nhãn chứng nhận do dashboard cấp.")
    doc.add_paragraph("GRI (Global Reporting Initiative) phát triển bộ chuẩn báo cáo phát triển bền vững. Hệ thống chuẩn gồm Universal Standards áp dụng chung, Sector Standards theo ngành và Topic Standards theo chủ đề [1]–[4].")
    add_figure(doc, assets["gri"], "Quan hệ giữa Universal, Sector và Topic Standards")
    add_table(doc, "Vai trò các chuẩn GRI", ["Chuẩn", "Vai trò giản lược", "Cách dùng trong prototype"], [
        ("GRI 1", "Nền tảng, khái niệm, nguyên tắc và yêu cầu sử dụng GRI", "Giải thích bối cảnh; không tự động kiểm tra đầy đủ tuân thủ"),
        ("GRI 2", "Thông tin chung về tổ chức và thực hành báo cáo", "Tham chiếu provenance và một số công bố quản trị"),
        ("GRI 3", "Quy trình xác định và quản lý chủ đề trọng yếu", "Khung hiểu material topic"),
        ("GRI 11", "Sector Standard cho Oil and Gas", "Chuẩn ngành chính; liên kết chủ đề/metric và GW15"),
        ("Topic Standards", "Công bố chi tiết cho từng chủ đề", "metrics.yml ánh xạ GRI 201/207/302/303/305/306/403/404…"),
    ], widths=[2.4,7.1,6.7], font_size=8.2)
    add_h2(doc, "5.1. Vì sao GRI 11 phù hợp")
    doc.add_paragraph("GRI 11 được thiết kế cho các tổ chức dầu khí, bao gồm hoạt động lọc dầu. Chuẩn gợi ý các tác động có khả năng trọng yếu và công bố liên quan. Trong prototype, mã GRI đi cùng metric hoặc topic để người dùng mở đúng tài liệu tham chiếu; nó không thay việc đọc yêu cầu gốc.")
    add_h2(doc, "5.2. Cách đọc GRI reference trên dashboard")
    add_bullets(doc, ["Ví dụ 'GRI 305-1; GRI 11.1' nghĩa là metric được ánh xạ đồng thời tới công bố phát thải và chủ đề ngành.", "Dấu chấm/phần sau mã cần kiểm tra theo phiên bản chuẩn đang dùng.", "Tài liệu local có GRI 1, 2, 3, 11, 101, 102, 103, 303, 306; phiên bản cấu hình có thể tham chiếu thêm chuẩn khác chưa đính kèm."])
    add_callout(doc, "LƯU Ý", "GRI 11 có cập nhật phiên bản V1.1 vào năm 2026. Prototype và tài liệu nguồn cần ghi rõ phiên bản áp dụng trước khi so sánh báo cáo lịch sử: [CẦN NGƯỜI PHÁT TRIỂN XÁC NHẬN].")
    add_summary(doc, ["GRI 11 được dùng cùng Universal và Topic Standards.", "Reference trên dashboard là điểm dẫn để rà soát, không phải chứng nhận tuân thủ."])

    add_chapter(doc, 6, "Thuật ngữ ngành Oil and Gas", "Bảng tra nhanh các metric thường gặp trong báo cáo lọc hóa dầu.")
    oil_terms = [
        ("GHG", "Greenhouse gases", "Khí gây hiệu ứng nhà kính quy đổi CO2e", "tCO2e", "GRI 305 / 11.1", "Xem khí, hệ số và boundary"),
        ("Scope 1", "Direct GHG emissions", "Phát thải trực tiếp từ nguồn tổ chức kiểm soát", "tCO2e", "GRI 305-1", "Không gộp Scope 2"),
        ("Scope 2", "Energy indirect GHG", "Phát thải gián tiếp từ điện/năng lượng mua", "tCO2e", "GRI 305-2", "Market/location-based"),
        ("Phát thải tuyệt đối", "Absolute emissions", "Tổng phát thải trong kỳ", "tCO2e", "GRI 305", "Không so với intensity"),
        ("Cường độ phát thải", "GHG intensity", "Phát thải chia cho sản lượng/mẫu số", "tCO2e/tấn SP", "GRI 305-4", "Mẫu số phải giống"),
        ("Tổng năng lượng", "Energy consumption", "Năng lượng tiêu thụ trong boundary", "GJ", "GRI 302 / 11.1", "Xem loại năng lượng"),
        ("Nước đầu vào", "Water withdrawal", "Lượng nước lấy từ các nguồn", "m³", "GRI 303-3 / 11.6", "Nguồn và khu vực stress"),
        ("Nước thải", "Water discharge", "Nước xả ra theo điểm đến", "m³", "GRI 303-4 / 11.6", "Không đồng nhất withdrawal"),
        ("Chất thải nguy hại", "Hazardous waste", "Chất thải có đặc tính nguy hại", "tấn", "GRI 306-3 / 11.5", "Định nghĩa pháp lý"),
        ("Chất thải không nguy hại", "Non-hazardous waste", "Chất thải còn lại", "tấn", "GRI 306-3 / 11.5", "Không cộng trùng"),
        ("Sự cố tràn dầu", "Oil spill count", "Số vụ tràn dầu ghi nhận", "vụ", "GRI 11.8", "Ngưỡng 'đáng kể'"),
        ("LTIFR", "Lost Time Injury Frequency Rate", "Tần suất tai nạn mất ngày công", "ca/triệu giờ", "GRI 403-9 / 11.9", "Mẫu số giờ công"),
        ("TRIR", "Total Recordable Incident Rate", "Tần suất sự cố ghi nhận", "ca/triệu giờ", "GRI 403-9 / 11.9", "Định nghĩa ca"),
        ("Đào tạo", "Training hours", "Số giờ đào tạo bình quân", "giờ/người/năm", "GRI 404-1", "Đối tượng/mẫu số"),
        ("Đầu tư môi trường", "Environmental CAPEX", "Chi đầu tư tạo tài sản môi trường", "VND", "GRI 201 / 11.2", "Không so với OPEX"),
        ("Chi phí môi trường", "Environmental expense/OPEX", "Chi phí vận hành môi trường", "VND", "GRI 201 / 11.2", "Không so với CAPEX"),
        ("Tiền phạt môi trường", "Environmental fine", "Tiền phạt do không tuân thủ môi trường", "VND", "GRI 2-27", "Kỳ và cơ quan"),
        ("Thuế", "Tax paid", "Thuế và đóng góp ngân sách đã nộp", "VND", "GRI 207 / 11.21", "Paid khác accrued"),
    ]
    add_table(doc, "Thuật ngữ ngành Oil and Gas", ["Thuật ngữ", "Tên tiếng Anh", "Định nghĩa đơn giản", "Đơn vị", "GRI", "Lưu ý so sánh"], oil_terms, widths=[2.7,3.2,4.5,2.1,2.4,3.2], font_size=6.8)
    add_callout(doc, "VÍ DỤ", "Nếu LTIFR năm A tính trên nhân viên BSR còn năm B bao gồm cả nhà thầu, hai số có thể không so sánh được dù cùng đơn vị.")
    add_summary(doc, ["Tên gần giống chưa đủ để so sánh.", "Luôn kiểm tra định nghĩa, mẫu số, Scope và boundary."])


def part_iii(doc: Document, assets: dict, rules, scoring):
    add_part(doc, "III", "Cơ sở kỹ thuật và thuật toán")
    add_chapter(doc, 7, "Information Extraction", "Cách prototype biến văn bản dài thành các bản ghi có thể tìm kiếm và kiểm tra.")
    doc.add_paragraph("Information Extraction (IE – trích xuất thông tin) là quá trình nhận diện dữ kiện có cấu trúc từ văn bản không cấu trúc. Passage là đoạn văn; sentence là câu; claim là mệnh đề cần đánh giá; entity là thực thể như năm, tổ chức, đơn vị; metric là chỉ số đo lường.")
    add_h2(doc, "7.1. Cách hiểu phổ thông")
    doc.add_paragraph("Hãy hình dung người đọc dùng bút đánh dấu: xanh cho từ khóa môi trường, vàng cho số và đơn vị, tím cho năm, rồi ghi số trang bên cạnh. Prototype tự động hóa một phần thao tác đó bằng từ điển, regex và luật. Nó không 'hiểu' tài liệu như chuyên gia và có thể bỏ sót cách diễn đạt lạ.")
    add_h2(doc, "7.2. Công cụ đang dùng")
    add_table(doc, "Vai trò công cụ trích xuất", ["Công cụ", "Lý thuyết", "Trong source hiện tại"], [
        ("spaCy", "Nền tảng NLP xử lý Doc, token, sentence và pipeline", "spacy.blank('vi') + sentencizer để tách câu; regex fallback"),
        ("PhraseMatcher", "So khớp danh sách cụm từ hiệu quả", "Được nêu trong thiết kế/công nghệ; chưa thấy được gọi trực tiếp trong module extraction hiện tại"),
        ("EntityRuler", "Gán entity theo pattern", "Được nêu trong thiết kế; chưa thấy được gọi trực tiếp trong pipeline hiện tại"),
        ("Regex", "Biểu thức tìm mẫu số, đơn vị, năm và từ khóa", "Đang dùng trong làm sạch, tách câu và thuộc tính claim"),
        ("Từ điển/YAML", "Danh sách biến thể cho metric/chủ đề", "metrics.yml cung cấp variants Việt–Anh"),
    ], widths=[2.7,6.2,7.3])
    add_callout(doc, "LƯU Ý", "PhraseMatcher và EntityRuler là khả năng phù hợp về mặt thiết kế, nhưng source hiện tại chủ yếu dùng sentencizer, regex và từ khóa. Không nên mô tả chúng là bước đang chạy nếu chưa được tích hợp.")
    add_h2(doc, "7.3. Thuật toán tổng quát")
    add_bullets(doc, ["Đọc văn bản theo tài liệu/trang.", "Làm sạch khoảng trắng và ký tự bất thường.", "Tách passage và sentence.", "Tìm từ khóa ESG/metric.", "Nhận diện loại claim.", "Trích value, unit, time, baseline/target year, scope, boundary và direction nếu có.", "Gán topic/pillar.", "Lưu provenance và confidence."] , numbered=True)
    add_code(doc, """
    for page in document:
        text = clean_text(page.text)
        for sentence in sentence_split(text):
            if contains_esg_keyword(sentence):
                claim = classify_and_extract(sentence)
                claim.provenance = (document_id, year, type, page_number)
                save(claim, extraction_method="rule_based", confidence=score)
    """)
    add_h2(doc, "7.4. Ví dụ đầu vào–đầu ra")
    add_table(doc, "Ví dụ trích xuất claim minh họa", ["Đầu vào minh họa", "Đầu ra cấu trúc"], [
        ("'Năm 2024, công ty đặt mục tiêu giảm 10% cường độ phát thải vào 2025 so với 2022.'", "type=TARGET; value=10; unit=%; report_year=2024; baseline_year=2022; target_year=2025; direction=IMPROVE; metric=GHG_INTENSITY"),
    ], widths=[8.1,8.1])
    add_summary(doc, ["Trích xuất là rule-based, không phải suy luận ý định.", "Confidence phản ánh độ chắc chắn của bước máy, không phải độ đúng của claim."])

    add_chapter(doc, 8, "Chuẩn hóa dữ liệu", "Giữ nguyên dữ liệu gốc nhưng tạo một biểu diễn chung để so sánh an toàn.")
    doc.add_paragraph("Chuẩn hóa biến các cách viết khác nhau về một tên chuẩn, đơn vị chuẩn và kiểu số nhất quán. Mọi record vẫn giữ raw_value, raw_unit và source_text để truy vết. Nếu thiếu hệ số hoặc không biết boundary, hệ thống không nên tự quy đổi hay tự lấp.")
    add_h2(doc, "8.1. Các nhóm chuẩn hóa")
    add_table(doc, "Nguyên tắc chuẩn hóa", ["Nhóm", "Ví dụ", "Nguyên tắc"], [
        ("Tên metric", "'phát thải trực tiếp' → GHG_SCOPE_1", "Dựa variants và ngữ cảnh; tránh gộp Scope 1/2"),
        ("Năm", "'FY24' → 2024", "Tách report year khỏi metric year/baseline/target"),
        ("Khối lượng CO2e", "1 ktCO2e = 1.000 tCO2e; 1 tCO2e = 1.000 kgCO2e", "Chỉ quy đổi khi cùng đại lượng"),
        ("Tiền", "1 tỷ đồng = 1.000 triệu = 1.000.000 nghìn VND", "Phân biệt VND, nghìn, triệu, tỷ"),
        ("Tỷ lệ", "5% ↔ 0,05", "Lưu rõ dạng hiển thị và cơ số"),
        ("Scope/boundary", "Scope 1; hợp nhất", "Chuẩn hóa nhãn nhưng không xóa khác biệt"),
        ("Giá trị thiếu", "N/A, không nêu, OCR hỏng", "Gắn trạng thái; không thay bằng 0"),
    ], widths=[3.0,5.4,7.8])
    add_h2(doc, "8.2. Ví dụ quy đổi")
    add_code(doc, """
    2.500.000 kgCO2e × (1 tCO2e / 1.000 kgCO2e) = 2.500 tCO2e
    12,5 tỷ VND × 1.000.000.000 = 12.500.000.000 VND
    """)
    add_callout(doc, "CẢNH BÁO", "Không quy đổi CAPEX thành OPEX; không quy đổi tổng phát thải thành cường độ nếu không có mẫu số; không coi hai boundary khác nhau là cùng dữ liệu.")
    add_summary(doc, ["Raw value/unit luôn được giữ.", "Thiếu dữ kiện dẫn đến AMBIGUOUS hoặc NOT_COMPARABLE, không phải CONTRADICTS."])

    add_chapter(doc, 9, "Phân loại claim")
    claim_rows = [
        ("QUALITATIVE", "Mô tả không có số", "nỗ lực, xanh, bền vững", "'Áp dụng giải pháp xanh'", "actor/action/object/qualifier", "Chính sách, phương pháp", "Mơ hồ, thiếu bằng chứng"),
        ("QUANTITATIVE", "Có giá trị/đơn vị", "%/tấn/m³/GJ", "'Phát thải 1.000 tCO2e'", "value/unit/time/scope", "Metric cùng kỳ", "Sai đơn vị/scope"),
        ("TARGET", "Cam kết tương lai", "mục tiêu, đến 2030", "'Giảm 20% đến 2030'", "baseline/target/scope", "Kế hoạch và tiến độ", "Weak target/future only"),
        ("ACHIEVEMENT", "Tuyên bố đã đạt", "đạt, hoàn thành, giảm", "'Đã giảm 8%'", "value/time/baseline", "Số trước-sau", "Contradiction"),
        ("POLICY", "Chính sách/quy trình", "chính sách, quy chế", "'Ban hành quy trình tràn dầu'", "actor/action/scope", "Văn bản/quy trình", "Thiếu hiệu lực/phạm vi"),
        ("COMPARATIVE", "So sánh giữa kỳ/đối tượng", "tăng, giảm, so với", "'Thấp hơn năm 2023'", "direction/time/baseline", "Metric hai kỳ", "Khác định nghĩa/boundary"),
    ]
    add_table(doc, "Sáu loại claim", ["Loại", "Định nghĩa", "Từ khóa", "Ví dụ", "Thuộc tính", "Evidence cần", "Rủi ro"], claim_rows, widths=[2.3,2.7,2.4,3.3,3.0,3.0,2.7], font_size=6.6)
    doc.add_paragraph("Trong source hiện tại, phân loại dùng từ khóa và thuộc tính regex. Một câu có thể chứa nhiều ý; prototype chọn một nhãn chính. Khi câu bị chia sai hoặc có bảng nối tiếp, người dùng cần xem source_text và passage.")
    add_callout(doc, "VÍ DỤ", "'BSR đặt mục tiêu giảm và đã đầu tư 50 tỷ đồng' chứa TARGET lẫn QUANTITATIVE/ACHIEVEMENT. Nên tách thành hai claim nếu cần đánh giá độc lập.")
    add_summary(doc, ["Loại claim quyết định loại evidence cần tìm.", "Một nhãn tự động không thay việc đọc câu đầy đủ."])

    add_chapter(doc, 10, "Evidence Matching", "Tìm ứng viên trước, rồi xác minh khả năng so sánh trước khi kết luận.")
    add_h2(doc, "10.1. Cách hiểu phổ thông")
    doc.add_paragraph("Nếu claim là câu hỏi, evidence matching là bước tìm các trang có khả năng chứa câu trả lời. RapidFuzz so sánh tập từ để xếp hạng độ giống; source cộng điểm khi cùng metric và cùng năm. Điểm giống chỉ giúp tạo ứng viên, không chứng minh nội dung hỗ trợ.")
    add_h2(doc, "10.2. Bước 1 – Tạo ứng viên")
    add_bullets(doc, ["Cùng topic/pillar hoặc metric code.", "Từ khóa/biến thể tương tự bằng token_set_ratio.", "Cùng report year, metric year hoặc baseline liên quan.", "Ưu tiên đoạn gần claim khi provenance cho phép.", "Source hiện cộng 0,35 nếu cùng metric và 0,15 nếu cùng năm; tổng điểm được chặn ở 1,0."])
    add_h2(doc, "10.3. Bước 2 – Comparability gate")
    add_table(doc, "Cổng kiểm tra khả năng so sánh", ["Điều kiện", "Câu hỏi", "Nếu không đạt"], [
        ("Metric", "Có cùng mã/định nghĩa chỉ số?", "NOT_COMPARABLE"),
        ("Kỳ", "Cùng năm hoặc đúng baseline?", "NOT_COMPARABLE/AMBIGUOUS"),
        ("Đơn vị", "Giống hoặc quy đổi chắc chắn?", "AMBIGUOUS/NOT_COMPARABLE"),
        ("Scope", "Cùng Scope 1/2 hoặc phạm vi tương đương?", "NOT_COMPARABLE"),
        ("Boundary", "Cùng hợp nhất/riêng lẻ/cơ sở?", "NOT_COMPARABLE"),
        ("Định nghĩa", "Cùng phương pháp, đối tượng và mẫu số?", "NOT_COMPARABLE"),
        ("Value kind", "Cùng absolute hoặc intensity?", "NOT_COMPARABLE"),
    ], widths=[2.7,8.0,5.5])
    status_rows = [
        ("SUPPORTS", "Bằng chứng phù hợp và cùng điều kiện", "Claim 1.000 tCO2e; bảng 1.000 tCO2e"),
        ("PARTIAL_SUPPORT", "Hỗ trợ một phần; còn thiếu thuộc tính", "Có số nhưng thiếu scope"),
        ("CONTRADICTS", "Cặp so sánh được nhưng nội dung trái nhau", "Claim giảm; metric so sánh được cho thấy tăng vượt tolerance"),
        ("MISSING", "Không tìm thấy evidence trong tập dữ liệu", "Không có metric cùng topic/kỳ"),
        ("AMBIGUOUS", "Có ứng viên nhưng chưa đủ dữ kiện", "Đơn vị ghi 'tấn' không rõ CO2e"),
        ("NOT_COMPARABLE", "Có evidence nhưng khác điều kiện", "CAPEX khác OPEX; consolidated khác standalone"),
    ]
    add_table(doc, "Sáu trạng thái evidence matching", ["Trạng thái", "Ý nghĩa", "Ví dụ minh họa"], status_rows, widths=[3.2,6.3,6.7])
    add_callout(doc, "CẢNH BÁO", "Không nâng NOT_COMPARABLE thành CONTRADICTS chỉ vì hai con số khác nhau. Đây là nguyên tắc quan trọng nhất để hạn chế false positive.")
    add_summary(doc, ["Fuzzy matching chỉ tạo ứng viên.", "Comparability gate quyết định có được phép đối chiếu định lượng hay không."])

    add_chapter(doc, 11, "Rule Engine", "Mỗi luật là một kiểm tra có điều kiện kích hoạt, loại trừ, severity và giải thích.")
    doc.add_paragraph("Rule Engine (bộ máy luật) biến logic chuyên gia thành các kiểm tra lặp lại được. Prototype chọn rule-based vì dễ giải thích, không cần dữ liệu gán nhãn lớn và không dùng API trả phí. Hạn chế là độ bao phủ phụ thuộc từ khóa và cấu hình; luật có thể tạo false positive nếu provenance hoặc scope thiếu.")
    rule_names_vi = {
        "GW01":"Tuyên bố mơ hồ", "GW02":"Khoảng trống bằng chứng", "GW03":"Mục tiêu yếu", "GW04":"Mâu thuẫn giữa tài liệu", "GW05":"Mâu thuẫn theo thời gian", "GW06":"Công bố chọn lọc", "GW07":"Thay đổi năm cơ sở", "GW08":"Thay đổi Scope/boundary", "GW09":"Không khớp đơn vị", "GW10":"Nhầm tuyệt đối/cường độ", "GW11":"Thiếu phương pháp", "GW12":"Tuyên bố thiếu cân bằng", "GW13":"Chỉ hứa tương lai", "GW14":"Khoảng trống restatement", "GW15":"Thiếu công bố GRI"}
    rule_examples = {
        "GW01":"'cải thiện đáng kể' không số", "GW02":"claim định lượng nhưng không evidence", "GW03":"mục tiêu thiếu baseline", "GW04":"hai tài liệu cùng scope ghi trái nhau", "GW05":"nói cải thiện nhưng chuỗi số xấu đi", "GW06":"hai năm có số, năm hiện tại thiếu", "GW07":"đổi baseline không giải trình", "GW08":"Scope/boundary thay đổi", "GW09":"kg và tấn không xác định quy đổi", "GW10":"absolute so với intensity", "GW11":"có số nhưng thiếu phương pháp", "GW12":"chỉ nêu chiều tích cực", "GW13":"lặp mục tiêu không tiến độ", "GW14":"sửa số cũ không restatement", "GW15":"chủ đề GRI 11 thiếu disclosure"}
    rows=[]
    for rule in rules:
        rid=rule["rule_id"]
        cond = "; ".join(str(x) for x in (rule.get("conditions") or []))
        excl = "; ".join(str(x) for x in (rule.get("exclusions") or []))
        rows.append((rid, rule_names_vi.get(rid, rule.get("name")), rule.get("description",""), cond, excl, rule.get("severity"), rule_examples.get(rid,"—"), "Mở claim/evidence; kiểm tra provenance và điều kiện so sánh"))
    add_table(doc, "Danh mục 15 luật đang bật trong rules.yml", ["ID", "Tên", "Mục đích", "Kích hoạt", "Ngoại lệ", "Sev.", "Ví dụ", "Cách kiểm tra"], rows, widths=[1.3,2.5,3.4,3.7,3.2,1.0,3.0,3.3], font_size=5.6)
    add_h2(doc, "11.1. Severity và explanation")
    doc.add_paragraph("Severity là mức nghiêm trọng cấu hình từ 1 đến 5, không phải xác suất doanh nghiệp vi phạm. Source gán trọng số severity lần lượt 0,2; 0,4; 0,6; 0,8; 1,0. Mỗi rule result lưu rule ID, risk type, score, explanation tiếng Việt và provenance để drill-down.")
    add_callout(doc, "LƯU Ý", "Cả 15 luật trong rules.yml đều enabled=true tại thời điểm kiểm chứng. Nếu tắt luật, cần chạy lại pipeline và ghi phiên bản cấu hình.")
    add_summary(doc, ["Rule-based dễ giải thích nhưng phụ thuộc cấu hình.", "Severity không phải bằng chứng hay xác suất pháp lý."])

    add_chapter(doc, 12, "Thuật toán tính điểm rủi ro", "Điểm 0–100 tổng hợp năm nhóm tín hiệu; điểm cao chỉ cho biết cần ưu tiên đọc.")
    add_code(doc, """
    Risk Claim = 100 × (
        0,35 × Contradiction
      + 0,25 × Evidence Gap
      + 0,15 × Vagueness
      + 0,15 × Target Integrity
      + 0,10 × Temporal Consistency
    )
    """)
    comp_rows = [
        ("Contradiction", "GW04", "Mâu thuẫn giữa tài liệu", "0,35"),
        ("Evidence Gap", "GW02, GW06, GW15", "Thiếu/chọn lọc/omission", "0,25"),
        ("Vagueness", "GW01, GW11", "Mơ hồ hoặc thiếu phương pháp", "0,15"),
        ("Target Integrity", "GW03, GW07, GW13", "Chất lượng mục tiêu/baseline/tiến độ", "0,15"),
        ("Temporal Consistency", "GW05, GW08, GW10, GW12, GW14", "Nhất quán theo kỳ và phạm vi", "0,10"),
    ]
    add_table(doc, "Thành phần Risk Claim theo source", ["Thành phần", "Luật", "Ý nghĩa", "Trọng số"], comp_rows, widths=[3.2,4.2,6.8,2.0])
    doc.add_paragraph("Mỗi thành phần lấy giá trị lớn nhất của severity weight trong các luật cùng nhóm đã kích hoạt. Nếu không có luật, thành phần bằng 0. Tổng được nhân 100 và chặn trong [0,100]. Confidence hiển thị là trung bình giữa claim confidence và evidence coverage. Topic/pillar/company trên dashboard hiện tổng hợp bằng trung bình score của claim trong tập lọc; materiality weighting chưa được hiện thực hóa.")
    add_table(doc, "Phân loại điểm", ["Khoảng điểm", "Mức", "Cách hiểu"], [("0–29","Thấp","Ít tín hiệu cần xem xét"),("30–59","Trung bình","Cần kiểm tra claim và evidence"),("60–79","Cao","Có nhiều yếu tố rủi ro"),("80–100","Rất cao","Ưu tiên rà soát thủ công")], widths=[3.0,3.6,9.6])
    add_h2(doc, "12.1. Ví dụ tính từng bước – dữ liệu minh họa")
    add_bullets(doc, [
        "Một claim demo kích hoạt GW04 severity 5 → Contradiction = 1,0.",
        "Kích hoạt GW02 severity 3 → Evidence Gap = 0,6.",
        "Không có GW01/GW11 → Vagueness = 0.",
        "Kích hoạt GW03 severity 3 → Target Integrity = 0,6.",
        "Không có luật temporal → Temporal Consistency = 0.",
        "Risk = 100 × (0,35×1 + 0,25×0,6 + 0,15×0 + 0,15×0,6 + 0,10×0) = 59,0 → Trung bình.",
    ], numbered=True)
    add_callout(doc, "CẢNH BÁO", "Ví dụ trên minh họa công thức, không phải điểm của một claim BSR thực tế. Điểm 59 không có nghĩa là 59% khả năng greenwashing.")
    add_summary(doc, ["Điểm là thước ưu tiên rà soát.", "Evidence coverage và confidence phải được đọc cùng Risk Score."])

    add_chapter(doc, 13, "Thuật toán tổng thể", "Một pipeline có điểm kiểm soát, trạng thái thiếu và provenance xuyên suốt.")
    add_figure(doc, assets["technical"], "Pipeline kỹ thuật và các điểm kiểm soát")
    add_table(doc, "Đầu vào và đầu ra từng bước", ["Bước", "Đầu vào", "Đầu ra", "Ngoại lệ/kiểm soát"], [
        ("Adapter", "JSON/CSV/PDF text", "document, passage, record", "Cờ is_demo_data; không ghi đè nguồn"),
        ("Preprocess", "text theo trang", "câu sạch", "OCR/font; giữ page"),
        ("Extraction", "câu", "claim/metric thô", "confidence và method"),
        ("Normalization", "value/unit thô", "canonical value/unit", "không quy đổi nếu thiếu"),
        ("Candidate", "claim + evidence", "danh sách xếp hạng", "RapidFuzz chỉ hỗ trợ tìm"),
        ("Comparability", "cặp ứng viên", "comparable/reasons", "scope/boundary/unit/kind"),
        ("Matching", "cặp hợp lệ", "6 relationship", "tolerance"),
        ("Rules", "claim/match/context", "rule_results", "conditions/exclusions"),
        ("Scoring", "rule_results", "claim/topic score", "weights/bands"),
        ("Dashboard", "SQLite", "KPI/charts/tables", "filters và no-data state"),
    ], widths=[2.4,3.5,3.7,6.6], font_size=7.5)
    add_h2(doc, "13.1. Pseudocode toàn hệ thống")
    add_code(doc, """
    docs = import_with_provenance(raw_files)
    for doc in docs:
        claims, metrics = extract(normalize_text(doc))
        metrics = normalize_values(metrics, metrics_yml)
        for claim in claims:
            candidates = rank_evidence(claim, metrics, rapidfuzz=True)
            relationship = verify_comparability_then_match(claim, candidates)
            alerts = run_enabled_rules(claim, relationship, context)
            score = calculate_claim_risk(alerts, scoring_yml)
            persist(claim, relationship, alerts, score)
    aggregate_by_topic_year_pillar()
    render_dashboard_from_sqlite()
    """)
    add_h2(doc, "13.2. Độ phức tạp và hạn chế false positive")
    doc.add_paragraph("Nếu có C claim và E evidence, so khớp toàn cục ngây thơ có thể gần O(C×E). Lọc theo metric/topic/year làm giảm số cặp thực tế. Prototype nhỏ nên ưu tiên minh bạch hơn tối ưu hóa phức tạp. Các rào chắn chính chống false positive là comparability gate, tolerance, exclusions của luật, trạng thái NOT_COMPARABLE và provenance.")
    add_h2(doc, "13.3. Xử lý thiếu và provenance")
    doc.add_paragraph("Dữ liệu thiếu không được điền 0. MISSING dùng khi không tìm thấy evidence; AMBIGUOUS khi có ứng viên nhưng thiếu dữ kiện; NOT_COMPARABLE khi dữ liệu khác điều kiện. Provenance tối thiểu gồm document_id, report_year, document_type, page_number, source_text, extraction_method và confidence; metric còn giữ raw/normalized value/unit, metric year, scope, boundary và denominator.")
    add_summary(doc, ["Pipeline lưu nguồn gốc ở từng lớp.", "Comparability và trạng thái thiếu là cơ chế trung tâm để tránh kết luận sai."])


def part_iv(doc: Document, assets: dict):
    add_part(doc, "IV", "Hướng dẫn sử dụng")
    add_chapter(doc, 14, "Yêu cầu hệ thống", "Chuẩn bị môi trường tối thiểu để chạy prototype trên máy cá nhân.")
    add_table(doc, "Yêu cầu kỹ thuật", ["Hạng mục", "Yêu cầu/khuyến nghị"], [
        ("Phần cứng", "CPU 2 lõi trở lên, RAM 8 GB, còn trống khoảng 2 GB; nhiều PDF/OCR có thể cần thêm"),
        ("Hệ điều hành", "Windows 10/11; Linux/macOS có thể chạy nếu các thư viện tương thích"),
        ("Python", "3.11 hoặc bản ổn định tương đương; source hiện được kiểm thử trong môi trường dự án"),
        ("Trình duyệt", "Microsoft Edge, Chrome hoặc Firefox bản hiện hành; màn hình laptop từ 1366×768"),
        ("Thư viện chính", "pandas, spaCy, RapidFuzz, PyYAML, PyMuPDF/pdfplumber, SQLite, Plotly Dash, dash-bootstrap-components, pytest"),
    ], widths=[3.7,12.5])
    add_h2(doc, "14.1. Cấu trúc thư mục cần biết")
    add_code(doc, """
    esg-tracker/
    ├── app.py                     # dashboard
    ├── config/                    # metrics.yml, rules.yml, scoring.yml
    ├── data/raw|processed|sample  # dữ liệu theo lớp
    ├── database/                  # schema.sql, esg_tracker.db
    ├── src/                       # preprocessing → scoring
    ├── scripts/                   # initialize, import, run_pipeline
    ├── dashboard/                 # pages, components, assets
    └── tests/                     # unit test
    """)
    add_callout(doc, "LƯU Ý", "Dữ liệu nguồn ở thư mục ESG cha được adapter đọc; không di chuyển hoặc ghi đè nếu chưa sao lưu. File SQLite mặc định: esg-tracker/database/esg_tracker.db.")
    add_summary(doc, ["Python 3.11 và trình duyệt hiện đại là đủ cho demo.", "Ba file YAML là điểm cấu hình nghiệp vụ chính."])

    add_chapter(doc, 15, "Cài đặt và khởi động", "Quy trình Windows từng bước; các lệnh đã đối chiếu README và source.")
    steps = [
        ("1", "Cài Python", "Tải Python 3.11 từ python.org; chọn Add Python to PATH."),
        ("2", "Mở terminal", "Mở Windows PowerShell; kiểm tra python --version."),
        ("3", "Vào dự án", r"cd C:\Users\THINKPAD\Documents\ChatGPT\ESG\esg-tracker"),
        ("4", "Tạo môi trường", "python -m venv .venv"),
        ("5", "Kích hoạt", r".\.venv\Scripts\Activate.ps1"),
        ("6", "Cài thư viện", "pip install -r requirements.txt"),
        ("7", "Khởi tạo DB", "python scripts/initialize_database.py"),
        ("8", "Nhập dữ liệu", "python scripts/import_data.py"),
        ("9", "Chạy pipeline", "python scripts/run_pipeline.py"),
        ("10", "Mở dashboard", "python app.py"),
        ("11", "Truy cập", "http://127.0.0.1:8050"),
    ]
    add_table(doc, "Quy trình cài đặt trên Windows", ["Bước", "Thao tác", "Lệnh/giải thích"], steps, widths=[1.2,4.0,11.0])
    add_h2(doc, "15.1. Lệnh đầy đủ")
    add_code(doc, r"""
    cd C:\Users\THINKPAD\Documents\ChatGPT\ESG\esg-tracker
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python scripts/initialize_database.py
    python scripts/import_data.py
    python scripts/run_pipeline.py
    python app.py
    """)
    add_h2(doc, "15.2. Ý nghĩa")
    add_bullets(doc, ["venv cô lập thư viện của dự án.", "initialize_database.py tạo schema SQLite.", "import_data.py nạp nguồn Phase 1 và demo, gắn cờ nguồn.", "run_pipeline.py chuẩn hóa, matching, chạy luật và scoring.", "app.py mở web server; nếu database rỗng, ứng dụng tự khởi tạo/nhập/chạy pipeline."])
    add_callout(doc, "CẢNH BÁO", "Khi PowerShell chặn Activate.ps1, không thay đổi ExecutionPolicy toàn hệ thống nếu không có quyền quản trị. Có thể dùng Command Prompt với .venv\\Scripts\\activate.bat hoặc gọi trực tiếp .venv\\Scripts\\python.exe.")
    add_summary(doc, ["Mở dashboard tại 127.0.0.1:8050.", "Không đóng cửa sổ đang chạy app nếu còn sử dụng dashboard."])

    add_chapter(doc, 16, "Làm quen giao diện", "Nhận diện các vùng trên màn hình trước khi lọc và drill-down.")
    add_figure(doc, assets["ui"], "Sơ đồ đánh số các thành phần giao diện prototype")
    add_table(doc, "Chú giải thành phần giao diện", ["Số", "Thành phần", "Công dụng"], [
        ("1", "Bộ lọc đa chiều", "Lọc đồng bộ theo nguồn, năm, tài liệu, pillar, topic, metric, rule, severity, relationship"),
        ("2–6", "Năm tab", "Chuyển giữa tổng quan, chủ đề, xu hướng, đối chiếu và provenance"),
        ("7–12", "KPI", "Hiển thị score, mức, số claim/cảnh báo, coverage và confidence"),
        ("13", "DataTable", "Tìm kiếm/lọc/sắp xếp/phân trang; chọn dòng để drill-down khi callback hỗ trợ"),
    ], widths=[1.5,4.8,9.9])
    add_h2(doc, "16.1. Tên tab đã đối chiếu giao diện thật")
    add_bullets(doc, ["📊 Tổng quan rủi ro", "🗺️ Ma trận rủi ro chủ đề", "📈 Xu hướng chỉ số định lượng", "⚖️ Phân tích & Đối chiếu mâu thuẫn", "🔍 Truy xuất nguồn gốc bằng chứng"])
    add_h2(doc, "16.2. Tooltip, loading, reset và no-data")
    doc.add_paragraph("Biểu đồ Plotly hiển thị tooltip khi rê chuột. Các khu vực cập nhật có loading state. Nút 'Đặt lại bộ lọc' đưa bộ lọc về mặc định. Khi tổ hợp lọc không có bản ghi, giao diện hiển thị trạng thái không có dữ liệu thay vì tự suy ra số 0.")
    add_callout(doc, "LƯU Ý", "Ảnh chụp toàn màn hình tổng quan đã được kiểm tra trực tiếp tại localhost trong quá trình biên soạn. Ảnh từng tab ở bản bàn giao chính thức: [CHÈN ẢNH: ảnh chụp đủ 5 tab tại phiên bản phát hành].")
    add_summary(doc, ["Bộ lọc tác động trên 5 màn hình.", "Luôn kiểm tra chế độ Dữ liệu minh họa hay Nguồn BSR trước khi đọc KPI."])

    add_chapter(doc, 17, "Hướng dẫn từng màn hình", "Mỗi mục có mục đích, thao tác, cách đọc, ví dụ, lỗi và vị trí ảnh.")
    screens = [
        ("17.1. Tổng quan rủi ro", "Nắm bức tranh nhanh và chọn claim ưu tiên.", "Khi bắt đầu một phiên rà soát hoặc so sánh năm.", "Risk Score, phân loại, claim, cảnh báo, evidence coverage, confidence, điểm E/S/G, biểu đồ rủi ro và bảng claim.", ["Chọn Chế độ dữ liệu.", "Chọn một năm hoặc Tất cả.", "Quan sát KPI và coverage.", "Sắp xếp bảng theo Risk Score.", "Chọn claim để mở chi tiết nếu drill-down khả dụng."], "Đọc Risk Score cùng coverage/confidence; một tập ít evidence có thể tạo nhiều GW02.", "Lọc Demo–2024 và tìm claim điểm cao để luyện thao tác.", "Nhầm Demo với nguồn thực; coi trung bình là xác suất.", "[CHÈN ẢNH: Tab Tổng quan rủi ro]"),
        ("17.2. Ma trận rủi ro chủ đề", "Tìm topic/năm cần ưu tiên.", "Khi cần so sánh 2022–2025 hoặc xem GRI reference.", "Heatmap topic × year, score, số claim/cảnh báo và tham chiếu GRI.", ["Chọn pillar hoặc topic.", "Rê chuột để xem tooltip.", "Bấm ô heatmap để lọc danh sách claim khi callback hỗ trợ.", "Đối chiếu số claim trước khi so sánh màu."], "Màu thể hiện score tổng hợp; ô trống là không có dữ liệu, không phải rủi ro bằng 0.", "Tìm chủ đề có nhiều cảnh báo trong 2024.", "So màu khi số claim quá khác; bỏ qua ô trống.", "[CHÈN ẢNH: Tab Ma trận rủi ro chủ đề]"),
        ("17.3. Xu hướng chỉ số định lượng", "Xem diễn biến metric qua năm.", "Khi kiểm tra phát thải, năng lượng, nước, chất thải, an toàn hoặc chi phí.", "Bộ chọn metric, unit/value kind, đường xu hướng, marker và tooltip provenance.", ["Chọn metric code.", "Chọn nguồn và khoảng năm.", "Đọc trục X là năm; trục Y và đơn vị.", "Kiểm tra absolute/intensity, Scope và boundary.", "Tìm gap nếu một năm không có marker."], "Đường tăng/giảm chỉ có ý nghĩa khi chuỗi so sánh được.", "Chọn GHG_SCOPE_1 và kiểm tra năm 2022–2025 trong Demo.", "Gộp Scope 1/2; so CAPEX với ENV_EXPENSE.", "[CHÈN ẢNH: Tab Xu hướng chỉ số định lượng]"),
        ("17.4. Phân tích & Đối chiếu mâu thuẫn", "Đọc claim và evidence cạnh nhau.", "Khi relationship là CONTRADICTS, AMBIGUOUS hoặc NOT_COMPARABLE.", "Claim, evidence, metric, năm, unit, scope, boundary, relationship, Rule ID, severity, explanation.", ["Lọc relationship.", "Chọn một dòng.", "So năm và metric.", "Kiểm tra unit convertibility.", "Kiểm tra Scope/boundary/value kind.", "Đọc explanation và trang nguồn."], "CONTRADICTS chỉ hợp lệ khi comparable=true; NOT_COMPARABLE là cơ chế bảo vệ.", "Chọn trường hợp khác boundary trong Demo.", "Chỉ nhìn hai số; bỏ qua comparability reasons.", "[CHÈN ẢNH: Tab Phân tích & Đối chiếu mâu thuẫn]"),
        ("17.5. Truy xuất nguồn gốc bằng chứng", "Rà nguyên văn và provenance.", "Bước cuối trước khi trích dẫn hoặc kết luận nghiên cứu.", "Claim/evidence nguyên văn, confidence, relationship, tài liệu, loại báo cáo, năm, trang, explanation.", ["Chọn claim.", "Đọc nguyên văn không cắt ngữ cảnh.", "Mở tài liệu nguồn theo tên/trang.", "Kiểm tra bảng/ghi chú chân trang.", "Ghi nhận quyết định rà soát thủ công."], "Confidence thấp ưu tiên đọc PDF; page number có thể cần kiểm tra nếu OCR lệch.", "Truy ngược một GW02 đến trang báo cáo.", "Trích câu rời ngữ cảnh; coi confidence là độ đúng doanh nghiệp.", "[CHÈN ẢNH: Tab Truy xuất nguồn gốc bằng chứng]"),
    ]
    for title,purpose,when,components,steps,reading,example,errors,image_marker in screens:
        add_h2(doc,title)
        add_h3(doc,"1. Mục đích"); doc.add_paragraph(purpose)
        add_h3(doc,"2. Khi nào sử dụng"); doc.add_paragraph(when)
        add_h3(doc,"3. Thành phần giao diện"); doc.add_paragraph(components)
        add_h3(doc,"4. Các bước thao tác"); add_bullets(doc,steps,numbered=True)
        add_h3(doc,"5. Cách đọc kết quả"); doc.add_paragraph(reading)
        add_h3(doc,"6. Ví dụ minh họa"); add_callout(doc,"VÍ DỤ",example+" Đây là thao tác trên dữ liệu minh họa, không phải kết quả BSR thực tế.")
        add_h3(doc,"7. Lỗi thường gặp"); doc.add_paragraph(errors)
        add_h3(doc,"8. Ảnh minh họa"); doc.add_paragraph(image_marker)
    add_summary(doc, ["Mỗi tab trả lời một câu hỏi khác nhau.", "Drill-down về nguyên văn là bước bắt buộc trước khi diễn giải."])

    add_chapter(doc, 18, "Các kịch bản sử dụng", "Tám bài thực hành từ tổng quan đến trang nguồn.")
    scenarios = [
        ("1. Xem tổng quan một năm", "Chọn đúng nguồn và năm", "Chế độ dữ liệu → Năm → tab Tổng quan → đọc KPI", "KPI/bảng được lọc", "So score với coverage; không kết luận hành vi"),
        ("2. So sánh E/S/G giữa năm", "Có claim ở các năm", "Lần lượt chọn năm, ghi E/S/G; giữ cùng nguồn", "Bảng so sánh nhất quán", "Kiểm tra số claim từng pillar"),
        ("3. Tìm topic nhiều cảnh báo", "Có topic_scores/rules", "Mở Ma trận → rê tooltip → chọn ô/topic", "Danh sách claim liên quan", "Nhiều cảnh báo có thể do thiếu evidence"),
        ("4. Claim thiếu bằng chứng", "Relationship=MISSING", "Lọc MISSING → mở viewer → tìm tài liệu/trang khác", "Biết claim chưa có evidence trong corpus", "Không viết 'sai' hay 'mâu thuẫn'"),
        ("5. Claim bị mâu thuẫn", "Relationship=CONTRADICTS", "Mở Explorer → xác nhận comparable → so giá trị/tolerance → trang nguồn", "Có hồ sơ đối chiếu", "Cần chuyên gia xác minh phương pháp"),
        ("6. NOT_COMPARABLE", "Có evidence nhưng khác điều kiện", "Lọc NOT_COMPARABLE → đọc reasons → so Scope/boundary/kind", "Xác định nguyên nhân không so sánh", "Không đổi thành CONTRADICTS"),
        ("7. Xu hướng phát thải 2022–2025", "Dùng chế độ Demo nếu cần đủ 4 năm", "Chọn GHG_SCOPE_1/2 hoặc intensity → kiểm tra unit/scope", "Đường xu hướng và gap", "2022 Demo không phải số BSR thật"),
        ("8. Từ cảnh báo đến trang", "Có document/page provenance", "Chọn alert → Viewer → ghi document, year, page → mở PDF", "Tái kiểm tra được nguồn", "Số trang PDF và trang in có thể lệch"),
    ]
    for name,pre,steps,expected,interpretation in scenarios:
        add_h2(doc, name)
        add_table(doc, f"Kịch bản {name}", ["Mục", "Nội dung"], [("Mục tiêu",name.split(". ",1)[1]),("Điều kiện đầu vào",pre),("Các bước",steps),("Kết quả mong đợi",expected),("Cách diễn giải",interpretation),("Lưu ý","Dữ liệu ví dụ không đại diện kết quả thực tế BSR")], widths=[4.0,12.2], font_size=8.3)
    add_summary(doc, ["Luôn bắt đầu bằng việc chọn đúng chế độ dữ liệu.", "Kết thúc bằng provenance và đọc nguyên văn."])

    add_chapter(doc, 19, "Cách đọc kết quả đúng", "Một quy trình năm bước để tránh biến tín hiệu thành phán quyết.")
    add_figure(doc, assets["reading"], "Cách đọc một cảnh báo an toàn")
    add_table(doc, "Nên làm và không nên làm", ["Nên làm", "Không nên làm"], [
        ("Đọc claim và evidence nguyên văn", "Chỉ nhìn Risk Score"),
        ("Kiểm tra metric, năm, unit, Scope, boundary", "So hai số vì trông gần giống"),
        ("Phân biệt absolute/intensity và mẫu số", "Suy ra tổng lượng giảm từ intensity giảm"),
        ("Tìm giải trình baseline/restatement", "Coi thay đổi là cố ý che giấu"),
        ("Đọc MISSING là 'chưa thấy trong corpus'", "Đọc MISSING như CONTRADICTS"),
        ("Ưu tiên kiểm tra confidence thấp", "Coi confidence là xác suất claim đúng"),
        ("Ghi lại phiên bản cấu hình", "So điểm từ hai cấu hình khác nhau"),
    ], widths=[8.1,8.1])
    add_callout(doc, "CẢNH BÁO", "Cách viết đúng trong báo cáo: 'Prototype phát hiện tín hiệu GW08 do boundary khác nhau; cặp được gắn NOT_COMPARABLE và cần rà soát thủ công.'")
    add_summary(doc, ["Risk Score là chỉ báo ưu tiên.", "Phải xem nguồn gốc, comparability và confidence trước khi sử dụng kết quả."])


def part_v(doc: Document):
    add_part(doc, "V", "Quản trị và khắc phục sự cố")
    add_chapter(doc, 20, "Nhập và cập nhật dữ liệu", "Quản lý dữ liệu theo lớp, có sao lưu và cờ nguồn.")
    add_h2(doc, "20.1. Định dạng và trường dữ liệu")
    add_table(doc, "Trường đầu vào tối thiểu", ["Nhóm", "Trường chính", "Bắt buộc/lưu ý"], [
        ("Document", "company, report_year, document_type, file_name/path", "Bắt buộc để provenance"),
        ("Passage/claim", "source_text, page_number, extraction_method, confidence", "page có thể null nhưng phải ghi trạng thái"),
        ("Metric", "metric_code, raw_value, raw_unit, metric_year", "Giữ cả normalized_value/unit"),
        ("Comparability", "scope, boundary, value_kind, definition, denominator", "Không tự lấp khi thiếu"),
        ("Nguồn", "is_demo_data", "true cho demo; false cho nguồn BSR"),
    ], widths=[3.0,7.1,6.1])
    add_h2(doc, "20.2. Thêm báo cáo/năm mới")
    add_bullets(doc, ["Sao lưu database và cấu hình.", "Đặt file nguồn vào vùng raw hoặc cập nhật adapter theo schema Phase 1.", "Dùng tên ổn định: BSR_<document_type>_<year>.<ext>.", "Bổ sung manifest/hash nếu quy trình yêu cầu.", "Chạy initialize chỉ khi tạo DB mới; chạy import_data và run_pipeline.", "Kiểm tra số record theo company/year/is_demo_data.", "Mở dashboard và đối chiếu một mẫu theo trang nguồn."] , numbered=True)
    add_h2(doc, "20.3. Sao lưu SQLite")
    add_code(doc, r"""
    Copy-Item .\database\esg_tracker.db .\database\backup_esg_tracker_YYYYMMDD.db
    """)
    add_callout(doc, "CẢNH BÁO", "Không sửa trực tiếp esg_tracker.db khi chưa sao lưu. Không nhập dữ liệu mẫu với is_demo_data=false.")
    add_summary(doc, ["Nguồn thực và demo phải tách bằng cờ.", "Sau import phải kiểm tra số lượng và một mẫu provenance."])

    add_chapter(doc, 21, "Cấu hình hệ thống", "Thay đổi YAML có thể thay đổi cả relationship, cảnh báo và điểm.")
    add_table(doc, "Ba file cấu hình", ["File", "Nội dung", "Tác động"], [
        ("config/metrics.yml", "Tên Việt–Anh, variants, đơn vị, GRI, hướng, tolerance, comparability", "Mapping, quy đổi và đối chiếu metric"),
        ("config/rules.yml", "15 luật, enabled, severity, fields, conditions, exclusions, template", "Rule result và explanation"),
        ("config/scoring.yml", "5 trọng số, 4 band, severity_weights", "Risk Score và phân loại"),
    ], widths=[3.5,7.2,5.5])
    add_h2(doc, "21.1. Quy trình thay đổi an toàn")
    add_bullets(doc, ["Sao chép file YAML sang thư mục backup có ngày.", "Chỉ sửa một nhóm thay đổi mỗi lần.", "Kiểm tra tổng scoring weights bằng 1,0.", "Giữ đúng cú pháp YAML và kiểu dữ liệu.", "Chạy pytest -q.", "Chạy lại pipeline và ghi phiên bản cấu hình/kết quả.", "So sánh trước–sau trên cùng corpus."], numbered=True)
    add_code(doc, """
    # Ví dụ tắt tạm một luật trong rules.yml
    enabled: false

    # Kiểm tra sau thay đổi
    pytest -q
    python scripts/run_pipeline.py
    """)
    add_callout(doc, "CẢNH BÁO", "Thay tolerance, severity hoặc trọng số có thể đổi score và thứ tự ưu tiên dù dữ liệu không đổi. Không so sánh hai lần chạy nếu không biết phiên bản cấu hình.")
    add_summary(doc, ["YAML là cấu hình nghiệp vụ có ảnh hưởng trực tiếp.", "Luôn sao lưu, test và version hóa."])

    add_chapter(doc, 22, "Lỗi thường gặp", "Chẩn đoán theo biểu hiện trước khi sửa dữ liệu hoặc cấu hình.")
    errors = [
        ("Không cài được thư viện", "pip báo build/download lỗi", "Mạng, pip cũ, Python không phù hợp", "python -m pip install --upgrade pip; kiểm tra mạng; dùng đúng venv"),
        ("Sai Python", "Syntax/import lỗi", "Python quá cũ", "python --version; cài 3.11"),
        ("Không thấy file", "FileNotFoundError", "Đứng sai thư mục/tên đổi", "Get-Location; Test-Path .\\config\\metrics.yml"),
        ("DB chưa tạo", "no such table", "Chưa initialize", "python scripts/initialize_database.py"),
        ("Cổng 8050 bận", "Address already in use", "Một app khác đang nghe", "Get-NetTCPConnection -LocalPort 8050; dừng đúng tiến trình của mình hoặc cấu hình cổng [CẦN XÁC NHẬN]"),
        ("Dashboard trống", "KPI/bảng không dữ liệu", "Chưa import/pipeline hoặc lọc quá chặt", "Chạy import_data.py, run_pipeline.py; reset filter"),
        ("Bộ lọc không có lựa chọn", "Dropdown rỗng", "Không có record trong chế độ nguồn", "Chọn Demo; kiểm tra is_demo_data/year"),
        ("Font tiếng Việt lỗi", "Ô vuông/ký tự sai", "Font/encoding", "Dùng UTF-8 và Arial/Segoe UI; kiểm tra JSON encoding"),
        ("PDF không trích xuất", "Trang rỗng", "PDF scan/không có text layer", "OCR riêng; đánh dấu extraction_method và confidence"),
        ("OCR sai số/unit", "1.000 thành 1000 hoặc I/1", "Layout/scan", "So raw text với trang PDF; sửa adapter có audit trail"),
        ("Không tìm thấy evidence", "MISSING", "Corpus thiếu hoặc variants thiếu", "Tìm thủ công; kiểm tra metrics.yml; không đổi thành CONTRADICTS"),
        ("Tất cả MISSING", "Coverage≈0", "Mapping/year/source lỗi", "Kiểm tra metric_code, report_year, is_demo_data và pipeline log"),
        ("Thiếu một năm", "Biểu đồ có gap", "Không record hoặc bị filter", "Reset; query metric theo year; phân biệt gap với 0"),
        ("Điểm đổi sau cấu hình", "Cùng claim khác score", "weights/severity/tolerance đổi", "Khôi phục YAML backup; chạy lại và ghi version"),
        ("PowerShell chặn activate", "running scripts is disabled", "ExecutionPolicy", "Dùng cmd activate.bat hoặc .venv\\Scripts\\python.exe trực tiếp"),
    ]
    add_table(doc, "Bảng xử lý lỗi", ["Lỗi", "Biểu hiện", "Nguyên nhân", "Cách xử lý"], errors, widths=[3.0,3.6,4.4,5.2], font_size=7.1)
    add_h2(doc, "22.1. Lệnh kiểm tra nhanh")
    add_code(doc, r"""
    python --version
    python -m pip --version
    Test-Path .\database\esg_tracker.db
    pytest -q
    python scripts\run_pipeline.py
    Get-NetTCPConnection -LocalPort 8050 -ErrorAction SilentlyContinue
    """)
    add_callout(doc, "LƯU Ý", "Nếu sửa dữ liệu, hãy giữ raw record, ghi người sửa/lý do và chạy lại test. Không xóa database như bước xử lý đầu tiên.")
    add_summary(doc, ["Reset filter và kiểm tra đúng venv trước.", "MISSING hàng loạt thường là lỗi mapping hoặc nguồn, không phải hiện tượng nghiệp vụ."])

    add_chapter(doc, 23, "Câu hỏi thường gặp")
    faqs = [
        ("ESG Tracker có kết luận doanh nghiệp tẩy xanh không?", "Không. Hệ thống chỉ tạo tín hiệu rủi ro/cảnh báo cần rà soát."),
        ("Vì sao điểm cao?", "Một hoặc nhiều nhóm luật có severity cao; mở chi tiết rule và evidence."),
        ("Vì sao không có evidence?", "Có thể corpus chưa chứa, mapping thiếu, năm khác hoặc OCR lỗi."),
        ("AMBIGUOUS khác MISSING?", "AMBIGUOUS có ứng viên nhưng thiếu dữ kiện; MISSING là chưa tìm thấy ứng viên phù hợp."),
        ("Hai số giống nhau sao không so sánh?", "Có thể khác metric, Scope, boundary, definition hoặc value kind."),
        ("Vì sao khác Scope không đối chiếu?", "Nguồn phát thải khác nhau nên phép so sánh có thể sai bản chất."),
        ("Vì sao giữ đơn vị gốc?", "Để truy vết, phát hiện lỗi quy đổi và tái tính."),
        ("Có thể thêm doanh nghiệp khác?", "Schema có bảng companies; adapter/chủ đề/rules cần hiệu chỉnh và kiểm thử."),
        ("Có thể đổi trọng số?", "Có, trong scoring.yml; phải version hóa và chạy lại."),
        ("GRI 11 dùng thế nào?", "Ánh xạ chủ đề/metric và hỗ trợ rule omission; không tự chứng nhận tuân thủ."),
        ("Có dùng báo cáo tiếng Anh?", "Variants Việt–Anh hỗ trợ một phần; cần mở rộng từ điển và test sentence rules."),
        ("Có dùng machine learning không?", "Bản hiện tại chủ yếu rule-based; không dùng mô hình trả phí."),
        ("Confidence nghĩa là gì?", "Độ tin cậy của trích xuất/matching, không phải xác suất doanh nghiệp nói thật."),
        ("Dữ liệu demo là kết quả thật?", "Không. Demo luôn is_demo_data=true và chỉ phục vụ trình diễn."),
        ("Truy ngược báo cáo gốc thế nào?", "Mở tab nguồn bằng chứng; lấy tài liệu, năm, loại báo cáo và trang."),
        ("MISSING có phải vi phạm GRI?", "Không. Cần kiểm tra phạm vi corpus, materiality và giải trình của tổ chức."),
        ("Score theo công ty tính thế nào?", "Giao diện hiện dùng trung bình claim trong tập lọc; weighting chính thức cần xác nhận."),
        ("Tại sao CAPEX không so OPEX?", "Hai loại chi có bản chất kế toán khác nhau; test bảo vệ điều kiện này."),
    ]
    add_table(doc, "Câu hỏi thường gặp", ["Câu hỏi", "Trả lời ngắn"], faqs, widths=[7.2,9.0], font_size=8.0)
    add_summary(doc, ["Khi nghi ngờ, quay lại claim, evidence và provenance.", "Không biến trạng thái kỹ thuật thành kết luận pháp lý."])


def appendices(doc: Document, metrics, rules):
    add_part(doc, "VI", "Phụ lục")
    doc.add_page_break(); doc.add_heading("Phụ lục A. Bảng thuật ngữ", level=1)
    glossary = [
        ("Absolute value", "Giá trị tuyệt đối", "Tổng lượng trong kỳ, chưa chia cho mẫu số."),
        ("Baseline", "Năm cơ sở", "Mốc dùng để đo thay đổi của mục tiêu hoặc xu hướng."),
        ("Boundary", "Ranh giới báo cáo", "Đơn vị/cơ sở/hoạt động được đưa vào phép tính."),
        ("Claim", "Tuyên bố ESG", "Mệnh đề mô tả chính sách, số liệu, mục tiêu hoặc thành tựu."),
        ("Confidence", "Độ tin cậy", "Mức chắc chắn của bước trích xuất/matching; không phải độ trung thực."),
        ("Drill-down", "Đi sâu chi tiết", "Từ KPI/biểu đồ mở danh sách và provenance."),
        ("EntityRuler", "Bộ gán thực thể theo luật", "Thành phần spaCy nhận diện entity theo pattern."),
        ("ESG", "Môi trường – Xã hội – Quản trị", "Ba nhóm vấn đề dùng để tổ chức phân tích bền vững."),
        ("Evidence", "Bằng chứng", "Đoạn văn, bảng hoặc metric hỗ trợ/đối chiếu claim."),
        ("Evidence coverage", "Độ phủ bằng chứng", "Tỷ lệ claim có evidence liên quan trong corpus."),
        ("False positive", "Cảnh báo dương tính giả", "Hệ thống báo tín hiệu nhưng kiểm tra thủ công thấy không phù hợp."),
        ("Fuzzy matching", "So khớp gần đúng", "Xếp hạng văn bản theo độ tương đồng thay vì trùng tuyệt đối."),
        ("Greenwashing", "Tẩy xanh", "Truyền thông tạo ấn tượng môi trường tích cực hơn thực tế; cần xác minh."),
        ("GRI", "Sáng kiến Báo cáo Toàn cầu", "Tổ chức/bộ chuẩn báo cáo tác động phát triển bền vững."),
        ("Heatmap", "Bản đồ nhiệt", "Ma trận dùng màu để biểu diễn giá trị theo hai chiều."),
        ("Information Extraction", "Trích xuất thông tin", "Chuyển văn bản không cấu trúc thành trường dữ liệu."),
        ("Intensity", "Cường độ", "Giá trị trên một mẫu số, như tCO2e/tấn sản phẩm."),
        ("Materiality", "Tính trọng yếu", "Mức đáng kể của tác động cần ưu tiên xác định/báo cáo."),
        ("Metric", "Chỉ số", "Đại lượng có định nghĩa, giá trị, đơn vị và điều kiện so sánh."),
        ("NLP", "Xử lý ngôn ngữ tự nhiên", "Kỹ thuật máy tính xử lý văn bản/ngôn ngữ."),
        ("PhraseMatcher", "Bộ so khớp cụm từ", "Thành phần spaCy tìm cụm từ từ danh sách pattern."),
        ("Plotly Dash", "Khung dashboard Python", "Công nghệ web dùng để tạo giao diện tương tác của prototype."),
        ("Provenance", "Nguồn gốc dữ liệu", "Thông tin tài liệu, năm, trang, nguyên văn và phương pháp."),
        ("Regex", "Biểu thức chính quy", "Ngôn ngữ mẫu để tìm số, đơn vị, năm hoặc chuỗi."),
        ("Risk Score", "Điểm rủi ro", "Điểm 0–100 ưu tiên rà soát, không phải xác suất vi phạm."),
        ("Rule Engine", "Bộ máy luật", "Thực thi điều kiện, ngoại lệ và explanation có cấu hình."),
        ("Scope", "Phạm vi", "Nhóm nguồn hoặc phạm vi đo; với GHG có Scope 1, 2, 3."),
        ("Severity", "Mức nghiêm trọng", "Mức 1–5 của rule result trong cấu hình."),
        ("SQLite", "Cơ sở dữ liệu tệp", "CSDL quan hệ gọn nhẹ lưu MVP."),
        ("Target", "Mục tiêu", "Kết quả dự kiến đạt tại một thời điểm, thường cần baseline/scope."),
        ("Topic", "Chủ đề", "Nhóm vấn đề ESG, có thể ánh xạ với GRI."),
    ]
    glossary.sort(key=lambda x: x[0].lower())
    add_table(doc, "Glossary ESG Tracker", ["Tên tiếng Anh", "Tên tiếng Việt", "Giải thích đơn giản"], glossary, widths=[4.3,4.2,7.7], font_size=7.8)

    doc.add_page_break(); doc.add_heading("Phụ lục B. Danh mục metric", level=1)
    metric_rows=[]
    for code,cfg in metrics.items():
        comparable = ", ".join(cfg.get("comparable_when",[]))
        scope_note = "Theo metric/record" if "same_scope" in comparable else "Không cố định; kiểm tra boundary/denominator"
        metric_rows.append((code, f"{cfg.get('name_vi','')} / {cfg.get('name_en','')}", cfg.get("standard_unit",""), cfg.get("gri_reference",""), scope_note, cfg.get("direction",""), f"{comparable}; tolerance={cfg.get('tolerance')}"))
    add_table(doc, "Danh mục 16 metric từ metrics.yml", ["Metric code", "Tên Việt–Anh", "Đơn vị", "GRI", "Scope", "Hướng", "Điều kiện so sánh"], metric_rows, widths=[2.6,4.0,2.3,2.7,2.9,2.5,4.0], font_size=5.8)
    add_callout(doc, "LƯU Ý", "Hướng LOWER/HIGHER_IS_BETTER là quy ước scoring, không thay đánh giá bối cảnh. TAX_PAID được cấu hình NEUTRAL.")

    doc.add_page_break(); doc.add_heading("Phụ lục C. Danh mục luật", level=1)
    rule_rows=[]
    for r in rules:
        rule_rows.append((r["rule_id"], r["name"], "Đang hoạt động" if r.get("enabled") else "Chưa triển khai/tắt", r.get("severity"), ", ".join(r.get("required_fields",[])), r.get("explanation_template","")))
    add_table(doc, "Tổng hợp trạng thái luật", ["ID", "Tên luật", "Trạng thái", "Severity", "Required fields", "Explanation template"], rule_rows, widths=[1.5,3.4,2.7,1.4,3.4,7.0], font_size=6.5)
    doc.add_paragraph("Các luật ngoài danh mục trên: chưa triển khai trong prototype. Toàn bộ 15 luật GW01–GW15 đang enabled=true tại thời điểm tài liệu được tạo.")

    doc.add_page_break(); doc.add_heading("Phụ lục D. Trạng thái dữ liệu", level=1)
    add_table(doc, "Từ điển trạng thái matching", ["Trạng thái", "Có evidence?", "So sánh được?", "Cách hiểu", "Hành động"], [
        ("SUPPORTS","Có","Có","Evidence phù hợp","Đọc nguồn và ghi nhận hỗ trợ"),
        ("PARTIAL_SUPPORT","Có","Một phần","Hỗ trợ nhưng thiếu thuộc tính","Bổ sung scope/unit/method"),
        ("CONTRADICTS","Có","Có","Nội dung trái nhau vượt tolerance","Ưu tiên rà soát hai nguồn"),
        ("MISSING","Chưa thấy","Chưa xác định","Không tìm được evidence trong corpus","Mở rộng tìm kiếm; không kết luận sai"),
        ("AMBIGUOUS","Có ứng viên","Chưa đủ dữ kiện","Mơ hồ về unit/định nghĩa","Kiểm tra PDF và phương pháp"),
        ("NOT_COMPARABLE","Có","Không","Khác metric/kỳ/scope/boundary/kind","Không đối chiếu định lượng"),
    ], widths=[3.0,2.4,2.8,4.4,5.5], font_size=7.8)

    doc.add_page_break(); doc.add_heading("Phụ lục E. Tài liệu tham khảo", level=1)
    refs = [
        "[1] Global Reporting Initiative. (2021). GRI 1: Foundation 2021. https://www.globalreporting.org/publications/documents/english/gri-1-foundation-2021/",
        "[2] Global Reporting Initiative. (2021). GRI 2: General Disclosures 2021. https://www.globalreporting.org/standards/",
        "[3] Global Reporting Initiative. (2021). GRI 3: Material Topics 2021. https://www.globalreporting.org/standards/",
        "[4] Global Reporting Initiative. (2021/2026). GRI 11: Oil and Gas Sector. https://www.globalreporting.org/standards/standards-development/sector-standard-for-oil-and-gas-gri-11/",
        "[5] Global Reporting Initiative. GRI Standards – English language. https://www.globalreporting.org/how-to-use-the-gri-standards/gri-standards-english-language/",
        "[6] spaCy. Sentencizer API. https://spacy.io/api/sentencizer",
        "[7] spaCy. PhraseMatcher API. https://spacy.io/api/phrasematcher",
        "[8] spaCy. EntityRuler API. https://spacy.io/api/entityruler",
        "[9] RapidFuzz. fuzz.token_set_ratio documentation. https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html",
        "[10] Plotly. Dash documentation. https://dash.plotly.com/",
        "[11] de Freitas Netto, S. V., et al. (2020). Concepts and forms of greenwashing: a systematic review. Environmental Sciences Europe, 32, 19. https://doi.org/10.1186/s12302-020-0300-3",
        "[12] Delmas, M. A., & Burbano, V. C. (2011). The Drivers of Greenwashing. California Management Review, 54(1), 64–87. https://doi.org/10.1525/cmr.2011.54.1.64",
        "[13] Lyon, T. P., & Montgomery, A. W. (2015). The Means and End of Greenwash. Organization & Environment, 28(2), 223–249. https://doi.org/10.1177/1086026615575332",
        "[14] Python Software Foundation. venv — Creation of virtual environments. https://docs.python.org/3/library/venv.html",
        "[15] pandas development team. pandas documentation. https://pandas.pydata.org/docs/",
        "[16] SQLite Consortium. SQLite Documentation. https://www.sqlite.org/docs.html",
        "[17] PyMuPDF. Documentation. https://pymupdf.readthedocs.io/",
    ]
    doc.add_paragraph("Định dạng tham khảo: APA rút gọn. Ngày truy cập cho các nguồn web: 12/09/2026.")
    for ref in refs:
        p=doc.add_paragraph(ref)
        p.paragraph_format.first_line_indent = Cm(-0.6); p.paragraph_format.left_indent = Cm(0.6)

    doc.add_page_break(); doc.add_heading("Phụ lục F. Bảng kiểm bàn giao và xác nhận", level=1)
    add_table(doc, "Nội dung đã xác minh và cần xác nhận", ["Hạng mục", "Trạng thái", "Bằng chứng/ghi chú"], [
        ("5 tên tab", "Đã xác minh", "Đối chiếu source app.py và dashboard localhost"),
        ("Công thức scoring", "Đã xác minh", "config/scoring.yml và src/scoring/risk.py"),
        ("15 luật", "Đã xác minh", "config/rules.yml và src/rules/engine.py"),
        ("16 metric", "Đã xác minh", "config/metrics.yml"),
        ("Lệnh cài đặt", "Đã xác minh", "README.md và chạy test/app"),
        ("Nguồn BSR 2023–2025", "Đã xác minh", "JSON Phase 1; không có record nguồn 2022"),
        ("Ảnh từng tab bản phát hành", "Cần bổ sung", "[CHÈN ẢNH: 5 tab sau khi đóng băng giao diện]"),
        ("Chủ sở hữu/liên hệ", "Cần xác nhận", "[CẦN NGƯỜI PHÁT TRIỂN XÁC NHẬN]"),
        ("Phiên bản GRI áp dụng chính thức", "Cần xác nhận", "2021 hay GRI 11 V1.1 2026 cho báo cáo tương lai"),
        ("Công thức tổng hợp company có materiality weighting", "Cần xác nhận", "Source hiện dùng trung bình claim trong tập lọc"),
        ("Cấu hình cổng khác 8050", "Cần xác nhận", "app.py hiện chạy URL mặc định theo README"),
    ], widths=[5.2,3.0,8.0], font_size=7.8)
    add_callout(doc, "CẢNH BÁO", "Trước khi dùng làm phụ lục chính thức, nhóm phát triển cần điền thông tin quản trị, chụp lại đủ 5 tab và chốt phiên bản GRI/configuration baseline.")


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    ASSET.mkdir(parents=True, exist_ok=True)
    metrics, rules, scoring = load_configs()
    assets = {
        "overview": ASSET / "pipeline_overview.png",
        "technical": ASSET / "pipeline_technical.png",
        "gri": ASSET / "gri_system.png",
        "reading": ASSET / "safe_reading.png",
        "ui": ASSET / "ui_annotated.png",
    }
    diagram_pipeline(assets["overview"], technical=False)
    diagram_pipeline(assets["technical"], technical=True)
    diagram_gri(assets["gri"])
    diagram_reading(assets["reading"])
    diagram_ui(assets["ui"])

    doc = Document()
    configure_document(doc)
    front_matter(doc)
    part_i_ii(doc, assets)
    part_iii(doc, assets, rules, scoring)
    part_iv(doc, assets)
    part_v(doc)
    appendices(doc, metrics, rules)

    props = doc.core_properties
    props.title = "Hướng dẫn sử dụng ESG Tracker BSR 2023–2025"
    props.subject = "Prototype sàng lọc tín hiệu rủi ro greenwashing"
    props.author = "Tài liệu bàn giao ESG Tracker"
    props.keywords = "ESG, GRI 11, BSR, greenwashing, NLP, Dash"
    doc.save(DOCX_OUT)
    print(DOCX_OUT)
    print(f"chapters=23 figures={len(FIGURE_CAPTIONS)} tables={len(TABLE_CAPTIONS)} metrics={len(metrics)} rules={len(rules)}")


if __name__ == "__main__":
    build()
