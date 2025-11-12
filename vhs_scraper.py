#!/usr/bin/env python3
import requests, re, json, time
from bs4 import BeautifulSoup

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
            time.sleep(2)
    return None


def extract_course_links(search_html):
    soup = BeautifulSoup(search_html, "html.parser")
    links = []
    for a in soup.select("a[href*='/Veranstaltung/cmx']"):
        href = a.get("href")
        if href and href.startswith("/Veranstaltung/cmx") and href.endswith(".html"):
            links.append(BASE_URL + href)
    return sorted(set(links))


def parse_course(url):
    html = fetch(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    kurs = {}
    kurs["guid"] = re.search(r"(cmx[0-9a-f]+)\.html", url, re.I).group(1)
    title_tag = soup.find(["h1", "h2"])
    kurs["titel"] = title_tag.get_text(strip=True) if title_tag else "Ohne Titel"

    # Beschreibung: entferne nur Termin-/Bankblöcke
    desc_tag = soup.find("div", class_=re.compile("inhalt|beschreibung|content", re.I))
    beschreibung = desc_tag.decode_contents().strip() if desc_tag else ""
    beschreibung = re.sub(
        r"(Zeiten|Anzahl|Leitung|Nummer|Ort|Preis|Bankverbindung).*?(<br>|$)",
        "",
        beschreibung,
        flags=re.I | re.DOTALL,
    ).strip()
    kurs["beschreibung"] = beschreibung

    # Bild
    img = soup.find("img", src=re.compile(r"/cmx/ordner/.cache/images/", re.I))
    if img:
        src = img.get("src", "")
        kurs["bild"] = src if src.startswith("http") else BASE_URL + src
    else:
        kurs["bild"] = ""

    text = soup.get_text(" ", strip=True)
    def grab(label):
        m = re.search(rf"{label}\s*:? ([^:]+?)(?: [A-ZÄÖÜ]|$)", text, re.I)
        return m.group(1).strip() if m else ""

    kurs["nummer"] = grab("Nummer")
    kurs["dozent"] = grab("Leitung")
    kurs["ort"] = grab("Ort")
    kurs["preis"] = grab("Preis")

    # Zeiten: hole alles zwischen Datum und Preis oder Zeilenende
    m = re.search(r"(\d{1,2}\.\d{2}\.\d{4}.*?)(?:Preis|Leitung|Nummer|$)", text, re.S)
    kurs["zeiten"] = m.group(1).strip() if m else ""

    # Link
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

    links = extract_course_links(html)
    print(f"Gefundene Kurse: {len(links)}")

    results = []
    for link in links:
        kurs = parse_course(link)
        if kurs:
            results.append(kurs)
        time.sleep(1)

    with open("kurse.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"💾 {len(results)} Kurse gespeichert in 'kurse.json'.")


if __name__ == "__main__":
    main()
