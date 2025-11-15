#!/usr/bin/env python3
"""
Clean-Skript für VHS-Kurse.
Bereinigt die vom Scraper erzeugte kurse.json und schreibt kurse.clean.json.
"""

import json
import sys
import re
from bs4 import BeautifulSoup

# -------------------------------------------------------------
# Helferfunktionen
# -------------------------------------------------------------

def clean_html(html):
    """Bereinigt HTML von unnötigem Müll, ohne echten Inhalt zu verlieren."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Offensichtlicher Müll
    for tag in soup.find_all(["script", "style", "picture", "figure", "header", "footer"]):
        tag.decompose()

    # Leere Container entfernen
    for div in soup.find_all("div"):
        if not div.get_text(strip=True):
            div.decompose()

    # Extrahiere reinen Text
    text = soup.get_text("\n", strip=True)

    # Mehrfache Zeilenumbrüche reduzieren
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    # Mehrfache Leerzeichen entfernen
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def normalize_price(price):
    if not price:
        return ""
    price = price.replace("€", "").replace("EUR", "").strip()
    return price


def normalize_times(zeiten):
    if not zeiten:
        return ""
    z = re.sub(r"\s+", " ", zeiten).strip()
    return z


def normalize_title(title):
    if not title:
        return ""
    return re.sub(r"\s+", " ", title.strip())


def process_course(course):
    """Bereinigt ein einzelnes Kursobjekt."""
    cleaned = course.copy()

    cleaned["titel"] = normalize_title(course.get("titel", ""))
    cleaned["beschreibung_raw"] = course.get("beschreibung", "")

    cleaned["beschreibung"] = clean_html(course.get("beschreibung", ""))

    cleaned["preis"] = normalize_price(course.get("preis", ""))
    cleaned["zeiten"] = normalize_times(course.get("zeiten", ""))
    cleaned["dozent"] = course.get("dozent", "").strip()
    cleaned["ort"] = course.get("ort", "").strip()

    return cleaned


# -------------------------------------------------------------
# Main
# -------------------------------------------------------------

def main():
    if len(sys.argv) != 3:
        print("❌ Aufruf: python vhs_clean.py input.json output.json")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    print(f"📥 Lade {input_file} ...")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    cleaned = [process_course(c) for c in data]

    print(f"💾 Speichere bereinigte Datei nach {output_file} ...")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"✅ Fertig! {len(cleaned)} Kurse bereinigt.")


if __name__ == "__main__":
    main()
