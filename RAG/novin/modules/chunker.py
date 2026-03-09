from bs4 import BeautifulSoup
from typing import List, Dict, Optional


MAX_CHUNK_CHARS = 3000  


def chunk_html_by_sections(full_html: str) -> List[Dict]:
    """
    Returns list of chunk dicts, each with:
      index        : int
      html         : str  — the HTML snippet to translate
      text         : str  — plain-text version (used for QC / stats)
      section_title: str
      chunk_type   : 'warning' | 'section' | 'body' | 'table' | 'image'
      page_num     : str  — single page this chunk belongs to
      char_count   : int
    """
    soup = BeautifulSoup(full_html, "lxml")
    body = soup.find("body") or soup

    chunks: List[Dict] = []


    current_elements: List       = []
    current_section: str         = "Introduction"
    current_type: str            = "body"
    current_chars: int           = 0
    current_page: Optional[str]  = None
    has_image_content: bool      = False  

    def flush():
        nonlocal current_elements, current_chars, current_page
        nonlocal current_type, has_image_content
        if not current_elements:
            return
        html  = "".join(str(el) for el in current_elements)
        text  = BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)

        if not text and not has_image_content:
            current_elements = []
            current_chars    = 0
            has_image_content = False
            return
        chunks.append({
            "index"        : len(chunks),
            "html"         : html,
            "text"         : text,
            "section_title": current_section,
            "chunk_type"   : current_type,
            "page_num"     : current_page or "1",
            "char_count"   : len(text),
        })
        current_elements  = []
        current_chars     = 0
        has_image_content = False


    page_divs = body.find_all("div", class_="page", recursive=False)
    if not page_divs:
        page_divs = [body]

    for page_div in page_divs:
        page_num = page_div.get("data-page", current_page or "1")


        if current_page is not None and page_num != current_page:
            flush()

        current_page = page_num

        for element in page_div.children:

            if not hasattr(element, "name") or element.name is None:
                continue
            if element.name in ["html", "head", "style", "script"]:
                continue

            classes = element.get("class", [])


            if "image-block" in classes:
                if current_chars > MAX_CHUNK_CHARS * 0.5 and current_elements:
                    flush()
                    current_type = "body"
                current_elements.append(element)
                has_image_content = True
                continue

            el_text  = element.get_text(separator=" ", strip=True)
            if not el_text:
                continue
            el_chars = len(el_text)


            if element.name in ["h1", "h2", "h3", "h4"]:
                flush()
                current_section  = el_text
                current_type     = "section"
                current_elements = [element]
                current_chars    = el_chars
                continue

            if "warning-block" in classes:
                flush()
                chunks.append({
                    "index"        : len(chunks),
                    "html"         : str(element),
                    "text"         : el_text,
                    "section_title": "WARNING",
                    "chunk_type"   : "warning",
                    "page_num"     : page_num,
                    "char_count"   : el_chars,
                })
                continue


            if element.name == "table":
                flush()
                chunks.append({
                    "index"        : len(chunks),
                    "html"         : str(element),
                    "text"         : el_text,
                    "section_title": current_section,
                    "chunk_type"   : "table",
                    "page_num"     : page_num,
                    "char_count"   : el_chars,
                })
                continue


            if current_chars + el_chars > MAX_CHUNK_CHARS and current_elements:
                flush()
                current_type = "body"

            current_elements.append(element)
            current_chars += el_chars

    flush()  


    merged: List[Dict] = []
    for chunk in chunks:
        if (merged
                and chunk["chunk_type"] == "body"
                and chunk["char_count"] < 100
                and chunk["page_num"] == merged[-1]["page_num"]   # same page only
                and merged[-1]["chunk_type"] != "table"):
            merged[-1]["html"]       += chunk["html"]
            merged[-1]["text"]       += " " + chunk["text"]
            merged[-1]["char_count"] += chunk["char_count"]
        else:
            merged.append(chunk)

    for i, c in enumerate(merged):
        c["index"] = i

    return merged


def get_chunk_summary(chunks: List[Dict]) -> Dict:
    types: Dict[str, int] = {}
    for c in chunks:
        types[c["chunk_type"]] = types.get(c["chunk_type"], 0) + 1
    return {
        "total_chunks": len(chunks),
        "by_type"     : types,
        "avg_chars"   : sum(c["char_count"] for c in chunks) // max(len(chunks), 1),
        "max_chars"   : max((c["char_count"] for c in chunks), default=0),
    }