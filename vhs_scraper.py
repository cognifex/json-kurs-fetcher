#!/usr/bin/env python3
"""Scraper für Kursangebote der VHS Lahnstein — Hotfix-Version."""

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
    "&Vormittag=1&Nachmittag=1&Abend=1&Montag=1&Dienstag=1&Mittwoch=1&Donnerstag=1&Freitag=1&Samstag=1&Sonntag=1",
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
            response = requests.get(url, headers=HEADERS, timeout=20)
            if response.status_code == 200:
                return response.text
            if response.status_code == 410:
                print(f"⚠️ Seite entfernt: {url}")
                return None
            print(f"⚠️ Status {response.status_code} für {url}")
        except requests.RequestException as exc:
            print(f"⚠️ Fehler bei Abruf {url}: {exc}")
        time.sleep(1 + attempt)
    return None


# ---------------------------------------------------------------------------
# Übersicht → Kurslinks
# ---------------------------------------------------------------------------

def extract_course_links(html):
    """Sammelt Kurslinks von einer Übersichtsseite."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for anchor in soup.select("a[href*='/Veranstaltung/cmx']"):
        href = anchor.get("href")
        if not href:
            continue
        if not href.startswith("http"):
            href = BASE_URL + href
        if href.endswith(".html"):
            links.append(href)
    return sorted(set(links))


# ---------------------------------------------------------------------------
# Beschreibung bereinigen (safe-mode Hotfix)
# ---------------------------------------------------------------------------

def clean_description_container(container, title=None, safe=False):
    """
    Bereinigt HTML.
    HOTFIX:
    - safe=True = Labels NICHT entfernen (neue VHS-Seiten haben sie mitten im Text)
    """
    if not isinstance(container, Tag):
        return ""

    # JavaScript/CSS entfernen
    for tag in container.find_all(["script", "style", "picture", "figure", "header", "footer"]):
        tag.decompose()

    # Ursprüngliche Entfernung der Label-Blöcke — nur wenn nicht safe
    if not safe:
        for block in container.find_all(
            string=re.compile(r"\b(Zeiten|Preis|Nummer|Leitung|Ort|Bankverbindung)\b", re.I)
        ):
            parent = block.find_parent(["div", "p", "li", "tr", "table"]) or block.parent
            if isinstance(parent, Tag):
                parent.decompose()

    # Tabellen entfernen
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

    # Unerwünschte Attribute entfernen
    for tag in container.find_all(True):
        if isinstance(tag, Tag):
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in {"href", "src"}}

    html_text = container.decode_contents().strip()
    return re.sub(r"\s+\n", "\n", html_text)


# ---------------------------------------------------------------------------
# Beschreibung sammeln (mit erweitertem Hotfix)
# ---------------------------------------------------------------------------

def collect_description(soup, title=None):
    """Fasst relevante Inhaltsblöcke zusammen (Hotfix für neues VHS-Template)."""
    primary_selectors = [
        "div.VeranstaltungInhalt",
        "div.VeranstaltungBeschreibung",
        "section.veranstaltungInhalt",
    ]

    fallback_selectors = [
        "div.Text.Detail",
        "main#content div.Text",
    ]

    # HOTFIX: neue VHS-Struktur
    hotfix_selectors = [
        "#content div.Text.Detail",
        "div#content div.Text.Detail",
        "main div.Text.Detail",
        "#content div.Text",
    ]

    # 1. Original-Selektoren
    sections = []
    seen = set()
    for selector in primary_selectors:
        for node in soup.select(selector):
            if id(node) not in seen:
                seen.add(id(node))
                sections.append(node)

    # 2. Alte Fallbacks
    if not sections:
        for selector in fallback_selectors:
            for node in soup.select(selector):
                if id(node) not in seen:
                    seen.add(id(node))
                    sections.append(node)
            if sections:
                break

    # 3. HOTFIX
    if not sections:
        for selector in hotfix_selectors:
            for node in soup.select(selector):
                if id(node) not in seen:
                    seen.add(id(node))
                    sections.append(node)
            if sections:
                break

    # 4. Letzter Notfall
    if not sections:
        fallback = soup.select_one("main, #content, body")
        if fallback:
            return clean_description_container(fallback, title=title, safe=True)
        return ""

    merged_html = "".join(section.decode_contents() for section in sections)
    wrapper = BeautifulSoup(f"<div>{merged_html}</div>", "html.parser")

    # HOTFIX: safe=True, damit Labels nicht entfernt werden
    return clean_description_container(wrapper.div, title=title, safe=True)


# ---------------------------------------------------------------------------
# Label-Extraktion
# ---------------------------------------------------------------------------

def split_off_next_label(text, current_label):
    other_labels = [label for label in LABELS if label != current_label]
    if not text:
        return ""

    pattern = re.compile(rf"\b(?:{'|'.join(other_labels)})\b", re.I)
    match = pattern.search(text)
    if match:
        text = text[: match.start()]
    return text.strip(" -:\n\t ")


def find_labeled_value(soup, label):
    pattern = re.compile(rf"^{label}\s*:?(.*)$", re.I)
    for tag in soup.find_all(True):
        text = tag.get_text(" ", strip=True)
        match = pattern.match(text)
        if not match:
            continue
        value = match.group(1).strip()
        value = split_off_next_label(value, label)
        if value:
            return value
    return ""


# ---------------------------------------------------------------------------
# Zeiten
# ---------------------------------------------------------------------------

def extract_times(soup):
    selectors = [
        "div.veranstaltungTermine",
        "div.VeranstaltungTermine",
        "section.veranstaltungTermine",
        "section.VeranstaltungTermine",
    ]
    for sel in selectors:
        c = soup.select_one(sel)
        if c:
            for tag in c.find_all(["script", "style", "picture", "figure"], recursive=True):
                tag.decompose()
            text = c.get_text(" ", strip=True)
            text = re.sub(r"\s{2,}", " ", text)
            return text.strip()

    value = find_labeled_value(soup, "Zeiten")
    if value:
        return value

    page_text = soup.get_text(" ", strip=True)
    match = re.search(
        r"(\d{1,2}\.\d{2}\.\d{4}.*?)(?=\b(?:Preis|Nummer|Leitung|Ort)\b|$)",
        page_text
    )
    return match.group(1).strip() if match else ""


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
        title_tag = soup.find(["h1", "h2"])
        pre_title = title_tag.get_text(strip=True) if title_tag else None

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

    title_tag = soup.find(["h1", "h2"])
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
    parser = argparse.ArgumentParser(description="VHS Kurs-Scraper")
    parser.add_argument("--debug", action="store_true",
                        help="Speichert HTML & Fehlerlogs, bricht nie ab.")
    parser.add_argument("--output", default="kurse.json",
                        help="Ziel-Datei (default: kurse.json)")
    return parser.parse_args()


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
