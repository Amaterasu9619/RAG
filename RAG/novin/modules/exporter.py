import io
import base64
import re
from typing import Optional
from bs4 import BeautifulSoup



_WEASYPRINT_CSS = """
@page { size: A4; margin: 20mm; }
body  { font-family: Arial, sans-serif; font-size: 10pt; line-height: 1.5; color: #000; }
h1    { font-size: 16pt; margin: 0 0 6pt; }
h2    { font-size: 13pt; margin: 8pt 0 4pt; }
h3    { font-size: 11pt; margin: 6pt 0 3pt; }
p     { margin: 3pt 0; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; }
td, th{ border: 0.5pt solid #888; padding: 4pt; font-size: 9pt; }
img   { max-width: 100%; height: auto; display: block; margin: 6pt 0; }
.page { page-break-after: always; }
.page:last-child { page-break-after: avoid; }
"""


def html_to_pdf_weasyprint(html_content: str) -> Optional[bytes]:
    try:
        from weasyprint import HTML, CSS
        
        styled = html_content.replace(
            "</head>",
            f"<style>{_WEASYPRINT_CSS}</style></head>",
            1,
        )
        
        pdf_bytes = HTML(string=styled, base_url=".").write_pdf()
        return pdf_bytes
    except Exception as e:
        print(f"WeasyPrint failed: {e}")
        return None




def _decode_b64_image(src: str):
    """
    Extract raw bytes from a data:image/...;base64,... src attribute.
    Returns (bytes, ext) or (None, None).
    """
    m = re.match(r"data:image/(\w+);base64,(.+)", src, re.DOTALL)
    if not m:
        return None, None
    ext  = m.group(1).lower()
    data = base64.b64decode(m.group(2))
    return data, ext


def _rl_image(src: str, max_width_pts: float = 450):
    """Return a ReportLab Image flowable or None."""
    try:
        from reportlab.platypus import Image as RLImage
        from PIL import Image as PILImage

        raw, ext = _decode_b64_image(src)
        if not raw:
            return None

        pil = PILImage.open(io.BytesIO(raw))
        w_px, h_px = pil.size
        if w_px == 0 or h_px == 0:
            return None

       
        aspect = h_px / w_px
        w_pts  = min(max_width_pts, w_px * 0.75)   # rough px→pt
        h_pts  = w_pts * aspect

        buf = io.BytesIO(raw)
        img = RLImage(buf, width=w_pts, height=h_pts)
        return img
    except Exception:
        return None


def _process_page_div(page_div, story, styles, is_last_page: bool):
    """
    Walk a single .page div and append flowables to story.
    Adds a PageBreak after each page except the last.
    """
    from reportlab.platypus import (
        Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image as RLImage,
    )
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    heading_style = styles["Heading2"]
    body_style    = styles["Normal"]
    warn_style    = styles["Normal"]  

    def _safe_para(text: str, style, max_len: int = 2000) -> Paragraph:
        
        text = (text[:max_len]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
        return Paragraph(text, style)

    
    for element in page_div.children:
        if not hasattr(element, "name") or element.name is None:
            continue

        tag     = element.name
        classes = element.get("class", [])

        
        if tag in ("h1", "h2", "h3", "h4"):
            text = element.get_text(strip=True)
            if text:
                lvl   = {"h1": "Title", "h2": "Heading2",
                         "h3": "Heading3", "h4": "Heading4"}
                story.append(_safe_para(text, styles.get(lvl.get(tag, "Heading2"), heading_style)))
                story.append(Spacer(1, 2*mm))
            continue

        
        if "warning-block" in classes or "note-block" in classes:
            text = element.get_text(strip=True)
            if text:
                story.append(_safe_para(f"[WARNING] {text}", warn_style))
                story.append(Spacer(1, 2*mm))
            continue

       
        if "image-block" in classes:
            img_tag = element.find("img")
            if img_tag:
                src = img_tag.get("src", "")
                rl_img = _rl_image(src)
                if rl_img:
                    story.append(rl_img)
                    story.append(Spacer(1, 3*mm))
            continue

        
        if tag == "table":
            rows = []
            for tr in element.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if cells:
                    row = [_safe_para(c.get_text(strip=True), body_style, 300)
                           for c in cells]
                    rows.append(row)
            if rows:
                col_count = max(len(r) for r in rows)

                for r in rows:
                    while len(r) < col_count:
                        r.append(_safe_para("", body_style))
                tbl = Table(rows, repeatRows=1, hAlign="LEFT")
                tbl.setStyle(TableStyle([
                    ("GRID",       (0, 0), (-1, -1), 0.4, colors.black),
                    ("FONTSIZE",   (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
                    ("VALIGN",     (0, 0), (-1, -1), "TOP"),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 3*mm))
            continue

        
        if tag == "div":
            _process_page_div(element, story, styles, is_last_page=True)
            continue

        
        if tag in ("p", "li", "span"):
            text = element.get_text(strip=True)
            if text:
                story.append(_safe_para(text, body_style))
            continue

    
    if not is_last_page:
        story.append(PageBreak())


def html_to_pdf_reportlab(html_content: str, title: str = "IFU Document") -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm,  bottomMargin=20*mm,
    )
    styles = getSampleStyleSheet()
    story  = []

    soup      = BeautifulSoup(html_content, "lxml")
    body      = soup.find("body") or soup
    page_divs = body.find_all("div", class_="page", recursive=False)

    if not page_divs:
        
        page_divs = [body]

    total = len(page_divs)
    for idx, page_div in enumerate(page_divs):
        is_last = (idx == total - 1)
        _process_page_div(page_div, story, styles, is_last_page=is_last)

    doc.build(story)
    return buf.getvalue()




def export_to_pdf(html_content: str, title: str = "IFU Document") -> bytes:
    """Try WeasyPrint first; fall back to ReportLab."""
    pdf = html_to_pdf_weasyprint(html_content)
    if pdf:
        return pdf
    return html_to_pdf_reportlab(html_content, title)