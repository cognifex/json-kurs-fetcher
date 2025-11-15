from bs4 import BeautifulSoup, NavigableString, Tag
import re

def clean_html_v2(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")

    # 1) Entferne nicht benötigte Elemente komplett
    for tag in soup(["script", "style", "picture", "figure", "img", "svg", "header", "footer"]):
        tag.decompose()

    # Tabellen kommen oft vom CMX-Footer (Bankverbindung etc.)
    for table in soup.find_all("table"):
        table.decompose()

    # 2) Entferne typische CMX-Footer-Blöcke (Bankverbindung etc.)
    footer_keywords = [
        "bankverbindung", "iban", "bic", "zahlungsbedingungen",
        "datenverarbeitung", "datenschutz", "haftungsausschluss"
    ]
    text_lower = soup.get_text(" ").lower()
    for keyword in footer_keywords:
        if keyword in text_lower:
            # rohes heuristisches Entfernen: der gesamte Abschnitt unterhalb der letzten <h3> wird gekillt
            last_h3 = soup.find_all("h3")
            if last_h3:
                # Lösche alles nach dem letzten H3
                for sib in last_h3[-1].find_all_next():
                    sib.decompose()

    # 3) span-Wrapper entfernen (nur Text übernehmen)
    for span in soup.find_all("span"):
        span.unwrap()

    # 4) Überflüssige <div> in Absätze umwandeln
    for div in soup.find_all("div"):
        # wenn der div nur Text oder inline enthält → <p>
        if len(div.find_all(["p", "ul", "ol", "h1", "h2", "h3"])) == 0:
            div.name = "p"

    # 5) Leere Tags löschen
    for tag in soup.find_all():
        if tag.name not in ["br", "img"] and not tag.get_text(strip=True):
            tag.decompose()

    # 6) <br> Blöcke konsolidieren → neue Absätze
    for br in soup.find_all("br"):
        # wenn mehrere <br><br> → ersetze durch Absatz
        next_node = br.next_sibling
        if isinstance(next_node, Tag) and next_node.name == "br":
            # ersetze beide durch ein <p>
            p = soup.new_tag("p")
            br.replace_with(p)
            next_node.decompose()

    # 7) Doppelte erste Titelzeile entfernen
    h_tags = soup.find_all(["h1", "h2", "h3"])
    if len(h_tags) >= 2:
        first_text = h_tags[0].get_text(strip=True)
        second_text = h_tags[1].get_text(strip=True)
        if first_text == second_text:
            h_tags[1].decompose()

    # 8) Whitespace in Textknoten normalisieren
    def normalize_text(node):
        if isinstance(node, NavigableString):
            fixed = re.sub(r"\s+", " ", str(node))
            return NavigableString(fixed)
        return node

    for element in soup.find_all(text=True):
        element.replace_with(normalize_text(element))

    # 9) Schöne HTML-Ausgabe erzeugen
    clean_html = soup.prettify()

    # 10) Fallback: Überflüssige Leerzeilen reduzieren
    clean_html = re.sub(r'\n\s*\n', '\n\n', clean_html)

    return clean_html.strip()
from bs4 import BeautifulSoup, NavigableString, Tag
import re

def clean_html_v2(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")

    # 1) Entferne nicht benötigte Elemente komplett
    for tag in soup(["script", "style", "picture", "figure", "img", "svg", "header", "footer"]):
        tag.decompose()

    # Tabellen kommen oft vom CMX-Footer (Bankverbindung etc.)
    for table in soup.find_all("table"):
        table.decompose()

    # 2) Entferne typische CMX-Footer-Blöcke (Bankverbindung etc.)
    footer_keywords = [
        "bankverbindung", "iban", "bic", "zahlungsbedingungen",
        "datenverarbeitung", "datenschutz", "haftungsausschluss"
    ]
    text_lower = soup.get_text(" ").lower()
    for keyword in footer_keywords:
        if keyword in text_lower:
            # rohes heuristisches Entfernen: der gesamte Abschnitt unterhalb der letzten <h3> wird gekillt
            last_h3 = soup.find_all("h3")
            if last_h3:
                # Lösche alles nach dem letzten H3
                for sib in last_h3[-1].find_all_next():
                    sib.decompose()

    # 3) span-Wrapper entfernen (nur Text übernehmen)
    for span in soup.find_all("span"):
        span.unwrap()

    # 4) Überflüssige <div> in Absätze umwandeln
    for div in soup.find_all("div"):
        # wenn der div nur Text oder inline enthält → <p>
        if len(div.find_all(["p", "ul", "ol", "h1", "h2", "h3"])) == 0:
            div.name = "p"

    # 5) Leere Tags löschen
    for tag in soup.find_all():
        if tag.name not in ["br", "img"] and not tag.get_text(strip=True):
            tag.decompose()

    # 6) <br> Blöcke konsolidieren → neue Absätze
    for br in soup.find_all("br"):
        # wenn mehrere <br><br> → ersetze durch Absatz
        next_node = br.next_sibling
        if isinstance(next_node, Tag) and next_node.name == "br":
            # ersetze beide durch ein <p>
            p = soup.new_tag("p")
            br.replace_with(p)
            next_node.decompose()

    # 7) Doppelte erste Titelzeile entfernen
    h_tags = soup.find_all(["h1", "h2", "h3"])
    if len(h_tags) >= 2:
        first_text = h_tags[0].get_text(strip=True)
        second_text = h_tags[1].get_text(strip=True)
        if first_text == second_text:
            h_tags[1].decompose()

    # 8) Whitespace in Textknoten normalisieren
    def normalize_text(node):
        if isinstance(node, NavigableString):
            fixed = re.sub(r"\s+", " ", str(node))
            return NavigableString(fixed)
        return node

    for element in soup.find_all(text=True):
        element.replace_with(normalize_text(element))

    # 9) Schöne HTML-Ausgabe erzeugen
    clean_html = soup.prettify()

    # 10) Fallback: Überflüssige Leerzeilen reduzieren
    clean_html = re.sub(r'\n\s*\n', '\n\n', clean_html)

    return clean_html.strip()
