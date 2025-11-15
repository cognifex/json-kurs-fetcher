import argparse
import json
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from bs4 import BeautifulSoup, Tag


ADMIN_KEYWORDS = {
    "iban",
    "bic",
    "bankverbindung",
    "name der bank",
    "kontoinhaber",
    "zahlungsbedingungen",
    "teilnahmebedingungen",
    "gebührenordnung",
    "rücktritt",
    "haftung",
    "datenschutz",
    "zahlung",
}


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def iter_stripped_strings(node: Tag) -> Iterable[str]:
    for chunk in node.stripped_strings:
        text = normalize_whitespace(chunk)
        if text:
            yield text


def format_times_summary(cell: Tag) -> List[str]:
    return list(iter_stripped_strings(cell))


def format_times_details(cell: Tag) -> Tuple[List[str], Optional[str]]:
    header: Optional[str] = None
    summary_tag = cell.find("summary")
    if summary_tag:
        summary_text = normalize_whitespace(" ".join(summary_tag.stripped_strings))
        if summary_text:
            header = f"Termine ({summary_text})"

    detail_lines: List[str] = []
    table = cell.find("table")
    if not table:
        return detail_lines, header

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue

        date_text = ""
        time_text = ""
        status_text = ""
        primary_parts = list(iter_stripped_strings(cells[0]))
        if primary_parts:
            date_text = primary_parts[0]
        if len(primary_parts) >= 2:
            time_text = primary_parts[1]
        if len(primary_parts) >= 3:
            status_text = primary_parts[2]

        location_text = ""
        if len(cells) > 1:
            location_text = " ".join(iter_stripped_strings(cells[1]))

        line_parts: List[str] = []
        if date_text and time_text:
            line_parts.append(f"{date_text}, {time_text}")
        elif date_text:
            line_parts.append(date_text)
        elif time_text:
            line_parts.append(time_text)

        extra_parts: List[str] = []
        if status_text:
            extra_parts.append(status_text)
        if location_text:
            extra_parts.append(location_text)

        core_text = line_parts[0] if line_parts else ""
        if extra_parts:
            joiner = " – ".join(extra_parts)
            core_text = f"{core_text} – {joiner}" if core_text else joiner

        if core_text:
            detail_lines.append(f"- {core_text}")

    return detail_lines, header


def extract_times(soup: BeautifulSoup) -> str:
    table = soup.select_one("table.layoutgrid")
    if not table:
        return ""

    summary_lines: List[str] = []
    detail_lines: List[str] = []
    header: Optional[str] = None

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label_tag = cells[0].find("label")
        if not label_tag:
            continue
        label = normalize_whitespace(label_tag.get_text())
        value_cell = cells[1]
        key = label.lower()

        if key == "zeiten":
            summary_lines.extend(format_times_summary(value_cell))
        elif key in {"anzahl", "termine"}:
            details, candidate_header = format_times_details(value_cell)
            detail_lines.extend(details)
            if candidate_header and not header:
                header = candidate_header

    table.decompose()

    sections: List[str] = []
    if summary_lines:
        sections.append("\n".join(summary_lines))
    if detail_lines:
        heading = header or "Termine"
        sections.append(f"{heading}\n" + "\n".join(detail_lines))

    return "\n\n".join(section for section in sections if section).strip()


def remove_admin_lines(lines: Sequence[str]) -> List[str]:
    result: List[str] = []
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in ADMIN_KEYWORDS):
            continue
        if not result or result[-1] != line:
            result.append(line)
    return result


def join_paragraphs(lines: Sequence[str]) -> str:
    paragraphs: List[str] = []
    index = 0
    length = len(lines)
    while index < length:
        line = lines[index]
        if line.startswith("- "):
            bullet_block: List[str] = []
            while index < length and lines[index].startswith("- "):
                bullet_block.append(lines[index])
                index += 1
            paragraphs.append("\n".join(bullet_block))
        else:
            paragraphs.append(line)
            index += 1
    return "\n\n".join(paragraphs).strip()


def extract_description(soup: BeautifulSoup, title: str) -> str:
    for tag in soup.find_all(["script", "style", "picture", "figure", "img", "svg", "header", "footer"]):
        tag.decompose()

    for li in soup.find_all("li"):
        bullet_text = normalize_whitespace(" ".join(li.stripped_strings))
        li.clear()
        if bullet_text:
            li.append(f"- {bullet_text}")
    for container in soup.find_all(["ul", "ol"]):
        container.unwrap()

    for br in soup.find_all("br"):
        br.replace_with("\n")

    text = soup.get_text("\n")
    raw_lines = [normalize_whitespace(line) for line in text.splitlines()]
    lines = [line for line in raw_lines if line]
    lines = remove_admin_lines(lines)

    title = title.strip()
    if title:
        if not lines or lines[0].lower() != title.lower():
            lines.insert(0, title)

    return join_paragraphs(lines)


def process_course(course: dict) -> dict:
    course_copy = dict(course)
    raw_html = course.get("beschreibung") or ""
    course_copy["beschreibung_raw"] = raw_html

    soup = BeautifulSoup(raw_html, "html.parser") if raw_html else BeautifulSoup("", "html.parser")
    times_text = extract_times(soup)
    description = extract_description(soup, course.get("titel", ""))

    course_copy["beschreibung"] = description
    if times_text:
        course_copy["zeiten"] = times_text
    else:
        course_copy["zeiten"] = normalize_whitespace(course.get("zeiten", ""))

    return course_copy


def transform_payload(payload) -> dict:
    if isinstance(payload, dict):
        courses = payload.get("data", [])
    else:
        courses = payload

    processed_courses = [process_course(course) for course in courses or []]

    if isinstance(payload, dict):
        result = {k: v for k, v in payload.items() if k != "data"}
        result["data"] = processed_courses
        return result
    return {"data": processed_courses}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bereinigt Kurseinträge aus dem Scraper-Export.")
    parser.add_argument("input", type=Path, help="Pfad zur Eingabedatei (kurse.json)")
    parser.add_argument("output", type=Path, help="Pfad zur Ausgabedatei (kurse.clean.json)")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = transform_payload(payload)

    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
