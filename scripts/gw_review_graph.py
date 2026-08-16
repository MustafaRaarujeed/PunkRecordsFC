#!/usr/bin/env python3
"""Plot projected vs actual points for a recorded gameweek XI.

Usage:
  python3 scripts/fetch.py --players --force
  python3 scripts/gw_review_graph.py --gw 1

The projection comes from state/log/gw{N}-decision.json, written by
optimise.py. Actual points come from data/element-summary/{player_id}.json
after the gameweek has finished.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
DATA = ROOT / "data"
LOG = STATE / "log"
SUMMARIES = DATA / "element-summary"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gw", type=int, required=True, help="gameweek number")
    parser.add_argument("--decision", type=Path,
                        help="override state/log/gw{N}-decision.json")
    parser.add_argument("--out", type=Path,
                        help="SVG output path; defaults to state/log/gw{N}-review.svg")
    parser.add_argument("--csv", type=Path,
                        help="CSV output path; defaults to state/log/gw{N}-review.csv")
    return parser.parse_args()


def load_decision(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"{path} not found. Run optimise.py first so the XI is recorded.")
    return json.loads(path.read_text())


def actual_points(player_id: int, gw: int) -> int | None:
    path = SUMMARIES / f"{player_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    for row in payload.get("history", []):
        if int(row.get("round") or 0) == gw:
            return int(row.get("total_points") or 0)
    return None


def xi_rows(decision: dict, gw: int) -> list[dict]:
    rows = []
    for player in decision.get("squad", []):
        if not player.get("starter"):
            continue
        projected = float(player.get("xp") or 0.0)
        actual = actual_points(int(player["id"]), gw)
        multiplier = 2 if player.get("captain") else 1
        rows.append({
            "id": int(player["id"]),
            "name": player["name"],
            "team": player["team"],
            "pos": player["pos"],
            "captain": bool(player.get("captain")),
            "projected": round(projected, 3),
            "actual": actual,
            "projected_effective": round(projected * multiplier, 3),
            "actual_effective": None if actual is None else actual * multiplier,
            "delta": None if actual is None else round(actual - projected, 3),
            "delta_effective": None if actual is None else round(actual * multiplier - projected * multiplier, 3),
        })
    order = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}
    rows.sort(key=lambda r: (order.get(r["pos"], 9), -r["projected"]))
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id", "name", "team", "pos", "captain", "projected", "actual",
        "projected_effective", "actual_effective", "delta", "delta_effective",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fmt(value) -> str:
    if value is None:
        return "pending"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def svg(rows: list[dict], decision: dict, gw: int) -> str:
    margin_l = 170
    margin_r = 32
    top = 118
    row_h = 34
    chart_w = 520
    h = top + len(rows) * row_h + 86
    w = margin_l + chart_w + margin_r
    max_value = max(
        [10.0]
        + [r["projected"] for r in rows]
        + [float(r["actual"] or 0) for r in rows]
    )
    max_value = max_value * 1.15
    projected_total = sum(r["projected_effective"] for r in rows)
    actual_values = [r["actual_effective"] for r in rows]
    actual_total = None if any(v is None for v in actual_values) else sum(actual_values)
    objective = decision.get("objective", "")
    subtitle = f"{decision.get('mode', '')} · objective {objective} · captain doubled in totals"
    if objective != "xp_next":
        subtitle += " · warning: projection may be multi-GW, not single-GW"

    def x(value: float) -> float:
        return margin_l + value / max_value * chart_w

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>'
        'text{font-family:Aptos,Arial,sans-serif;fill:#17202a}'
        '.muted{fill:#5f6b7a}.small{font-size:12px}.label{font-size:13px}'
        '.title{font-size:22px;font-weight:700}.total{font-size:15px;font-weight:700}'
        '</style>',
        f'<text class="title" x="24" y="34">GW{gw} projected vs actual XI points</text>',
        f'<text class="muted small" x="24" y="58">{escape(subtitle)}</text>',
        f'<text class="total" x="24" y="86">Projected XI: {projected_total:.1f}</text>',
        f'<text class="total" x="210" y="86">Actual XI: {fmt(actual_total)}</text>',
        '<rect x="24" y="96" width="14" height="10" fill="#4464ad"/>',
        '<text class="small muted" x="44" y="105">Projected</text>',
        '<rect x="130" y="96" width="14" height="10" fill="#42a87a"/>',
        '<text class="small muted" x="150" y="105">Actual</text>',
    ]

    for tick in range(0, int(max_value) + 1, 2):
        xpos = x(tick)
        parts.append(f'<line x1="{xpos:.1f}" y1="{top - 14}" x2="{xpos:.1f}" y2="{h - 52}" stroke="#eef1f5"/>')
        parts.append(f'<text class="small muted" x="{xpos - 4:.1f}" y="{top - 22}">{tick}</text>')

    for idx, row in enumerate(rows):
        y = top + idx * row_h
        label = f"{row['name']} ({row['pos']})" + (" C" if row["captain"] else "")
        parts.append(f'<text class="label" x="24" y="{y + 17}">{escape(label)}</text>')
        parts.append(f'<rect x="{margin_l}" y="{y + 4}" width="{max(1, x(row["projected"]) - margin_l):.1f}" height="10" rx="2" fill="#4464ad"/>')
        if row["actual"] is not None:
            parts.append(f'<rect x="{margin_l}" y="{y + 18}" width="{max(1, x(float(row["actual"])) - margin_l):.1f}" height="10" rx="2" fill="#42a87a"/>')
        else:
            parts.append(f'<text class="small muted" x="{margin_l}" y="{y + 28}">actual pending</text>')
        parts.append(f'<text class="small muted" x="{margin_l + chart_w + 8}" y="{y + 13}">{row["projected"]:.1f}</text>')
        parts.append(f'<text class="small muted" x="{margin_l + chart_w + 8}" y="{y + 27}">{fmt(row["actual"])}</text>')

    parts.append(f'<text class="small muted" x="24" y="{h - 24}">Source: state/log/gw{gw}-decision.json + data/element-summary/*.json</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    args = parse_args()
    decision_path = args.decision or LOG / f"gw{args.gw}-decision.json"
    svg_path = args.out or LOG / f"gw{args.gw}-review.svg"
    csv_path = args.csv or LOG / f"gw{args.gw}-review.csv"

    decision = load_decision(decision_path)
    rows = xi_rows(decision, args.gw)
    if len(rows) != 11:
        raise SystemExit(f"expected 11 starters in {decision_path}, found {len(rows)}")

    write_csv(csv_path, rows)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg(rows, decision, args.gw))
    missing = sum(1 for row in rows if row["actual"] is None)
    print(f"wrote {svg_path}")
    print(f"wrote {csv_path}")
    if missing:
        print(f"actual points pending for {missing} starter(s); refresh with: python3 scripts/fetch.py --players --force")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
