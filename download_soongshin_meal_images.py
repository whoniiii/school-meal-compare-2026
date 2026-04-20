#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import zipfile
from collections import Counter
from pathlib import Path


BASE_URL = "https://soongshin.sen.es.kr"
MENU_PATH = "/88534/subMenu.do"
DETAIL_PATH = "/dggb/module/mlsv/selectMlsvDetailPopup.do"
IMAGE_PATH = "/dggb/module/file/selectImageView.do"
SITE_ID = "SEI_00001847"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def decode_html(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class Client:
    def __init__(self) -> None:
        self.cookie_path = Path(tempfile.gettempdir()) / f"soongshin_cookies_{os.getpid()}.txt"
        self.default_headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def request(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        referer: str | None = None,
        binary: bool = False,
        retries: int = 3,
    ) -> bytes | str:
        command = [
            "curl",
            "-fsSL",
            "--http1.1",
            "--connect-timeout",
            "20",
            "--max-time",
            "60",
            "--retry",
            str(retries),
            "--retry-delay",
            "1",
            "--cookie",
            str(self.cookie_path),
            "--cookie-jar",
            str(self.cookie_path),
            "-A",
            self.default_headers["User-Agent"],
            "-H",
            f"Accept-Language: {self.default_headers['Accept-Language']}",
        ]
        if referer:
            command.extend(["-e", referer])
        if data is not None:
            command.extend(["--data", urllib.parse.urlencode(data)])
        command.append(url)

        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"request failed for {url}: {stderr}")
        return completed.stdout if binary else decode_html(completed.stdout)


def fetch_month_ids(
    client: Client,
    base_url: str,
    menu_path: str,
    site_id: str,
    year: int,
    month: int,
) -> list[str]:
    url = urllib.parse.urljoin(base_url, menu_path)
    page = client.request(
        url,
        data={
            "viewType": "calendar",
            "siteId": site_id,
            "arrMlsvId": "0",
            "srhMlsvYear": str(year),
            "srhMlsvMonth": f"{month:02d}",
        },
        referer=url,
    )
    ids = re.findall(r"fnDetail\('(\d+)'\s*,\s*this\)", page)
    return list(dict.fromkeys(ids))


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def extract_detail(detail_html: str, base_url: str) -> dict[str, str | None]:
    date_match = re.search(r"(\d{4})년\s*(\d{2})월\s*(\d{2})일", detail_html)
    if not date_match:
        raise RuntimeError("detail page did not include a registration date")

    meal_match = re.search(
        r"<th[^>]*>\s*급식\s*</th>\s*<td[^>]*>(.*?)</td>", detail_html, re.S
    )
    meal = clean_text(meal_match.group(1)) if meal_match else ""

    image_match = re.search(
        r"atchFileId=(\d+)&fileSn=(\d+)",
        detail_html,
    )
    image_url = None
    if image_match:
        atch_file_id, file_sn = image_match.groups()
        image_url = f"{base_url}{IMAGE_PATH}?atchFileId={atch_file_id}&fileSn={file_sn}"

    return {
        "date": f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}",
        "meal": meal,
        "image_url": image_url,
    }


def guess_extension(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if image_bytes.startswith(b"BM"):
        return ".bmp"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def download_images(
    output_dir: Path,
    months: list[tuple[int, int]],
    *,
    base_url: str,
    menu_path: str,
    site_id: str,
    school_name: str,
) -> tuple[Path, list[dict[str, str | None]]]:
    client = Client()
    manifest: list[dict[str, str | None]] = []
    name_counts: Counter[str] = Counter()

    detail_url = urllib.parse.urljoin(base_url, DETAIL_PATH)
    menu_url = urllib.parse.urljoin(base_url, menu_path)

    for year, month in months:
        ids = fetch_month_ids(client, base_url, menu_path, site_id, year, month)
        if not ids:
            print(f"[warn] no meal ids found for {year}-{month:02d}", file=sys.stderr)

        for meal_id in ids:
            detail_html = client.request(
                detail_url,
                data={"mlsvId": meal_id},
                referer=menu_url,
            )
            detail = extract_detail(detail_html, base_url)
            record: dict[str, str | None] = {
                "mlsv_id": meal_id,
                "date": detail["date"],
                "meal": detail["meal"],
                "image_url": detail["image_url"],
                "saved_as": None,
            }

            image_url = detail["image_url"]
            if not image_url:
                record["status"] = "missing_image"
                manifest.append(record)
                continue

            image_bytes = client.request(
                image_url,
                referer=detail_url,
                binary=True,
            )
            extension = guess_extension(image_bytes)
            stem = str(detail["date"])
            name_counts[stem] += 1
            if name_counts[stem] > 1:
                stem = f"{stem}_{name_counts[stem]}"
            filename = f"{stem}{extension}"
            destination = output_dir / filename
            destination.write_bytes(image_bytes)

            record["saved_as"] = filename
            record["status"] = "downloaded"
            manifest.append(record)
            print(f"[saved] {filename}")

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "school": school_name,
                "source_page": urllib.parse.urljoin(base_url, menu_path),
                "months": [f"{year}-{month:02d}" for year, month in months],
                "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "items": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    zip_path = output_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.iterdir()):
            archive.write(path, arcname=path.name)

    return zip_path, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Seoul Soongshin Elementary School meal images by month."
    )
    parser.add_argument(
        "--output-dir",
        default="soongshin_meal_images_2026_03_04",
        help="Directory to store the downloaded images.",
    )
    parser.add_argument("--base-url", default=BASE_URL, help="School base URL.")
    parser.add_argument("--menu-path", default=MENU_PATH, help="Meal subMenu path.")
    parser.add_argument("--site-id", default=SITE_ID, help="siteId form value.")
    parser.add_argument(
        "--school-name",
        default="서울숭신초등학교",
        help="School name written to manifest.",
    )
    parser.add_argument("--year", type=int, default=2026, help="Target year.")
    parser.add_argument(
        "--months",
        default="3,4",
        help="Comma-separated month numbers (e.g. 3,4).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    month_values = [int(m.strip()) for m in args.months.split(",") if m.strip()]
    months = [(args.year, month) for month in month_values]
    zip_path, manifest = download_images(
        output_dir,
        months,
        base_url=args.base_url.rstrip("/"),
        menu_path=args.menu_path,
        site_id=args.site_id,
        school_name=args.school_name,
    )

    downloaded = sum(1 for item in manifest if item.get("status") == "downloaded")
    missing = sum(1 for item in manifest if item.get("status") == "missing_image")

    print(f"[done] downloaded={downloaded} missing_image={missing}")
    print(f"[dir] {output_dir}")
    print(f"[zip] {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
