#!/usr/bin/env python3
"""
VHS-Lahnstein Scraper 3.1
Ein kompakter, spezialisierter Scraper für vhs-lahnstein.de.
Er erzeugt eine saubere JSON-Datei mit allen Kursen (inkl. Beschreibung, Bild, Zeit, Ort usw.)
"""
import re
import time
import json
import argparse
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://vhs-lahnstein.de"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VHS-Scraper/3.1)"}


def fetch(url: str) -> str:
    """HTML abrufen, mit kleinem Delay."""
    time.sleep(1)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def get_course_links(overview_url: str) -> list[str]:
    """Alle Kurslinks von der Übersichtsseite sammeln."""
    html = fetch(overview_url)
    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(r"^/Veranstaltung/cmx[0-9a-f]+\.html$")
    links = [urljoin(BASE_URL, a["href"]) for a in soup.find_all("a", href=pattern)]
    return sorted(set(links))


def clean_html(html: str) -> str:
    """HTML aufräumen, aber Formatierung (Absätze, Listen) erhalten."""
    soup = BeautifulSoup(html, "html.parser")

    # Entferne Bilder, figure/picture, leere Elemente
    for t in soup(["img", "picture", "figure", "source", "script", "style"]):
        t.decompose()

    # Nur gewünschte Tags behalten
    allowed = {"p", "ul", "ol", "li", "br", "a", "b", "strong", "em"}
    for tag in soup.find_all(True):
        if tag.name not in allowed:
            tag.unwrap()
        else:
            tag.attrs = {k: v for k, v in tag.attrs.items() if k == "href"}

    # Entferne Textzeilen, die mit Zeit/Ort/Preis anfangen
    text = str(soup)
    text = re.sub(r"(?i)(Zeiten?|Ort|Preis|Bankverbindung|IBAN).*", "", text)
    return text.strip()


def parse_course(url: str) -> dict:
    """Einzelnen Kurs extrahieren."""
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    guid_match = re.search(r"(cmx[0-9a-f]+)\.html", url)
    guid = guid_match.group(1) if guid_match else ""

    titel = soup.find("h1")
    titel = titel.get_text(strip=True) if titel else ""

    # Beschreibung
    besch_node = soup.select_one(
        "div.VeranstaltungTeaserInhalt, div.VeranstaltungTeaserText, div.cmxModuleText"
    )
    beschreibung = clean_html(besch_node.decode_contents()) if besch_node else ""

    # Details (Regex im Volltext)
    text = soup.get_text(" ", strip=True)

    def find(pattern):
        m = re.search(pattern, text, re.I)
        return m.group(1).strip() if m else ""

    nummer = find(r"Nummer\s*[:\-]?\s*([A-Z0-9\-]+)")
    ort = find(r"Ort\s*[:\-]?\s*(.*?)\s+(?:Leitung|Preis|$)")
    preis = find(r"Preis\s*[:\-]?\s*([0-9\.,]+(?:\s*€)?)")
    dozent = find(r"Leitung\s*:?\s*([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-\s]+?)(?:,|Nummer|Ort|Preis|$)")

    # Zeiten
    term_div = soup.select_one(
        "div.VeranstaltungTeaserTermine, div.VeranstaltungTermine, div.termine"
    )
    zeiten = (
        re.sub(r"\s+", " ", term_div.get_text(" ", strip=True)) if term_div else ""
    )

    # Bild
    img = soup.find("img", src=re.compile(r"/cmx/ordner/.cache/images/", re.I))
    bild = urljoin(BASE_URL, img["src"]) if img and img.get("src") else ""

    # Anmeldelink
    link = f"{BASE_URL}/Anmeldung/neueAnmeldung-true/f_veranstaltung-{guid}"

    print(f"✔ {titel}")
    return {
        "guid": guid,
        "titel": titel,
        "beschreibung": beschreibung,
        "bild": bild,
        "nummer": nummer,
        "ort": ort,
        "preis": preis,
        "dozent": dozent,
        "zeiten": zeiten,
        "link": link,
    }


def main():
    parser = argparse.ArgumentParser(description="VHS Lahnstein Kurs-Scraper 3.1")
    parser.add_argument(
        "--url",
        default="https://vhs-lahnstein.de/Suche?cmxelementid=web4e15b88472a73&seite=Suche&Suche=1&Suchbegriffe=Tim+Heimes",
        help="Übersichtsseite mit Kursen",
    )
    parser.add_argument("--output", default="kurse.json", help="JSON-Datei speichern unter …")
    args = parser.parse_args()

    links = get_course_links(args.url)
    print(f"Gefundene Kurse: {len(links)}")

    all_courses = []
    for link in links:
        try:
            all_courses.append(parse_course(link))
        except Exception as e:
            print(f"⚠ Fehler bei {link}: {e}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_courses, f, ensure_ascii=False, indent=2)

    print(f"{len(all_courses)} Kurse gespeichert in {args.output}")


if __name__ == "__main__":
    main()
