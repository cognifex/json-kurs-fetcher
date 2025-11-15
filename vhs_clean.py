import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag


ADMIN_ALWAYS_KEYWORDS = {
    "iban",
    "bic",
    "bankverbindung",
    "name der bank",
    "kontoinhaber",
}

ADMIN_PREFIX_KEYWORDS = {
    "zahlungsbedingungen",
    "teilnahmebedingungen",
    "gebührenordnung",
    "rücktritt",
    "haftung",
    "zahlung",
}

ALLOWED_BLOCK_TAGS = {
    "p",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
}

ALLOWED_INLINE_TAGS = {
    "strong",
    "em",
    "b",
    "i",
    "u",
    "sup",
    "sub",
    "span",
    "a",
    "code",
}

ALLOWED_LIST_TAGS = {"li"}

ALLOWED_TAGS = ALLOWED_BLOCK_TAGS | ALLOWED_INLINE_TAGS | ALLOWED_LIST_TAGS | {"br"}

ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
}

REMOVED_TAGS = {
    "script",
    "style",
    "picture",
    "figure",
    "img",
    "svg",
    "header",
    "footer",
    "noscript",
}

STOP_KEYWORDS = {
    "zeiten",
    "anzahl",
    "termine",
    "leitung",
    "nummer",
    "ort",
    "preis",
}


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def convert_span_formatting(tag: Tag) -> None:
    if tag.name != "span":
        return

    raw_style = tag.get("style", "")
    style_map = {}
    for chunk in raw_style.split(";"):
        if ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        style_map[key.strip().lower()] = value.strip().lower()

    classes = [cls.lower() for cls in tag.get("class", [])]

    font_weight = style_map.get("font-weight")
    font_style = style_map.get("font-style")

    if font_weight in {"bold", "bolder", "600", "700", "800", "900"} or any("bold" in cls for cls in classes):
        tag.name = "strong"
    elif font_style in {"italic", "oblique"} or any(cls in {"italic", "kursiv"} or "italic" in cls for cls in classes):
        tag.name = "em"

    if "style" in tag.attrs:
        del tag.attrs["style"]
    if "class" in tag.attrs:
        del tag.attrs["class"]


def sanitize_tag(tag: Tag) -> None:
    convert_span_formatting(tag)

    if tag.name not in ALLOWED_TAGS:
        tag.unwrap()
        return

    allowed = ALLOWED_ATTRIBUTES.get(tag.name, set())
    for attr in list(tag.attrs):
        if attr not in allowed:
            del tag.attrs[attr]

    if tag.name == "a" and "href" in tag.attrs:
        tag.attrs["href"] = tag.attrs["href"].strip()
        if not tag.attrs["href"]:
            del tag.attrs["href"]


def clean_description_tree(root: Tag) -> None:
    for removable in list(root.find_all(REMOVED_TAGS)):
        removable.decompose()

    for tag in list(root.find_all(True)):
        sanitize_tag(tag)

    unwrap_block_wrappers(root)
    normalize_orphan_list_items(root)

    for tag in list(root.find_all(True)):
        if tag.name == "br":
            continue
        text_content = normalize_whitespace(tag.get_text(" "))
        if text_content:
            continue
        tag.decompose()


def unwrap_block_wrappers(root: Tag) -> None:
    block_like_children = (ALLOWED_BLOCK_TAGS | {"ul", "ol"}) - {"p"}
    for paragraph in list(root.find_all("p")):
        if any(isinstance(child, Tag) and child.name in block_like_children for child in paragraph.children):
            paragraph.unwrap()


def normalize_orphan_list_items(root: Tag) -> None:
    for child in list(root.children):
        if isinstance(child, Tag):
            normalize_orphan_list_items(child)

    if not isinstance(root, Tag):
        return

    if root.name in {"ul", "ol"}:
        return

    wrapper: Optional[Tag] = None
    for child in list(root.children):
        if isinstance(child, Tag) and child.name == "li":
            if wrapper is None:
                wrapper = root.new_tag("ul")
                child.insert_before(wrapper)
            child.extract()
            wrapper.append(child)
        else:
            wrapper = None


def collect_blocks(root: Tag, soup: BeautifulSoup) -> List[Tag]:
    blocks: List[Tag] = []
    for child in list(root.children):
        if isinstance(child, NavigableString):
            text = normalize_whitespace(str(child))
            if not text:
                continue
            paragraph = soup.new_tag("p")
            paragraph.string = text
            blocks.append(paragraph)
            continue

        if not isinstance(child, Tag):
            continue

        if child.name in ALLOWED_BLOCK_TAGS:
            blocks.append(child)
        elif child.name in ALLOWED_INLINE_TAGS:
            child.extract()
            paragraph = soup.new_tag("p")
            paragraph.append(child)
            blocks.append(paragraph)
        else:
            blocks.extend(collect_blocks(child, soup))

    deduped: List[Tag] = []
    seen_ids = set()
    for block in blocks:
        identifier = id(block)
        if identifier in seen_ids:
            continue
        seen_ids.add(identifier)
        deduped.append(block)
    return deduped


def is_admin_block(block: Tag, text: str) -> bool:
    if not text:
        return False

    lowered = text.lower()
    if block.name in {"ul", "ol", "li", "table"}:
        return False

    if any(keyword in lowered for keyword in ADMIN_ALWAYS_KEYWORDS):
        return True

    normalized = re.sub(r"\s+", " ", lowered).strip()
    for keyword in ADMIN_PREFIX_KEYWORDS:
        if normalized.startswith(keyword):
            return True

    return False


def filter_admin_blocks(blocks: Sequence[Tag]) -> List[Tag]:
    filtered: List[Tag] = []
    last_text: Optional[str] = None
    for block in blocks:
        text = normalize_whitespace(block.get_text(" ", strip=True))
        if not text:
            continue
        if is_admin_block(block, text):
            continue
        if last_text == text:
            continue
        filtered.append(block)
        last_text = text
    return filtered


def truncate_after_stop_keywords(blocks: Sequence[Tag]) -> List[Tag]:
    trimmed: List[Tag] = []
    for block in blocks:
        text = normalize_whitespace(block.get_text(" ", strip=True))
        lowered = text.lower()
        if any(lowered.startswith(keyword) for keyword in STOP_KEYWORDS):
            break
        trimmed.append(block)
    return trimmed


def ensure_title_block(blocks: List[Tag], soup: BeautifulSoup, title: str) -> List[Tag]:
    normalized_title = normalize_whitespace(title)
    if not normalized_title:
        return blocks

    if blocks:
        first_text = normalize_whitespace(blocks[0].get_text(" ", strip=True))
        if first_text.lower() == normalized_title.lower():
            return blocks

    title_paragraph = soup.new_tag("p")
    strong_tag = soup.new_tag("strong")
    strong_tag.string = normalized_title
    title_paragraph.append(strong_tag)
    return [title_paragraph, *blocks]


def blocks_to_string(blocks: Sequence[Tag]) -> str:
    if not blocks:
        return ""

    output = BeautifulSoup("", "html.parser")
    for index, block in enumerate(blocks):
        output.append(block)
        if index != len(blocks) - 1:
            output.append(output.new_string("\n\n"))

    return output.decode().strip()


def iter_stripped_strings(node: Tag) -> Iterable[str]:
    for chunk in node.stripped_strings:
        text = normalize_whitespace(chunk)
        if text:
            yield text


def format_times_summary(cell: Tag) -> List[str]:
    return list(iter_stripped_strings(cell))


def prettify_summary_line(line: str) -> str:
    if not line:
        return ""
    # Replace comma-separated fragments with middot separators for a calmer look
    return re.sub(r",\s+", " · ", line)


def format_times_details(cell: Tag) -> Tuple[List[Dict[str, str]], Optional[str]]:
    header: Optional[str] = None
    summary_tag = cell.find("summary")
    if summary_tag:
        summary_text = normalize_whitespace(" ".join(summary_tag.stripped_strings))
        if summary_text:
            header = f"Termine ({summary_text})"

    detail_items: List[Dict[str, str]] = []
    table = cell.find("table")
    if not table:
        return detail_items, header

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

        item: Dict[str, str] = {}
        if date_text:
            item["date"] = date_text
        if time_text:
            item["time"] = time_text
        if status_text:
            item["status"] = status_text
        if location_text:
            item["location"] = location_text

        if item:
            detail_items.append(item)

    return detail_items, header


def normalise_location(value: Optional[str]) -> str:
    if not value:
        return ""
    return normalize_whitespace(value).rstrip(" .")


def split_heading_parts(raw_heading: Optional[str]) -> Tuple[str, str]:
    heading = normalize_whitespace(raw_heading or "")
    if not heading:
        return "Termine", ""

    if "(" in heading and heading.endswith(")"):
        open_idx = heading.find("(")
        close_idx = heading.rfind(")")
        if open_idx != -1 and close_idx > open_idx:
            label = heading[:open_idx].strip()
            badge = heading[open_idx + 1 : close_idx].strip()
            if label:
                return label, badge

    return heading, ""


def build_times_detail_text(item: Dict[str, str], course_location: str = "") -> str:
    date_text = item.get("date", "")
    time_text = item.get("time", "")
    parts: List[str] = []
    if date_text:
        parts.append(date_text)
    if time_text:
        parts.append(time_text)
    location_text = item.get("location")
    if location_text and normalise_location(location_text) != normalise_location(course_location):
        parts.append(location_text)
    status_text = item.get("status")
    if status_text:
        parts.append(status_text)

    core_text = " · ".join(part for part in parts if part)
    return f"- {core_text}" if core_text else ""


def build_times_html(
    summary_lines: Sequence[str],
    detail_items: Sequence[Dict[str, str]],
    heading: Optional[str],
    course_location: str = "",
) -> str:
    if not summary_lines and not detail_items:
        return ""

    soup = BeautifulSoup("", "html.parser")
    container = soup.new_tag("div", attrs={"class": "vhs-times"})

    if summary_lines:
        summary_grid = soup.new_tag("div", attrs={"class": "vhs-times-summary-grid"})
        for line in summary_lines:
            text = prettify_summary_line(line)
            if not text:
                continue
            item = soup.new_tag("div", attrs={"class": "vhs-times-summary-item"})
            item.string = text
            summary_grid.append(item)
        if summary_grid.contents:
            container.append(summary_grid)

    if detail_items:
        heading_label, heading_badge = split_heading_parts(heading)
        heading_tag = soup.new_tag("div", attrs={"class": "vhs-times-heading"})
        label_tag = soup.new_tag("span", attrs={"class": "vhs-times-heading-label"})
        label_tag.string = heading_label
        heading_tag.append(label_tag)
        if heading_badge:
            badge_tag = soup.new_tag("span", attrs={"class": "vhs-times-count"})
            badge_tag.string = heading_badge
            heading_tag.append(badge_tag)
        container.append(heading_tag)

        list_tag = soup.new_tag("ul", attrs={"class": "vhs-times-list"})

        for detail in detail_items:
            list_item = soup.new_tag("li", attrs={"class": "vhs-times-list-item"})

            date_text = detail.get("date")
            if date_text:
                date_tag = soup.new_tag("span", attrs={"class": "vhs-times-date"})
                date_tag.string = date_text
                list_item.append(date_tag)

            time_text = detail.get("time")
            if time_text:
                time_tag = soup.new_tag("span", attrs={"class": "vhs-times-time"})
                time_tag.string = time_text
                list_item.append(time_tag)

            location_text = detail.get("location")
            if location_text and normalise_location(location_text) != normalise_location(course_location):
                location_tag = soup.new_tag("span", attrs={"class": "vhs-times-location"})
                location_tag.string = location_text
                list_item.append(location_tag)

            status_text = detail.get("status")
            if status_text:
                status_classes = ["vhs-times-status"]
                lowered = status_text.lower()
                if "abgesagt" in lowered:
                    status_classes.append("vhs-times-status--cancelled")
                elif "ausgebucht" in lowered or "belegt" in lowered:
                    status_classes.append("vhs-times-status--full")
                status_tag = soup.new_tag("span", attrs={"class": status_classes})
                status_tag.string = status_text
                list_item.append(status_tag)

            if list_item.contents:
                list_tag.append(list_item)

        if list_tag.contents:
            container.append(list_tag)

    return container.decode()


def extract_times(soup: BeautifulSoup, course_location: Optional[str] = None) -> Dict[str, str]:
    table = soup.select_one("table.layoutgrid")
    if not table:
        return {"text": "", "html": ""}

    summary_lines: List[str] = []
    detail_items: List[Dict[str, str]] = []
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
            detail_items.extend(details)
            if candidate_header and not header:
                header = candidate_header

    table.decompose()

    text_sections: List[str] = []
    summary_lines = [prettify_summary_line(line) for line in summary_lines if line]

    if summary_lines:
        text_sections.append("\n".join(summary_lines))
    course_location_value = normalize_whitespace(course_location or "")

    if detail_items:
        detail_lines = [
            line
            for line in (
                build_times_detail_text(item, course_location_value)
                for item in detail_items
            )
            if line
        ]
        if detail_lines:
            heading_label, heading_badge = split_heading_parts(header)
            heading_text = heading_label
            if heading_badge:
                heading_text = f"{heading_text} – {heading_badge}"
            text_sections.append(f"{heading_text}\n" + "\n".join(detail_lines))

    text_value = "\n\n".join(section for section in text_sections if section).strip()
    html_value = build_times_html(summary_lines, detail_items, header, course_location_value)

    return {"text": text_value, "html": html_value}


def extract_description(soup: BeautifulSoup, title: str) -> str:
    clean_description_tree(soup)

    root = soup.body or soup
    blocks = collect_blocks(root, soup)
    blocks = filter_admin_blocks(blocks)
    blocks = truncate_after_stop_keywords(blocks)
    blocks = ensure_title_block(blocks, soup, title)

    return blocks_to_string(blocks)


def process_course(course: dict) -> dict:
    course_copy = dict(course)
    raw_html = course.get("beschreibung") or ""
    course_copy["beschreibung_raw"] = raw_html

    soup = BeautifulSoup(raw_html, "html.parser") if raw_html else BeautifulSoup("", "html.parser")
    times_payload = extract_times(soup, course.get("ort"))
    description = extract_description(soup, course.get("titel", ""))

    course_copy["beschreibung"] = description
    times_text = times_payload.get("text", "")
    times_html = times_payload.get("html", "")

    if times_text:
        course_copy["zeiten"] = times_text
    else:
        course_copy["zeiten"] = normalize_whitespace(course.get("zeiten", ""))

    if times_html:
        course_copy["zeiten_html"] = times_html
    elif "zeiten_html" in course_copy:
        del course_copy["zeiten_html"]

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
