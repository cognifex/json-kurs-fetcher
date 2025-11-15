from bs4 import BeautifulSoup, NavigableString, Tag
import re

def clean_html_v2(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")

    # ---------------------------------------------------------
    # 1) Entferne technisch unnötige Elemente
    # ---------------------------------------------------------
    for tag in soup(["script", "style", "picture", "figure", "img", "svg", "header", "footer"]):
        tag.decompose()

    # CMX-footer Tabellen loswerden
    for table in soup.find_all("table"):
        table.decompose()

    # ---------------------------------------------------------
    # 2) Entferne gesamte CMX-Basisdaten-Blöcke
    #    (oft Bootstrap-Grids: col-sm-3, col-xs-6 etc.)
    # ---------------------------------------------------------
    def is_cmx_basis_block(tag):
        classes = tag.get("class", [])
        if not classes:
            return False
        return any(c.startswith("col-") for c in classes)

    for div in soup.find_all(is_cmx_basis_block):
        div.decompose()

    # ---------------------------------------------------------
    # 3) Entferne typische Verwaltungsinhalte
    # ---------------------------------------------------------
    admin_keywords = [
        "iban", "bic", "bankverbindung", "zahlungsbedingungen",
        "teilnahmebedingungen", "gebührenordnung",
        "rücktritt", "haftung", "datenschutz", "zahlung",
        "preis:", "kosten:", "ort:", "zeit:", "leitung:",
        "anzahl termine", "termine:"
    ]

    for el in soup.find_all(["p", "div", "span"]):
        t = el.get_text(" ", strip=True).lower()
        if any(kw in t for kw in admin_keywords):
            el.decompose()

    # ---------------------------------------------------------
    # 4) Entferne zusätzlichen Footer-Müll nach letztem <h3>
    # ---------------------------------------------------------
    footer_keywords = ["bankverbindung", "iban", "bic", "datenschutz", "haftung"]

    text_lower = soup.get_text(" ").lower()
    if any(kw in text_lower for kw in footer_keywords):
        last_h3 = soup.find_all("h3")
        if last_h3:
            for sib in last_h3[-1].find_all_next():
                sib.decompose()

    # ---------------------------------------------------------
    # 5) span-Wrapper entfernen
    # ---------------------------------------------------------
    for span in soup.find_all("span"):
        span.unwrap()

    # ---------------------------------------------------------
    # 6) Überflüssige DIVs in <p> verwandeln
    # ---------------------------------------------------------
    for div in soup.find_all("div"):
        if len(div.find_all(["p", "ul", "ol", "h1", "h2", "h3"])) == 0:
            div.name = "p"

    # ---------------------------------------------------------
    # 7) Leere Tags löschen
    # ---------------------------------------------------------
    for tag in soup.find_all():
        if tag.name not in ["br"] and not tag.get_text(strip=True):
            tag.decompose()

    # ---------------------------------------------------------
    # 8) <br><br>-Cluster → neuer Absatz
    # ---------------------------------------------------------
    for br in soup.find_all("br"):
        nxt = br.next_sibling
        if isinstance(nxt, Tag) and nxt.name == "br":
            p = soup.new_tag("p")
            br.replace_with(p)
            nxt.decompose()

    # ---------------------------------------------------------
    # 9) Duplicate Titelzeilen entfernen
    # ---------------------------------------------------------
    h_tags = soup.find_all(["h1", "h2", "h3"])
    if len(h_tags) >= 2:
        if h_tags[0].get_text(strip=True) == h_tags[1].get_text(strip=True):
            h_tags[1].decompose()

    # ---------------------------------------------------------
    # 10) Whitespace normalisieren
    # ---------------------------------------------------------
    def normalize_text(node):
        if isinstance(node, NavigableString):
            return NavigableString(re.sub(r"\s+", " ", str(node)))
        return node

    for element in soup.find_all(text=True):
        element.replace_with(normalize_text(element))

    # ---------------------------------------------------------
    # 11) Finale Ausgabe
    # ---------------------------------------------------------
    clean_html = soup.prettify()
    clean_html = re.sub(r'\n\s*\n', '\n\n', clean_html)

    return clean_html.strip()
