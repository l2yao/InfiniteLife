#!/usr/bin/env python3
"""Download MP3 files from masterhnz.com with sequential sub-indices.

Example:
    python download_mp3.py --start 1 --end 5 --output mp3
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://www.masterhnz.com/Video"


def download_file(url: str, dest: Path, timeout: int = 30) -> bool:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return False
            
            # Check content type to avoid downloading HTML pages
            content_type = response.headers.get("Content-Type", "")
            if "audio/mpeg" not in content_type:
                print(f"\nSkipping {url} (Content-Type: {content_type})")
                return False

            with open(dest, "wb") as out_file:
                out_file.write(response.read())
        return True
    except HTTPError as exc:
        # File not found
        return False
    except (URLError, OSError) as exc:
        print(f"\nError downloading {url}: {exc}")
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download MP3 files from masterhnz.com")
    parser.add_argument("--start", type=int, default=1, help="Starting index (e.g., 1 for 1401)")
    parser.add_argument("--end", type=int, default=5, help="Ending index (e.g., 5 for 1405)")
    parser.add_argument("--output", type=Path, default=Path("downloads"), help="Output directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    for i in range(args.start, args.end + 1):
        base_code = f"14{i:02d}"
        print(f"--- Processing base: {base_code} ---")
        
        for sub_idx in range(1, 1000):
            filename = f"{base_code}{sub_idx:03d}.mp3"
            url = f"{BASE_URL}/{filename}"
            dest = output_dir / filename
            
            if dest.exists():
                print(f"Skipping existing {filename}", end="\r")
                continue

            print(f"Attempting {filename}...", end="\r")
            if download_file(url, dest):
                print(f"Downloaded {filename}")
            else:
                # 404 or other failure
                print(f"\nStopped at {filename} (not found or error)")
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
