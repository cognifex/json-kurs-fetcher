#!/usr/bin/env python3
"""
Clean-Skript für VHS-Kurse.
Nimmt die rohen Scraper-Daten und bereinigt sie für die Weiterverarbeitung.
"""

import json
import argparse
import re
from bs4 import BeautifulSoup


def clean_html(html):
    """Bereinigt HTML von Müll, ohne echte Inhalte zu zerstören."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Entferne offensichtliche Müll-Tags
    for tag in soup.find_all(["script", "style", "header", "footer", "picture", "figure"]):
        tag.decompose()

    # Entferne leere Container
    for div in soup.find_all("div"):
        if not div.get_text(strip=True):
            div.decompose()

    # Entferne doppelte Leerzeichen & Zeilenumbrüche
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def normalize_price(price):
    if not price:
        return ""
    price = price.strip()
    price = price.replace("€", "").replace("EUR", "")
    return price.strip()


def normalize_times(zeiten):
    if not zeiten:
        return ""
    z = re.sub(r"\s+", " ", zeiten)
    return z.strip()


def normalize_title(title):
    if not title:
        return ""
    title = title.strip()
    title = re.sub(r"\s+", " ", title)
    return title


def process_course(course):
    """Bereinigt ein einzelnes Kursobjekt."""

    cleaned = course.copy()

    cleaned["titel"] = normalize_title(course.get("titel", ""))
    cleaned["beschreibung_raw"] = course.get("beschreibung", "")

    # erzeugt ein bereinigtes Beschreibungstextfeld
    cleaned["beschreibung"] = clean_html(course.get("beschreibung", ""))

    cleaned["preis"] = normalize_price(course.get("preis", ""))
    cleaned["zeiten"] = normalize_times(course.get("zeiten", ""))
    cleaned["dozent"] = course.get("dozent", "").strip()
    cleaned["ort"] = course.get("ort", "").strip()

    return cleaned


def main():
    parser = argparse.ArgumentParser(description="Bereinigt VHS-Kurse JSON.")
    parser.add_argument("--input", default="kurse.json")
    parser.add_argument("--output", default="kurse_clean.json")
    args = parser.parse_args()

    print(f"📥 Lade {args.input} ...")

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    cleaned = []
    for c in data:
        cleaned.append(process_course(c))

    print(f"💾 Speichere bereinigte Daten nach {args.output} ...")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"✅ Fertig! {len(cleaned)} Kurse bereinigt.")


if __name__ == "__main__":
    main()
