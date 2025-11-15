#!/usr/bin/env python3
"""Scraper für Kursangebote der VHS Lahnstein."""

import json
import re
import time

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


def clean_description_container(container, title=None):
    """Bereinigt HTML, behält aber Formatierung."""
    if container is None:
        return ""

    for tag in container.find_all(
        ["script", "style", "picture", "figure", "header", "footer"], recursive=True
    ):
        tag.decompose()

    for block in container.find_all(
        string=re.compile(r"\b(Zeiten|Preis|Nummer|Leitung|Ort|Bankverbindung)\b", re.I)
    ):
        parent = block.find_parent(["div", "p", "li", "tr", "table"])
        if parent is None:
            parent = block.parent
        if hasattr(parent, "decompose"):
            parent.decompose()

    for table in list(container.find_all("table")):
        if not isinstance(table, Tag):
            continue
        classes = table.get("class", [])
        if "layoutgrid" in classes or table.find("label"):
            table.decompose()
    for table in list(container.find_all("table")):
        if not isinstance(table, Tag):
            continue
        if not table.get_text(strip=True):
            table.decompose()

    for tag in container.find_all(True):
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in {"href", "src"}}

    if title:
        normalized_title = re.sub(r"\s+", " ", title).strip().lower()
        for heading in container.find_all(["h1", "h2"]):
            heading_text = re.sub(r"\s+", " ", heading.get_text(strip=True)).lower()
            if heading_text == normalized_title:
                heading.decompose()

    html_text = container.decode_contents().strip()
    return re.sub(r"\s+\n", "\n", html_text)


def collect_description(soup, title=None):
    """Fasst relevante Inhaltsblöcke zusammen."""
    primary_selectors = [
        "div.VeranstaltungInhalt",
        "div.VeranstaltungBeschreibung",
        "section.veranstaltungInhalt",
    ]
    fallback_selectors = [
        "div.Text.Detail",
        "main#content div.Text",
    ]
    sections = []
    seen = set()
    for selector in primary_selectors:
        for node in soup.select(selector):
            if id(node) in seen:
                continue
            seen.add(id(node))
            sections.append(node)

    if not sections:
        for selector in fallback_selectors:
            for node in soup.select(selector):
                if id(node) in seen:
                    continue
                seen.add(id(node))
                sections.append(node)
            if sections:
                break

    if not sections:
        return ""

    merged_html = "".join(section.decode_contents() for section in sections)
    wrapper = BeautifulSoup(f"<div>{merged_html}</div>", "html.parser")
    return clean_description_container(wrapper.div, title=title)


def split_off_next_label(text, current_label):
    """Schneidet alles ab, was zu einem nachfolgenden Label gehört."""
    other_labels = [label for label in LABELS if label != current_label]
    if not text:
        return ""
    pattern = re.compile(rf"\b(?:{'|'.join(other_labels)})\b", re.I)
    match = pattern.search(text)
    if match:
        text = text[: match.start()]
    return text.strip(" -:\n\t ")


def find_labeled_value(soup, label):
    """Sucht Textstellen wie 'Label: Wert' und extrahiert den Wert."""
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


def extract_times(soup):
    """Holt den Zeitenblock aus Termintabellen."""
    selectors = [
        "div.veranstaltungTermine",
        "div.VeranstaltungTermine",
        "section.veranstaltungTermine",
        "section.VeranstaltungTermine",
    ]
    for selector in selectors:
        container = soup.select_one(selector)
        if container:
            for tag in container.find_all(["script", "style", "picture", "figure"], recursive=True):
                tag.decompose()
            text = container.get_text(" ", strip=True)
            text = re.sub(r"\s{2,}", " ", text)
            return text.strip()

    table_value = find_labeled_value(soup, "Zeiten")
    if table_value:
        return table_value

    page_text = soup.get_text(" ", strip=True)
    match = re.search(r"(\d{1,2}\.\d{2}\.\d{4}.*?)(?=\b(?:Preis|Nummer|Leitung|Ort)\b|$)", page_text)
    return match.group(1).strip() if match else ""


def parse_course(url):
    """Extrahiert Felder aus einer Kursseite."""
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

    image_tag = soup.find("img", src=re.compile(r"/cmx/ordner/.cache/images/", re.I))
    if image_tag:
        src = image_tag.get("src", "")
        course["bild"] = src if src.startswith("http") else BASE_URL + src
    else:
        course["bild"] = ""

    for label in LABELS:
        course[label.lower()] = find_labeled_value(soup, label)

    course["dozent"] = course.pop("leitung", "")

    course["zeiten"] = extract_times(soup)

    guid_ref = re.search(r"f_veranstaltung-(cmx[0-9a-f]+)", html)
    if guid_ref:
        signup_guid = guid_ref.group(1)
    else:
        signup_guid = course["guid"]
    course["link"] = (
        f"{BASE_URL}/Anmeldung/neueAnmeldung-true/f_veranstaltung-{signup_guid}" if signup_guid else ""
    )

    print(f"✅ {course['titel']}")
    return course


def iterate_courses(urls):
    """Läuft über alle Übersichtsseiten und parst Kurse."""
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
            course = parse_course(link)
            if course:
                courses.append(course)
            time.sleep(1.5)
    return courses


def main():
    """Steuert den gesamten Ablauf und speichert kurse.json."""
    courses = iterate_courses(OVERVIEW_URLS)

    with open("kurse.json", "w", encoding="utf-8") as handle:
        json.dump(courses, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"\n💾 {len(courses)} Kurse gespeichert in 'kurse.json'.")


if __name__ == "__main__":
    main()
