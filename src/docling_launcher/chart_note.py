"""A warning under every table the chart model wrote (2026-09-21, the owner's decision).

Docling writes a chart's values as a Markdown table under the picture, headed by the
picture's class in words - "Line chart", "Bar chart", "Pie chart". On the SIA 190 standard
the model read one simple curve roughly right and invented the values of a nomogram and of
a chart with an inverted axis - confident numbers that look like data. Every such table
therefore gets a line saying where its numbers came from; a table that already has it is
left alone, and a real document table (no chart heading above it) is never touched.
"""
from __future__ import annotations

from pathlib import Path

from .constants import CHART_TABLE_NOTE

CHART_HEADINGS = {"line chart", "bar chart", "pie chart", "stacked bar chart", "scatter chart", "chart"}


def mark_chart_tables(markdown: Path) -> int:
    """Puts CHART_TABLE_NOTE under each chart table of the file. Returns how many."""
    try:
        lines = markdown.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    out: list[str] = []
    added = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        out.append(line)
        index += 1
        if line.strip().lower() not in CHART_HEADINGS:
            continue
        # blank lines, then the table
        blanks = []
        while index < len(lines) and not lines[index].strip():
            blanks.append(lines[index])
            index += 1
        if index >= len(lines) or not lines[index].lstrip().startswith("|"):
            out.extend(blanks)
            continue
        out.extend(blanks)
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            out.append(lines[index])
            index += 1
        # already marked?
        look = index
        while look < len(lines) and not lines[look].strip():
            look += 1
        if look < len(lines) and lines[look].strip() == CHART_TABLE_NOTE:
            continue
        out.extend(["", CHART_TABLE_NOTE])
        added += 1
    if added:
        markdown.write_text("\n".join(out) + "\n", encoding="utf-8")
    return added
