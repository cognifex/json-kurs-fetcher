#!/usr/bin/env python3
import requests, json, re, time
from bs4 import BeautifulSoup

BASE_URL = "https://vhs-lahnstein.de"
SEARCH_URL = "https://vhs-lahnstein.de/Suche?cmxelementid=web4e15b88472a73&seite=Suche&Suche=1&Suchbegriffe=Tim+Heimes&Vormittag=1&Nachmittag=1&Abend=1&Montag=1&Dienstag=1&Mittwoch=1&Donnerstag=1&Freitag=1&Samstag=1&Sonntag=1"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VHS-Scraper/2.1)"}


def fetch(url):
    """Lädt HTML mit Retry"""
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.text
            elif r.status_code == 410:
                print(f"⚠️  Seite entfernt: {url}")
                return None
        except Exception as e:
            print(f"Fehler bei Abruf {url}: {e}")
            time.sleep(1)
    return None


def extract_course_links(html):
    """Alle Kurslinks von der Übersicht"""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("a[href*='/Veranstaltung/cmx']"):
        href = a.get("href")
        if href and href.startswith("/Veranstaltung/cmx") and href.endswith(".html"):
            links.append(BASE_URL + href)
    return list(set(links))


def clean_html_fragment(html):
    """Entfernt Kopfzeilen, Bilder, Figures etc. und säubert kaputte Tags"""
    soup = BeautifulSoup(html, "html.parser")

    # Unerwünschte Tags entfernen
    for tag in soup.find_all(["picture", "img", "source", "strong", "h1", "figure"]):
        tag.decompose()

    # Leere Container löschen
    for div in soup.find_all("div"):
        if not div.get_text(strip=True):
            div.decompose()

    # Überflüssige span-Tags entfernen
    for span in soup.find_all("span"):
        span.unwrap()

    return str(soup).strip()


def parse_course(url):
    """Parst eine Kursdetailseite"""
    html = fetch(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    kurs = {}

    # GUID aus URL
    m = re.search(r"cmx([a-z0-9]+)\.html", url)
    kurs["guid"] = f"cmx{m.group(1)}" if m else ""

    # Titel
    title_tag = soup.find(["h1", "h2"])
    kurs["titel"] = title_tag.get_text(strip=True) if title_tag else "Ohne Titel"

    # Beschreibung (gezielt & Fallback)
    desc_tag = soup.select_one(
        "div.VeranstaltungTeaserInhalt, div.VeranstaltungInhalt, div.textbereich, div.beschreibung"
    )
    if not desc_tag:
        candidates = [d for d in soup.find_all("div") if len(d.get_text(strip=True)) > 300]
        desc_tag = max(candidates, key=lambda d: len(d.get_text(strip=True)), default=None)

    beschreibung = clean_html_fragment(desc_tag.decode_contents()) if desc_tag else ""
    beschreibung = re.sub(r"(Zeiten|Leitung|Nummer|Ort|Preis|Bankverbindung).*", "", beschreibung, flags=re.DOTALL)
    kurs["beschreibung"] = beschreibung.strip()

    # Kursbild
    bild_tag = soup.find("img", src=re.compile(r"/cmx/ordner/.cache/images/"))
    if bild_tag:
        src = bild_tag.get("src")
        kurs["bild"] = src if src.startswith("http") else BASE_URL + src
    else:
        kurs["bild"] = ""

    # Details (Nummer, Ort, Preis) aus strukturiertem Block
    details = {}
    for div in soup.select("div.VeranstaltungTeaserDetails div"):
        txt = div.get_text(" ", strip=True)
        if ":" in txt:
            k, v = txt.split(":", 1)
            details[k.strip().lower()] = v.strip()

    def strip_bankinfo(s: str) -> str:
        return re.split(r"Bankverbindung", s)[0].strip()

    kurs["nummer"] = details.get("nummer", "")
    kurs["ort"] = details.get("ort", "")
    kurs["preis"] = strip_bankinfo(details.get("preis", ""))

    # Dozent und Zeiten (aus Text)
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Leitung\s*:?\s*([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\s\-]+)", text)
    kurs["dozent"] = m.group(1).strip() if m else ""

    m = re.search(r"(\d{1,2}\.\d{2}\.\d{4}.*?)(?= Preis|Leitung|Nummer|Ort|$)", text)
    kurs["zeiten"] = m.group(1).strip() if m else ""

    # Anmeldelink
    m = re.search(r"f_veranstaltung-(cmx[0-9a-f]+)", html)
    guid = m.group(1) if m else kurs["guid"]
    kurs["link"] = f"{BASE_URL}/Anmeldung/neueAnmeldung-true/f_veranstaltung-{guid}"

    print(f"✅ {kurs['titel']}")
    return kurs


def main():
    print(f"🔎 Lade Übersicht: {SEARCH_URL}")
    html = fetch(SEARCH_URL)
    if not html:
        print("❌ Übersicht nicht abrufbar.")
        return

    kurs_links = extract_course_links(html)
    print(f"Gefundene Kurse: {len(kurs_links)}")

    result = []
    for link in kurs_links:
        kurs = parse_course(link)
        if kurs:
            result.append(kurs)
        time.sleep(1.5)

    with open("kurse.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n💾 {len(result)} Kurse gespeichert in 'kurse.json'.")


if __name__ == "__main__":
    main()
