#!/usr/bin/env python3
"""Export projection outputs to a human-readable Excel workbook.

The Python model remains the source of truth. This script only packages
data/projections.csv and data/projections.json into worksheets for inspection.
It deliberately uses only the standard library so the export path does not add
another required dependency to the weekly routine.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CORE_COLS = [
    "id", "name", "team", "pos", "price", "status", "no_history", "avail",
    "p_start", "xmins", "fixtures", "xp_next", "xp_horizon", "xp_per_m",
    "ppg_horizon", "xp_edge", "selected_by", "source", "news",
]
COMPONENT_COLS = [
    "id", "name", "team", "pos", "price", "xp_horizon",
    "xp_appearance", "xp_goals", "xp_assists", "xp_clean_sheet",
    "xp_concede_penalty", "xp_saves", "xp_defcon", "xp_bonus", "xp_cards",
    "xp_observed", "xp_structural", "xp_component_sum",
]
FLAG_COLS = [
    "id", "name", "team", "pos", "price", "status", "no_history", "stale",
    "new_club", "assumed", "avail", "p_start", "xmins", "xp_horizon",
    "xp_edge", "source", "news",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create data/projections.xlsx from projections.csv/json.")
    parser.add_argument("--csv", type=Path, default=DATA / "projections.csv",
                        help="flat projection CSV written by project.py")
    parser.add_argument("--json", type=Path, default=DATA / "projections.json",
                        help="rich projection JSON written by project.py")
    parser.add_argument("-o", "--output", type=Path, default=DATA / "projections.xlsx",
                        help="xlsx path to write")
    parser.add_argument("--top", type=int, default=40,
                        help="rows per position on the Top By Position sheet")
    return parser.parse_args()


def load_csv(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def number(value):
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?(\d+\.\d*|\d*\.\d+)", text):
        return float(text)
    return value


def price(value):
    value = number(value)
    if isinstance(value, (int, float)):
        return value / 10
    return value


def col_name(index: int) -> str:
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def sheet_ref(row: int, col: int) -> str:
    return f"{col_name(col)}{row}"


def cell_xml(row: int, col: int, value, style: int = 0) -> str:
    ref = sheet_ref(row, col)
    style_attr = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style_attr}><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{escape(str(value))}</t></is></c>'


def row_xml(row_num: int, values: list, styles: list[int] | None = None) -> str:
    cells = []
    styles = styles or []
    for idx, value in enumerate(values, start=1):
        style = styles[idx - 1] if idx <= len(styles) else 0
        cells.append(cell_xml(row_num, idx, value, style))
    return f'<row r="{row_num}">{"".join(cells)}</row>'


def dimension(rows: list[list]) -> str:
    if not rows:
        return "A1"
    return f"A1:{sheet_ref(len(rows), max(len(r) for r in rows) or 1)}"


def widths_xml(widths: list[float]) -> str:
    cols = []
    for idx, width in enumerate(widths, start=1):
        cols.append(
            f'<col min="{idx}" max="{idx}" width="{width:.1f}" customWidth="1"/>')
    return f"<cols>{''.join(cols)}</cols>" if cols else ""


def sheet_xml(rows: list[list], *, widths: list[float] | None = None,
              freeze_header: bool = True, autofilter: bool = True) -> str:
    rows_xml = []
    for row_num, row in enumerate(rows, start=1):
        style = [1] * len(row) if row_num == 1 else []
        rows_xml.append(row_xml(row_num, row, style))
    views = ""
    if freeze_header and len(rows) > 1:
        views = (
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
        )
    auto = f'<autoFilter ref="{dimension(rows)}"/>' if autofilter and len(rows) > 1 else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{views}{widths_xml(widths or [])}<sheetData>{''.join(rows_xml)}</sheetData>{auto}"
        "</worksheet>"
    )


def workbook_xml(sheet_names: list[str]) -> str:
    sheets = []
    for idx, name in enumerate(sheet_names, start=1):
        sheets.append(
            f'<sheet name="{escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(sheets)}</sheets></workbook>"
    )


def workbook_rels_xml(sheet_count: int) -> str:
    rels = []
    for idx in range(1, sheet_count + 1):
        rels.append(
            f'<Relationship Id="rId{idx}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>')
    rels.append(
        f'<Relationship Id="rId{sheet_count + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(rels)}</Relationships>"
    )


def root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )


def styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Aptos"/></font>'
        '<font><b/><sz val="11"/><name val="Aptos"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def content_types_xml(sheet_count: int) -> str:
    overrides = [
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for idx in range(1, sheet_count + 1):
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{''.join(overrides)}</Types>"
    )


def select_columns(rows: list[dict], columns: list[str]) -> list[list]:
    out = [columns]
    for row in rows:
        out.append([price(row[col]) if col == "price" else number(row.get(col, "")) for col in columns])
    return out


def summary_rows(payload: dict, rows: list[dict], csv_path: Path, json_path: Path) -> list[list]:
    meta = payload.get("meta", {})
    counts = {
        "no_history": sum(int(number(r.get("no_history", 0))) for r in rows),
        "stale": sum(int(number(r.get("stale", 0))) for r in rows),
        "new_club": sum(int(number(r.get("new_club", 0))) for r in rows),
        "assumed": sum(int(number(r.get("assumed", 0))) for r in rows),
    }
    return [
        ["Metric", "Value"],
        ["Generated UTC", datetime.now(timezone.utc).replace(microsecond=0).isoformat()],
        ["Gameweeks", ", ".join(str(gw) for gw in meta.get("gameweeks", []))],
        ["Strength source", meta.get("strength_source", "")],
        ["Odds coverage", f"{meta.get('odds_fixtures', 0)}/{meta.get('total_fixtures', 0)} fixtures"],
        ["Players", meta.get("players", len(rows))],
        ["Missing summaries", meta.get("missing_summaries", "")],
        ["No-history players", counts["no_history"]],
        ["Stale-history players", counts["stale"]],
        ["New-club players", counts["new_club"]],
        ["Assumed players", counts["assumed"]],
        ["CSV source", str(csv_path)],
        ["JSON source", str(json_path)],
    ]


def gameweek_rows(payload: dict) -> list[list]:
    players = payload.get("players", [])
    gameweeks = [str(gw) for gw in payload.get("meta", {}).get("gameweeks", [])]
    header = ["id", "name", "team", "pos", "price", *[f"GW{gw}" for gw in gameweeks], "xp_horizon"]
    rows = [header]
    for player in players:
        per_gw = player.get("per_gw", {})
        rows.append([
            player.get("id"), player.get("name"), player.get("team"), player.get("pos"),
            price(player.get("price")),
            *[number(per_gw.get(gw, "")) for gw in gameweeks],
            number(player.get("xp_horizon", "")),
        ])
    return rows


def top_by_position_rows(rows: list[dict], limit: int) -> list[list]:
    out = [["pos", "rank", "id", "name", "team", "price", "xp_horizon", "xp_next", "xp_edge", "selected_by"]]
    for pos in ("GKP", "DEF", "MID", "FWD"):
        ranked = sorted(
            (r for r in rows if r.get("pos") == pos),
            key=lambda r: number(r.get("xp_horizon", 0)),
            reverse=True,
        )
        for rank, row in enumerate(ranked[:limit], start=1):
            out.append([
                pos, rank, number(row.get("id")), row.get("name"), row.get("team"),
                price(row.get("price")), number(row.get("xp_horizon")),
                number(row.get("xp_next")), number(row.get("xp_edge")),
                number(row.get("selected_by")),
            ])
    return out


def write_xlsx(path: Path, sheets: list[tuple[str, list[list], list[float]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml(len(sheets)))
        archive.writestr("_rels/.rels", root_rels_xml())
        archive.writestr("xl/workbook.xml", workbook_xml([name for name, _, _ in sheets]))
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml(len(sheets)))
        archive.writestr("xl/styles.xml", styles_xml())
        for idx, (_, rows, widths) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{idx}.xml", sheet_xml(rows, widths=widths))


def main() -> int:
    args = parse_args()
    if not args.csv.exists():
        raise SystemExit(f"{args.csv} not found. Run: python3 scripts/project.py --horizon 6")
    if not args.json.exists():
        raise SystemExit(f"{args.json} not found. Run: python3 scripts/project.py --horizon 6")

    rows = load_csv(args.csv)
    payload = load_json(args.json)
    flagged = [
        row for row in rows
        if any(int(number(row.get(col, 0))) for col in ("no_history", "stale", "new_club", "assumed"))
        or row.get("status") not in ("", "a")
    ]

    sheets = [
        ("Summary", summary_rows(payload, rows, args.csv, args.json), [22, 90]),
        ("Players", select_columns(rows, CORE_COLS), [8, 18, 8, 8, 8, 8, 12, 8, 9, 8, 8, 9, 11, 9, 12, 9, 11, 18, 60]),
        ("Components", select_columns(rows, COMPONENT_COLS), [8, 18, 8, 8, 8, 11, 13, 10, 10, 14, 17, 9, 10, 10, 9, 11, 12, 16]),
        ("Gameweeks", gameweek_rows(payload), [8, 18, 8, 8, 8, *([9] * len(payload.get("meta", {}).get("gameweeks", []))), 11]),
        ("Flags", select_columns(flagged, FLAG_COLS), [8, 18, 8, 8, 8, 8, 12, 8, 9, 9, 8, 9, 8, 11, 9, 18, 60]),
        ("Top By Position", top_by_position_rows(rows, args.top), [8, 8, 8, 18, 8, 8, 11, 9, 9, 11]),
    ]
    write_xlsx(args.output, sheets)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
