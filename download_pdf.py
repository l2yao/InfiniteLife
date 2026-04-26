#!/usr/bin/env python3
"""Download PDF files from a range of codes (140102-140502).

Example:
    python download_doc.py --start 1 --end 5 --output pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://www.masterhnz.com/Pdf/14"
FILENAME_TEMPLATE = "14{number:02d}02.pdf"


def download_file(url: str, dest: Path, timeout: int = 30) -> bool:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=timeout) as response, open(dest, "wb") as out_file:
            out_file.write(response.read())
        return True
    except HTTPError as exc:
        print(f"HTTP error {exc.code} for {url}")
    except URLError as exc:
        print(f"URL error for {url}: {exc.reason}")
    except OSError as exc:
        print(f"Failed writing {dest}: {exc}")
    return False


def build_urls(start: int, end: int) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for index in range(start, end + 1):
        filename = FILENAME_TEMPLATE.format(number=index)
        url = f"{BASE_URL}/{filename}"
        urls.append((url, filename))
    return urls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download PDF files for masterhnz.com",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--start", type=int, default=1, help="Starting index (1-5)")
    parser.add_argument("--end", type=int, default=5, help="Ending index (1-5)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("downloads"),
        help="Output directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.start < 1 or args.end < args.start:
        print("Error: invalid range.")
        return 1

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    urls = build_urls(args.start, args.end)
    print(f"Downloading {len(urls)} files to {output_dir}")

    success_count = 0
    for url, filename in urls:
        dest = output_dir / filename
        print(f"Downloading {filename}...")
        if download_file(url, dest):
            success_count += 1
        else:
            print(f"Failed: {url}")

    print(f"Finished. {success_count}/{len(urls)} files downloaded.")
    return 0 if success_count == len(urls) else 2


if __name__ == "__main__":
    raise SystemExit(main())
