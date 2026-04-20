#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


def load_manifest(manifest_path: Path) -> dict[str, dict[str, str | None]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_date: dict[str, dict[str, str | None]] = {}
    for item in payload.get("items", []):
        date = item.get("date")
        if date:
            by_date[str(date)] = {
                "saved_as": item.get("saved_as"),
                "status": item.get("status"),
            }
    return by_date


def daterange(start: dt.date, end: dt.date) -> list[dt.date]:
    days: list[dt.date] = []
    current = start
    while current <= end:
        days.append(current)
        current += dt.timedelta(days=1)
    return days


def render_card(
    school_name: str,
    image_dir: Path,
    item: dict[str, str | None] | None,
    date_str: str,
) -> str:
    if not item or not item.get("saved_as"):
        return (
            f"<div class='photo-box missing'>"
            f"<div class='school'>{school_name}</div>"
            f"<div class='missing-text'>이미지 없음</div>"
            f"</div>"
        )
    image_rel = f"{image_dir.name}/{item['saved_as']}"
    return (
        f"<a class='photo-box' href='{image_rel}' target='_blank' rel='noopener'>"
        f"<div class='school'>{school_name}</div>"
        f"<img loading='lazy' src='{image_rel}' alt='{school_name} {date_str} 급식사진' />"
        f"</a>"
    )


def build_html(
    soongshin_manifest: Path,
    muhag_manifest: Path,
    out_html: Path,
    start_date: dt.date,
    end_date: dt.date,
) -> None:
    soongshin_map = load_manifest(soongshin_manifest)
    muhag_map = load_manifest(muhag_manifest)

    soongshin_dir = soongshin_manifest.parent
    muhag_dir = muhag_manifest.parent

    rows: list[str] = []
    for d in daterange(start_date, end_date):
        date_str = d.isoformat()
        weekday = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
        weekend_class = " weekend" if d.weekday() >= 5 else ""
        soongshin_item = soongshin_map.get(date_str)
        muhag_item = muhag_map.get(date_str)

        # Skip days with no meal image for both schools (weekends/holidays/no-service days).
        if not (soongshin_item and soongshin_item.get("saved_as")) and not (
            muhag_item and muhag_item.get("saved_as")
        ):
            continue

        soongshin_card = render_card(
            "서울숭신초등학교", soongshin_dir, soongshin_item, date_str
        )
        muhag_card = render_card(
            "서울무학초등학교", muhag_dir, muhag_item, date_str
        )
        rows.append(
            f"<section class='day-row{weekend_class}'>"
            f"<h2>{date_str} ({weekday})</h2>"
            f"<div class='compare-grid'>{soongshin_card}{muhag_card}</div>"
            f"</section>"
        )

    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>2026년 3~4월 급식사진 비교 - 숭신초 vs 무학초</title>
  <style>
    :root {{
      --bg: #f4f6fb;
      --card: #ffffff;
      --line: #d6dbe8;
      --text: #1f2937;
      --muted: #637086;
      --accent: #0f766e;
      --weekend: #fff7ed;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #eef6ff 0%, var(--bg) 30%);
      color: var(--text);
      font-family: "Pretendard", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
    }}
    .wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 28px;
      line-height: 1.2;
    }}
    .summary {{
      margin: 0 0 22px;
      color: var(--muted);
      font-size: 14px;
    }}
    .day-row {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 14px;
    }}
    .day-row.weekend {{
      background: var(--weekend);
    }}
    .day-row h2 {{
      margin: 0 0 10px;
      font-size: 17px;
    }}
    .compare-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .photo-box {{
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: hidden;
      background: #fff;
      text-decoration: none;
      color: inherit;
      display: flex;
      flex-direction: column;
      min-height: 250px;
    }}
    .photo-box img {{
      width: 100%;
      height: 320px;
      object-fit: contain;
      object-position: center;
      display: block;
      background: #f0f3f8;
    }}
    .school {{
      padding: 8px 10px;
      font-weight: 700;
      font-size: 14px;
      border-bottom: 1px solid var(--line);
      background: #f8fafc;
    }}
    .photo-box.missing {{
      justify-content: center;
      align-items: center;
      color: var(--muted);
      min-height: 250px;
    }}
    .photo-box.missing .school {{
      width: 100%;
      text-align: left;
    }}
    .missing-text {{
      margin-top: 10px;
      font-size: 14px;
      font-weight: 700;
      color: #9aa4b6;
    }}
    @media (max-width: 860px) {{
      .compare-grid {{ grid-template-columns: 1fr; }}
      .photo-box img {{ height: 280px; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <h1>서울숭신초등학교 vs 서울무학초등학교</h1>
    <p class="summary">2026-03-01 ~ 2026-04-30 날짜별 급식사진 비교 (클릭 시 원본 열기)</p>
    {"".join(rows)}
  </main>
</body>
</html>
"""
    out_html.write_text(html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build day-by-day comparison HTML.")
    parser.add_argument(
        "--soongshin-manifest",
        default="soongshin_meal_images_2026_03_04/manifest.json",
    )
    parser.add_argument(
        "--muhag-manifest",
        default="muhag_meal_images_2026_03_04/manifest.json",
    )
    parser.add_argument(
        "--out-html",
        default="meal_compare_soongshin_vs_muhag_2026_03_04.html",
    )
    parser.add_argument("--start-date", default="2026-03-01")
    parser.add_argument("--end-date", default="2026-04-30")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_html(
        soongshin_manifest=Path(args.soongshin_manifest).resolve(),
        muhag_manifest=Path(args.muhag_manifest).resolve(),
        out_html=Path(args.out_html).resolve(),
        start_date=dt.date.fromisoformat(args.start_date),
        end_date=dt.date.fromisoformat(args.end_date),
    )
    print(f"[html] {Path(args.out_html).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
