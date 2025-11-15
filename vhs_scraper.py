#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json, re, time

BASE_URL = "https://vhs-lahnstein.de"
SEARCH_URL = (
    "https://vhs-lahnstein.de/Suche?"
    "cmxelementid=web4e15b88472a73&seite=Suche&Suche=1&Suchbegriffe=Tim+Heimes"
    "&Vormittag=1&Nachmittag=1&Abend=1&Montag=1&Dienstag=1&Mittwoch=1&Donnerstag=1&Freitag=1&Samstag=1&Sonntag=1"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/129.0.0.0 Safari/537.36"
}


def fetch(url):
    """Hilfsfunktion mit Retry"""
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.text
            elif r.status_code == 410:
                print(f"⚠️ Seite entfernt: {url}")
                return None
        except Exception as e:
            print(f"Fehler bei Abruf {url}: {e}")
            time.sleep(1)
    return None


def extract_course_links(search_html):
    """Alle Kurslinks aus der Übersichtsseite sammeln"""
    soup = BeautifulSoup(search_html, "html.parser")
    links = []
    for a in soup.select("a[href*='/Veranstaltung/cmx']"):
        href = a.get("href")
        if href and href.startswith("/Veranstaltung/cmx") and href.endswith(".html"):
            links.append(BASE_URL + href)
    return sorted(set(links))


def clean_html_keep_format(soup_section):
    """HTML säubern, aber Format (Absätze, <br>, Listen) erhalten"""
    # Entferne Elemente mit rein organisatorischem Inhalt
    for tag in soup_section.find_all(
        ["script", "style", "picture", "figure", "header", "footer"], recursive=True
    ):
        tag.decompose()

    # Unnötige Inline-Styles und Klassen weg
    for tag in soup_section.find_all(True):
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in ["href", "src"]}

    # Entferne reine Termin-/Bankblöcke
    for bad in soup_section.find_all(
        string=re.compile(r"(Zeiten|Anzahl|Leitung|Nummer|Ort|Preis|Bankverbindung)", re.I)
    ):
        bad_parent = bad.find_parent(["div", "p", "li"])
        if bad_parent:
            bad_parent.decompose()

    # Rückgabe mit erhaltenem HTML
    html_str = soup_section.decode_contents()
    html_str = re.sub(r"\s+\n", "\n", html_str)
    return html_str.strip()


def parse_course(url):
    """Einzelne Kursseite scrapen"""
    html = fetch(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    kurs = {}

    # GUID aus URL
    m = re.search(r"(cmx[0-9a-f]+)\.html", url, re.I)
    kurs["guid"] = m.group(1) if m else ""

    # Titel
    title_tag = soup.find(["h1", "h2"])
    kurs["titel"] = title_tag.get_text(strip=True) if title_tag else "Ohne Titel"

    # --- Beschreibung (mehrere Abschnitte zusammenführen) ---
    content_sections = soup.select(
        "div.VeranstaltungInhalt, div.VeranstaltungBeschreibung, "
        "div.textbereich, section.veranstaltungInhalt"
    )
    beschreibung_html = ""
    if content_sections:
        merged = BeautifulSoup("<div></div>", "html.parser")
        container = merged.div
        for section in content_sections:
            for child in section.contents:
                container.append(child)
        beschreibung_html = clean_html_keep_format(container)

    kurs["beschreibung"] = beschreibung_html

    # --- Bild ---
    bild_tag = soup.find("img", src=re.compile(r"/cmx/ordner/.cache/images/", re.I))
    if bild_tag:
        src = bild_tag.get("src")
        kurs["bild"] = src if src.startswith("http") else BASE_URL + src
    else:
        kurs["bild"] = ""

    # --- Textinhalt für Metadaten ---
    text = soup.get_text(" ", strip=True)

    def extract_field(label):
        m = re.search(rf"{label}\s*:? ([^\n\r]+)", text, re.I)
        return m.group(1).strip() if m else ""

    kurs["nummer"] = extract_field("Nummer")
    kurs["dozent"] = extract_field("Leitung")
    kurs["ort"] = extract_field("Ort")
    kurs["preis"] = extract_field("Preis")

    # --- Zeiten ---
    m = re.search(r"(\d{1,2}\.\d{2}\.\d{4}.*?)(?:Preis|Leitung|Nummer|$)", text, re.S)
    kurs["zeiten"] = m.group(1).strip() if m else ""

    # --- Anmeldelink ---
    m = re.search(r"f_veranstaltung-(cmx[0-9a-f]+)", html)
    guid = m.group(1) if m else kurs["guid"]
    kurs["link"] = f"{BASE_URL}/Anmeldung/neueAnmeldung-true/f_veranstaltung-{guid}"

    print(f"✅ {kurs['titel']}")
    return kurs


def main():
    print(f"🔎 Lade Übersicht: {SEARCH_URL}")
    html = fetch(SEARCH_URL)
    if not html:
        print("❌ Fehler: Übersicht nicht abrufbar.")
        return

    kurs_links = extract_course_links(html)
    print(f"Gefundene Kurse: {len(kurs_links)}")

    result = []
    for link in kurs_links:
        kurs = parse_course(link)
        if kurs:
            result.append(kurs)
        time.sleep(1.5)  # etwas Pause

    with open("kurse.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n💾 {len(result)} Kurse gespeichert in 'kurse.json'.")


if __name__ == "__main__":
    main()
