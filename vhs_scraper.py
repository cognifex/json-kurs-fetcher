#!/usr/bin/env python3
"""Scraper für VHS Lahnstein Kursdaten."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

BASE_URL = "https://vhs-lahnstein.de"
DEFAULT_SEARCH_URL = (
    "https://vhs-lahnstein.de/Suche?cmxelementid=web4e15b88472a73&seite=Suche&Suche=1&Suchbegriffe="
    "Tim+Heimes&Vormittag=1&Nachmittag=1&Abend=1&Montag=1&Dienstag=1&Mittwoch=1&Donnerstag=1&Freitag=1&Samstag=1&Sonntag=1"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VHS-Scraper/3.0; +https://vhs-lahnstein.de)",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}
REQUEST_DELAY = 1.0
MAX_RETRIES = 3
STOP_WORDS = ("zeiten", "ort", "preis", "bankverbindung", "iban")


@dataclass
class Course:
    guid: str
    titel: str
    beschreibung: str
    bild: str
    nummer: str
    ort: str
    preis: str
    dozent: str
    zeiten: str
    link: str


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")


def build_search_url(url: Optional[str], name: Optional[str]) -> str:
    if url:
        return url
    if not name:
        return DEFAULT_SEARCH_URL

    parsed = urlparse(DEFAULT_SEARCH_URL)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["Suchbegriffe"] = [name]
    encoded = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=encoded))


def fetch(session: requests.Session, url: str) -> Optional[str]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.debug("Hole %s (Versuch %s/%s)", url, attempt, MAX_RETRIES)
            response = session.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException as exc:  # pragma: no cover - Netzabhängig
            logging.warning("Fehler beim Abrufen von %s: %s", url, exc)
            time.sleep(REQUEST_DELAY)
            continue

        if response.status_code == 410:
            logging.warning("Seite entfernt (410): %s", url)
            time.sleep(REQUEST_DELAY)
            return None

        if response.ok:
            time.sleep(REQUEST_DELAY)
            return response.text

        logging.warning("Unerwarteter Statuscode %s für %s", response.status_code, url)
        time.sleep(REQUEST_DELAY)

    logging.error("Dauerhafte Fehler beim Abrufen von %s", url)
    return None


def extract_course_links(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(r"^/Veranstaltung/cmx[0-9a-f]+\.html$", re.IGNORECASE)
    links: List[str] = []
    seen = set()

    for anchor in soup.find_all("a", href=pattern):
        href = anchor.get("href")
        if not href:
            continue
        absolute = urljoin(BASE_URL, href)
        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)

    return links


def find_first(soup: BeautifulSoup, selectors: Iterable[str]) -> Optional[Tag]:
    for selector in selectors:
        tag = soup.select_one(selector)
        if tag and tag.get_text(strip=True):
            return tag
    return None


REMOVABLE_CLASS_KEYWORDS = (
    "zeit",
    "term",
    "ort",
    "preis",
    "bank",
    "iban",
    "konto",
)


def clean_description(html_fragment: str) -> str:
    if not html_fragment:
        return ""

    fragment = BeautifulSoup(html_fragment, "html.parser")
    container: Tag
    if fragment.body:
        container = fragment.body
    else:
        container = fragment

    for tag in container.find_all(["picture", "figure", "img", "source", "strong", "span", "h1", "h2", "h3", "header", "footer"]):
        tag.decompose()

    for tag in list(container.find_all(True)):
        classes = {cls.lower() for cls in tag.get("class", [])}
        identifier = " ".join(filter(None, [tag.get("id", "")] + sorted(classes)))
        if any(keyword in identifier for keyword in REMOVABLE_CLASS_KEYWORDS):
            tag.decompose()
            continue

    allowed = {"p", "ul", "ol", "li", "br", "a"}
    for tag in list(container.find_all(True)):
        if tag.name in allowed:
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in {"href"}}
            continue
        tag.unwrap()

    for tag in container.find_all(["p", "li"]):
        text = tag.get_text(" ", strip=True)
        if not text:
            tag.decompose()
            continue
        lowered = text.lower()
        if any(keyword in lowered for keyword in STOP_WORDS):
            tag.decompose()

    children: List[str] = []
    for child in container.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                children.append(text)
        elif isinstance(child, Tag):
            html = child.decode()
            if html.strip():
                children.append(html)

    cleaned = "".join(children).strip()
    cleaned = re.sub(r"\s*\n\s*", "\n", cleaned)

    if not cleaned:
        return ""

    filtered_lines = []
    for line in re.split(r"[\r\n]+", cleaned):
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(keyword in lowered for keyword in STOP_WORDS):
            continue
        filtered_lines.append(stripped)

    return "\n".join(filtered_lines)


def extract_details(soup: BeautifulSoup) -> Dict[str, str]:
    details: Dict[str, str] = {}
    pattern = re.compile(
        r"([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\s/]+):\s*(.*?)(?=(?:[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\s/]+):|$)",
        re.DOTALL,
    )

    detail_selectors = [
        "div.VeranstaltungTeaserDetails div",
        "div.detailBlock div",
        "div.veranstaltungDetails div",
        "div.courseDetails div",
    ]
    for selector in detail_selectors:
        for div in soup.select(selector):
            text = div.get_text(" ", strip=True)
            if not text or ":" not in text:
                continue
            matches = list(pattern.finditer(text))
            if not matches:
                key, value = text.split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                if key and value and key not in details:
                    details[key] = value
                continue
            for match in matches:
                key = match.group(1).strip().lower()
                value = re.sub(r"\s+", " ", match.group(2)).strip()
                if key and value and key not in details:
                    details[key] = value

    for dt in soup.find_all("dt"):
        dd = dt.find_next("dd")
        if not dd:
            continue
        key = dt.get_text(" ", strip=True).strip(":").lower()
        value = dd.get_text(" ", strip=True)
        if key and value and key not in details:
            details[key] = value

    return details


def strip_bankinfo(value: str) -> str:
    if not value:
        return ""
    cleaned = re.split(r"Bankverbindung|IBAN", value, flags=re.IGNORECASE)[0]
    return cleaned.strip()


def extract_image(soup: BeautifulSoup) -> str:
    image = soup.find("img", src=re.compile(r"/cmx/ordner/.cache/images/", re.IGNORECASE))
    if not image:
        return ""
    src = image.get("src", "").strip()
    if not src:
        return ""
    if src.startswith("http"):
        return src
    return urljoin(BASE_URL, src)


def extract_teacher(details: Dict[str, str], soup: BeautifulSoup) -> str:
    if "leitung" in details:
        return details["leitung"].strip()

    text = soup.get_text(" ", strip=True)
    match = re.search(r"Leitung\s*:?.{0,5}([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-\s]+)", text)
    if match:
        return match.group(1).strip()
    return ""


def extract_times(details: Dict[str, str], soup: BeautifulSoup) -> str:
    for key in ("zeiten", "termine"):
        if key in details and details[key]:
            return unique_lines(details[key])

    selectors = [
        "div.VeranstaltungTeaserTermine",
        "div.VeranstaltungTermine",
        "div.termine",
        "section.termine",
    ]
    for selector in selectors:
        container = soup.select_one(selector)
        if not container:
            continue
        text = container.get_text("\n", strip=True)
        if text:
            return unique_lines(text)
    return ""


def unique_lines(value: str) -> str:
    lines = [line.strip() for line in re.split(r"[\r\n]+", value) if line.strip()]
    seen: set[str] = set()
    unique: List[str] = []
    for line in lines:
        normalized = re.sub(r"\s+", " ", line).strip().lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(line)
    return "\n".join(unique)


def build_link(guid: str) -> str:
    if not guid:
        return ""
    return f"{BASE_URL}/Anmeldung/neueAnmeldung-true/f_veranstaltung-{guid}"


def parse_course(session: requests.Session, url: str) -> Optional[Course]:
    html = fetch(session, url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    guid_match = re.search(r"(cmx[0-9a-f]+)\.html", url, re.IGNORECASE)
    guid = guid_match.group(1) if guid_match else ""

    title_tag = soup.find("h1") or soup.find("h2")
    title = title_tag.get_text(" ", strip=True) if title_tag else ""

    description_container = find_first(
        soup,
        [
            "div.VeranstaltungInhalt",
            "div.VeranstaltungBeschreibung",
            "div.textbereich",
            "div.beschreibung",
            "article",
            "div.VeranstaltungTeaserInhalt",
        ],
    )
    description_html = description_container.decode_contents() if description_container else ""
    description = clean_description(description_html)

    details = extract_details(soup)
    nummer = details.get("nummer", "")
    ort = details.get("ort", "")
    preis = strip_bankinfo(details.get("preis", ""))
    dozent = extract_teacher(details, soup)
    zeiten = extract_times(details, soup)
    bild = extract_image(soup)
    link = build_link(guid)

    logging.info("✔︎ %s", title or guid or url)

    return Course(
        guid=guid,
        titel=title,
        beschreibung=description,
        bild=bild,
        nummer=nummer,
        ort=ort,
        preis=preis,
        dozent=dozent,
        zeiten=zeiten,
        link=link,
    )


def write_json(courses: Iterable[Course], output_path: str) -> None:
    payload = [asdict(course) for course in courses]
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scraper für vhs-lahnstein.de")
    parser.add_argument("--url", help="Eigene Such-URL verwenden", default=None)
    parser.add_argument("--name", help="Suchbegriff ersetzen (nur mit Standard-URL)", default=None)
    parser.add_argument("--output", help="Ausgabedatei (Standard: kurse.json)", default="kurse.json")
    parser.add_argument("--verbose", action="store_true", help="Ausführliche Logausgabe")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    search_url = build_search_url(args.url, args.name)
    logging.info("Lade Übersicht: %s", search_url)

    session = requests.Session()
    overview_html = fetch(session, search_url)
    if not overview_html:
        logging.error("Übersichtsseite konnte nicht geladen werden.")
        return 1

    course_links = extract_course_links(overview_html)
    logging.info("Gefundene Kurslinks: %s", len(course_links))

    courses: List[Course] = []
    for link in course_links:
        course = parse_course(session, link)
        if course:
            courses.append(course)

    write_json(courses, args.output)
    logging.info("%s Kurse gespeichert in %s", len(courses), args.output)
    return 0


if __name__ == "__main__":  # pragma: no cover - Skripteintritt
    sys.exit(main())
