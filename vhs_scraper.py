#!/usr/bin/env python3
"""
VHS-Lahnstein Scraper 3.2 – GitHub-Workflow-optimiert
----------------------------------------------------
Scraped alle Kurse von https://vhs-lahnstein.de für einen bestimmten Suchbegriff
(z. B. "Tim Heimes") und schreibt sie in kurse.json.

Optimierungen:
- Browser-Mimikry (User-Agent, Referer)
- Retry bei 403 / 5xx
- kleine Vorschauausgabe bei leerem HTML (Debug)
"""

import re
import time
import json
import argparse
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://vhs-lahnstein.de"
HEADERS = {
    # Browser-Mimikry (Chrome unter Windows)
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Referer": "https://vhs-lahnstein.de/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MAX_RETRIES = 3
REQUEST_DELAY = 1.0


def fetch(url: str) -> str:
    """HTML mit Retry und Fake-Headers abrufen."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 403:
                print(f"⚠ Zugriff blockiert (403) – Versuch {attempt}/{MAX_RETRIES}")
                time.sleep(REQUEST_DELAY * 2)
                continue
            if r.status_code >= 500:
                print(f"⚠ Serverfehler ({r.status_code}) – Retry {attempt}")
                time.sleep(REQUEST_DELAY * 2)
                continue
            r.raise_for_status()
            if not r.text.strip():
                print("⚠ Leere Antwort erhalten.")
            return r.text
        except Exception as e:
            print(f"⚠ Fehler bei {url}: {e}")
            time.sleep(REQUEST_DELAY)
    print(f"❌ Dauerhaft fehlgeschlagen: {url}")
    return ""


def get_course_links(overview_url: str) -> list[str]:
    """Alle Kurslinks von der Übersichtsseite sammeln."""
    html = fetch(overview_url)
    if not html:
        print("⚠ Übersicht leer – vermutlich blockiert.")
        return []

    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(r"^/Veranstaltung/cmx[0-9a-f]+\.html$")
    links = [urljoin(BASE_URL, a["href"]) for a in soup.find_all("a", href=pattern)]
    print(f"Gefundene Kurslinks: {len(links)}")
    if len(links) == 0:
        print("🧾 HTML-Vorschau:", html[:500].replace("\n", " "))
    return sorted(set(links))


def clean_html(html: str) -> str:
    """HTML aufräumen, aber Formatierung (Absätze, Listen) erhalten."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["img", "picture", "figure", "source", "script", "style"]):
        t.decompose()

    allowed = {"p", "ul", "ol", "li", "br", "a", "b", "strong", "em"}
    for tag in soup.find_all(True):
        if tag.name not in allowed:
            tag.unwrap()
        else:
            tag.attrs = {k: v for k, v in tag.attrs.items() if k == "href"}

    text = str(soup)
    text = re.sub(r"(?i)(Zeiten?|Ort|Preis|Bankverbindung|IBAN).*", "", text)
    return text.strip()


def parse_course(url: str) -> dict:
    """Einzelnen Kurs extrahieren."""
    html = fetch(url)
    if not html:
        return {}

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

    # Volltext
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
    parser = argparse.ArgumentParser(description="VHS Lahnstein Kurs-Scraper 3.2 (GitHub)")
    parser.add_argument(
        "--url",
        default="https://vhs-lahnstein.de/Suche?cmxelementid=web4e15b88472a73&seite=Suche&Suche=1&Suchbegriffe=Tim+Heimes",
        help="Übersichtsseite mit Kursen",
    )
    parser.add_argument("--output", default="kurse.json", help="JSON-Datei speichern unter …")
    args = parser.parse_args()

    links = get_course_links(args.url)
    all_courses = []

    for link in links:
        try:
            course = parse_course(link)
            if course:
                all_courses.append(course)
        except Exception as e:
            print(f"⚠ Fehler bei {link}: {e}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_courses, f, ensure_ascii=False, indent=2)

    print(f"💾 {len(all_courses)} Kurse gespeichert in {args.output}")


if __name__ == "__main__":
    main()
