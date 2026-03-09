import fitz        
import base64
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any



def classify_block(text: str) -> str:
    t = text.strip()
    if re.match(r"(?i)^(WARNING|CAUTION|DANGER)\s*[:\-]?", t):
        return "warning"
    if re.match(r"(?i)^(IMPORTANT|NOTE)\s*[:\-]?", t):
        return "note"
    if re.match(r"(?i)^(Section|SECTION)\s+\d+", t):
        return "heading"
    if re.match(r"(?i)^(\d+\.\s+[A-Z][A-Z\s]{2,})$", t):
        return "heading"
    if re.match(r"^\d+[\.\)]\s+", t):
        return "instruction"
    return "body"



def _overlaps(b1: Tuple, b2: Tuple) -> bool:
    """Return True if two bboxes (x0,y0,x1,y1) overlap at all."""
    ax0, ay0, ax1, ay1 = b1
    bx0, by0, bx1, by1 = b2
    return ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0


def _inside(inner: Tuple, outer: Tuple, tolerance: float = 2.0) -> bool:
    """Return True if inner bbox is mostly inside outer bbox."""
    ax0, ay0, ax1, ay1 = inner
    bx0, by0, bx1, by1 = outer
    return (ax0 >= bx0 - tolerance and ay0 >= by0 - tolerance and
            ax1 <= bx1 + tolerance and ay1 <= by1 + tolerance)



def _extract_image_b64(doc: fitz.Document, xref: int, max_dim: int = 800) -> str:

    try:
        from PIL import Image
        import io

        img_data = doc.extract_image(xref)
        if not img_data:
            return ""

        raw = img_data["image"]
        ext = img_data.get("ext", "png").lower()

        pil_img = Image.open(io.BytesIO(raw))

        if pil_img.mode not in ("RGB", "RGBA", "L"):
            pil_img = pil_img.convert("RGB")

        w, h = pil_img.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    except Exception:
        return ""



def extract_page_html(page: fitz.Page, doc: fitz.Document, page_num: int) -> str:
    items: List[Tuple[float, str]] = []  

    table_bboxes: List[Tuple] = []
    tabs = page.find_tables()
    if tabs and tabs.tables:
        for table in tabs.tables:
            table_bboxes.append(tuple(table.bbox))
            df_data = table.extract()
            if not df_data:
                continue
            rows_html = []
            for row in df_data:
                cells = "".join(
                    f"<td>{str(cell).strip() if cell is not None else ''}</td>"
                    for cell in row
                )
                rows_html.append(f"<tr>{cells}</tr>")
            table_html = (
                '<table class="ifu-table" data-type="table"><tbody>'
                + "".join(rows_html)
                + "</tbody></table>"
            )
            items.append((table.bbox[1], table_html))   

    img_block_map: Dict[int, Tuple] = {}  
    raw_blocks = page.get_text("dict", flags=0)["blocks"]
    for block in raw_blocks:
        if block["type"] == 1:  
            xref = block.get("xref", 0)
            if xref:
                img_block_map[xref] = tuple(block["bbox"])

    for img_info in page.get_images(full=True):
        xref = img_info[0]
        w, h = img_info[2], img_info[3]
        if w < 10 or h < 10:      
            continue

        if xref in img_block_map:
            bbox = img_block_map[xref]
        else:
            try:
                rects = page.get_image_rects(xref)
                if rects:
                    bbox = tuple(rects[0])
                else:
                    continue
            except Exception:
                continue

        if any(_inside(bbox, tb) for tb in table_bboxes):
            continue

        b64 = _extract_image_b64(doc, xref)
        if not b64:
            continue

        img_html = (
            f'<div class="image-block" data-type="image" '
            f'data-page="{page_num}">'
            f'<img src="data:image/png;base64,{b64}" '
            f'alt="Figure on page {page_num}" '
            f'style="max-width:100%;height:auto;display:block;margin:8px 0;"/>'
            f'</div>'
        )
        items.append((bbox[1], img_html))


    for block in raw_blocks:
        if block["type"] != 0:
            continue

        bbox = tuple(block["bbox"])

        if any(_overlaps(bbox, tb) for tb in table_bboxes):
            continue

        block_text = " ".join(
            span["text"]
            for line in block["lines"]
            for span in line["spans"]
        ).strip()
        if not block_text:
            continue

        max_size = max(
            (span["size"] for line in block["lines"] for span in line["spans"]),
            default=0,
        )

        btype = classify_block(block_text)

        if btype == "warning":
            html = (
                f'<div class="warning-block" data-type="warning">'
                f'<strong>{block_text}</strong></div>'
            )
        elif btype == "note":
            html = f'<div class="note-block" data-type="note">{block_text}</div>'
        elif btype == "heading" or max_size > 14:
            tag = "h2" if max_size > 16 else "h3"
            html = f'<{tag} class="section-heading" data-type="heading">{block_text}</{tag}>'
        elif btype == "instruction":
            html = f'<p class="instruction" data-type="instruction">{block_text}</p>'
        else:
            html = f'<p class="body-text" data-type="body">{block_text}</p>'

        items.append((bbox[1], html))

    items.sort(key=lambda x: x[0])

    page_parts = [f'<div class="page" data-page="{page_num}">']
    page_parts.extend(html for _, html in items)
    page_parts.append("</div>")

    return "\n".join(page_parts)




def ingest_pdf(pdf_path: str, original_filename: str = "") -> dict:

    path = Path(pdf_path)
    doc = fitz.open(str(path))


    pdf_title = (
        doc.metadata.get("title", "").strip()
        or original_filename
        or "IFU Document"
    )

    metadata = {
        "title"     : pdf_title,
        "author"    : doc.metadata.get("author", ""),
        "page_count": len(doc),
        "filename"  : path.name,
    }

    pages_html = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        pages_html.append(extract_page_html(page, doc, page_num + 1))

    doc.close()

    full_html = (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        f'<head><meta charset="UTF-8"><title>{metadata["title"]}</title></head>\n'
        '<body>\n'
        + "\n".join(pages_html)
        + "\n</body>\n</html>"
    )

    return {
        "full_html": full_html,
        "pages": pages_html,
        "page_count": metadata["page_count"],
        "metadata": metadata,
    }