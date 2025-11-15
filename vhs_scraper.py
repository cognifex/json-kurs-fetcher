#!/usr/bin/env python3
"""Scraper für Kursangebote der VHS Lahnstein (Hotfix-Version 2025)."""

import argparse
import json
import re
import time
import traceback
import os

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://vhs-lahnstein.de"
OVERVIEW_URLS = [
    "https://vhs-lahnstein.de/Suche?cmxelementid=web4e15b88472a73&seite=Suche&Suche=1&Suchbegriffe=Tim+Heimes"
    "&Vormittag=1&Nachmittag=1&Abend=1&Montag=1&Dienstag=1&Mittwoch=1&Donnertag=1&Freitag=1&Samstag=1&Sonntag=1",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    )
}

LABELS = ["Nummer", "Leitung", "Ort", "Preis"]

DEBUG_MODE = False


# ---------------------------------------------------------------------------
# Netzwerk
# ---------------------------------------------------------------------------

def fetch(url):
    """Lädt HTML mit Headern und einfachem Retry."""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 410:
                print(f"⚠️ Seite entfernt: {url}")
                return None
            print(f"⚠️ Status {resp.status_code} für {url}")
        except requests.RequestException as exc:
            print(f"⚠️ Fehler bei Abruf {url}: {exc}")
        time.sleep(1 + attempt)
    return None


# ---------------------------------------------------------------------------
# Kurslinks extrahieren
# ---------------------------------------------------------------------------

def extract_course_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.select("a[href*='/Veranstaltung/cmx']"):
        href = a.get("href")
        if not href:
            continue
        if not href.startswith("http"):
            href = BASE_URL + href
        if href.endswith(".html"):
            links.append(href)

    return sorted(set(links))


# ---------------------------------------------------------------------------
# Beschreibung bereinigen (Hotfix: safe cleaning)
# ---------------------------------------------------------------------------

def clean_description_container(container, title=None, safe=False):
    """Bereinigt HTML. safe=True = löscht KEINE Beschreibung anhand von Labels."""
    if not isinstance(container, Tag):
        return ""

    # Entferne nur offensichtlichen Müll
    for tag in container.find_all(["script", "style", "picture", "figure", "header", "footer"]):
        tag.decompose()

    # Tabellen wie gehabt entfernen
    for table in list(container.find_all("table")):
        if not isinstance(table, Tag):
            continue

        classes = table.get("class", []) or []

        if "layoutgrid" in classes or table.find("label"):
            table.decompose()
            continue

        try:
            if not table.get_text(strip=True):
                table.decompose()
        except Exception:
            table.decompose()

    # Attribute strippen
    for tag in container.find_all(True):
        if isinstance(tag, Tag):
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in {"href", "src"}}

    html_text = container.decode_contents().strip()
    return re.sub(r"\s+\n", "\n", html_text)


# ---------------------------------------------------------------------------
# Beschreibung sammeln (NEUES VHS-TEMPLATE)
# ---------------------------------------------------------------------------

def collect_description(soup, title=None):
    """
    Neue VHS-Struktur:
    Beschreibung liegt zuverlässig in:
        #content div.Text.Detail
    """

    # 1. Primärer neuer Hotfix-Selector
    new_selectors = [
        "#content div.Text.Detail",
        "div#content div.Text.Detail",
        "main div.Text.Detail",
    ]

    for selector in new_selectors:
        nodes = soup.select(selector)
        if nodes:
            merged = "".join(node.decode_contents() for node in nodes)
            wrapper = BeautifulSoup(f"<div>{merged}</div>", "html.parser")
            return clean_description_container(wrapper.div, title=title, safe=True)

    # 2. Großer Notfall-Fallback → gesamte Seite durchsuchen
    fallback = soup.select_one("#content, main, body")
    if fallback:
        return clean_description_container(fallback, title=title, safe=True)

    return ""


# ---------------------------------------------------------------------------
# Label-Erkennung (wie vorher)
# ---------------------------------------------------------------------------

def split_off_next_label(text, current_label):
    others = [l for l in LABELS if l != current_label]
    if not text:
        return ""

    pattern = re.compile(rf"\b(?:{'|'.join(others)})\b", re.I)
    m = pattern.search(text)
    if m:
        text = text[:m.start()]
    return text.strip(" -:\n\t ")


def find_labeled_value(soup, label):
    pattern = re.compile(rf"^{label}\s*:?(.*)$", re.I)

    for tag in soup.find_all(True):
        text = tag.get_text(" ", strip=True)
        m = pattern.match(text)
        if not m:
            continue
        value = m.group(1).strip()
        value = split_off_next_label(value, label)
        if value:
            return value

    return ""


# ---------------------------------------------------------------------------
# Zeiten extrahieren (stabilisiert)
# ---------------------------------------------------------------------------

def extract_times(soup):
    # Neue VHS-Struktur hat keine "VeranstaltungTermine" mehr
    # Daher fallback: Finde Datumsblöcke im gesamten Text
    page = soup.get_text(" ", strip=True)

    # Beispielmuster: 12.03.2025 19:00–21:00
    regex = r"\d{1,2}\.\d{2}\.\d{4}.*?(?=\b(?:Preis|Nummer|Leitung|Ort)\b|$)"
    m = re.search(regex, page)

    return m.group(0).strip() if m else ""


# ---------------------------------------------------------------------------
# Debug-Logger
# ---------------------------------------------------------------------------

def log_debug_error(url, html, error, traceback_text, title=None):
    os.makedirs("debug/html", exist_ok=True)

    guid_match = re.search(r"(cmx[0-9a-f]+)", url, re.I)
    guid = guid_match.group(1) if guid_match else "unknown"

    html_path = f"debug/html/{guid}.html"
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html or "")
    except Exception:
        pass

    entry = {
        "url": url,
        "guid": guid,
        "title": title,
        "error": str(error),
        "traceback": traceback_text,
        "html_file": html_path,
    }

    with open("debug/errors.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Parse-Safe Wrapper
# ---------------------------------------------------------------------------

def parse_course_safe(url, debug=False):
    try:
        html = fetch(url)
        if not html:
            raise RuntimeError("Seite konnte nicht geladen werden")

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("h1")
        pre_title = title_tag.get_text(strip=True) if title_tag else ""

        return parse_course(url)

    except Exception as err:
        print(f"❌ Fehler beim Kurs: {url}")
        tb = traceback.format_exc()
        if debug:
            log_debug_error(url, html if "html" in locals() else None, err, tb, title=pre_title)
        return None


# ---------------------------------------------------------------------------
# Regulierer Parser
# ---------------------------------------------------------------------------

def parse_course(url):
    html = fetch(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    course = {}

    guid_match = re.search(r"(cmx[0-9a-f]+)\.html", url, re.I)
    course["guid"] = guid_match.group(1) if guid_match else ""

    title_tag = soup.find("h1")
    course["titel"] = title_tag.get_text(strip=True) if title_tag else "Ohne Titel"

    course["beschreibung"] = collect_description(soup, title=course["titel"])

    img = soup.find("img", src=re.compile(r"/cmx/ordner/.cache/images/", re.I))
    if img:
        src = img.get("src", "")
        course["bild"] = src if src.startswith("http") else BASE_URL + src
    else:
        course["bild"] = ""

    for label in LABELS:
        course[label.lower()] = find_labeled_value(soup, label)

    course["dozent"] = course.pop("leitung", "")
    course["zeiten"] = extract_times(soup)

    guid_ref = re.search(r"f_veranstaltung-(cmx[0-9a-f]+)", html)
    signup_guid = guid_ref.group(1) if guid_ref else course["guid"]

    course["link"] = (
        f"{BASE_URL}/Anmeldung/neueAnmeldung-true/f_veranstaltung-{signup_guid}"
        if signup_guid else ""
    )

    print(f"✅ {course['titel']}")
    return course


# ---------------------------------------------------------------------------
# Kursiteration
# ---------------------------------------------------------------------------

def iterate_courses(urls):
    courses = []
    seen = set()

    for overview_url in urls:
        print(f"🔎 Lade Übersicht: {overview_url}")
        overview_html = fetch(overview_url)
        if not overview_html:
            continue

        course_links = extract_course_links(overview_html)
        print(f"Gefundene Kurse: {len(course_links)}")

        for link in course_links:
            if link in seen:
                continue
            seen.add(link)

            course = parse_course_safe(link, debug=DEBUG_MODE)
            if course:
                courses.append(course)

            time.sleep(1.5)

    return courses


# ---------------------------------------------------------------------------
# CLI / Main
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="VHS Kurs-Scraper")
    p.add_argument("--debug", action="store_true",
                   help="Speichert HTML & Fehlerlogs, bricht nie ab.")
    p.add_argument("--output", default="kurse.json",
                   help="Ziel-Datei (default: kurse.json)")
    return p.parse_args()


def main():
    global DEBUG_MODE

    args = parse_args()
    DEBUG_MODE = args.debug

    if DEBUG_MODE:
        print("🐞 Debug-Modus aktiviert")

    courses = iterate_courses(OVERVIEW_URLS)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(courses, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n💾 {len(courses)} Kurse gespeichert in '{args.output}'.")


if __name__ == "__main__":
    main()
