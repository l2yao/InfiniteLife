#!/usr/bin/env python3
"""Convert Microsoft Word .doc files to plain text (.txt).

This script supports several fallback methods:
- win32com automation on Windows with Word installed
- antiword
- wvText
- LibreOffice / soffice
- textract Python library

Example:
    python doc_to_txt.py input.doc
    python doc_to_txt.py --input folder_with_docs --recursive
    python doc_to_txt.py --input file.doc --output file.txt
    python doc_to_txt.py --start 1 --end 22 --output converted_texts
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from pathlib import Path
except ImportError:
    pass

FILENAME_TEMPLATE = "14-004-{number:04d}{suffix}.doc"
SUFFIXES = ["a", "b"]
FILTER_ONLY_INDENTED = True


def run_command(command: list[str]) -> tuple[bool, str, str]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0, proc.stdout, proc.stderr
    except FileNotFoundError:
        return False, "", f"Command not found: {command[0]}"


def normalize_extracted_text(text: str) -> str:
    lines = text.splitlines()
    filtered = [line.rstrip() for line in lines if line.startswith((" ", "\t"))]
    return "\n".join(filtered) + ("\n" if filtered else "")


def write_text_with_filter(dst: Path, text: str) -> None:
    if FILTER_ONLY_INDENTED:
        text = normalize_extracted_text(text)
    dst.write_text(text, encoding="utf-8", errors="ignore")


def convert_with_antiword(src: Path, dst: Path) -> bool:
    ok, out, err = run_command(["antiword", str(src)])
    if not ok:
        print(f"antiword failed: {err.strip()}")
        return False
    write_text_with_filter(dst, out)
    return True


def convert_with_wvtext(src: Path, dst: Path) -> bool:
    ok, out, err = run_command(["wvText", str(src), str(dst)])
    if not ok:
        print(f"wvText failed: {err.strip()}")
        return False
    try:
        text = dst.read_text(encoding="utf-8", errors="ignore")
        write_text_with_filter(dst, text)
    except Exception:
        pass
    return True


def convert_with_libreoffice(src: Path, dst: Path) -> bool:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return False
    outdir = dst.parent
    ok, out, err = run_command([
        soffice,
        "--headless",
        "--convert-to",
        "txt:Text",
        "--outdir",
        str(outdir),
        str(src),
    ])
    if not ok:
        print(f"LibreOffice conversion failed: {err.strip()}")
        return False
    generated = outdir / f"{src.stem}.txt"
    if not generated.exists():
        print(f"LibreOffice did not create expected file: {generated}")
        return False
    try:
        text = generated.read_text(encoding="utf-8", errors="ignore")
        write_text_with_filter(dst, text)
    finally:
        generated.unlink(missing_ok=True)
    return True


def convert_with_textract(src: Path, dst: Path) -> bool:
    try:
        import textract
    except ImportError:
        return False
    try:
        raw = textract.process(str(src))
    except Exception as exc:
        print(f"textract failed: {exc}")
        return False
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="ignore")
    else:
        text = str(raw)
    write_text_with_filter(dst, text)
    return True


def _normalize_win32com_text_file(src: Path, dst: Path) -> bool:
    data = src.read_bytes()
    if data.startswith(b"\xff\xfe"):
        text = data.decode("utf-16-le", errors="replace")
    elif data.startswith(b"\xfe\xff"):
        text = data.decode("utf-16-be", errors="replace")
    else:
        for enc in ("utf-8", "cp950", "cp936", "big5", "latin1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = data.decode("utf-8", errors="replace")
    write_text_with_filter(dst, text)
    return True


def convert_with_win32com(src: Path, dst: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return False
    temp_dst = dst.parent / f"{dst.stem}.tmp.txt"
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(src))
        wdFormatUnicodeText = 7
        doc.SaveAs2(str(temp_dst), FileFormat=wdFormatUnicodeText)
        doc.Close(False)
        word.Quit()
        if not _normalize_win32com_text_file(temp_dst, dst):
            return False
        temp_dst.unlink(missing_ok=True)
        return True
    except Exception as exc:
        print(f"win32com conversion failed: {exc}")
        if temp_dst.exists():
            temp_dst.unlink(missing_ok=True)
        return False


def available_methods() -> dict[str, callable]:
    return {
        "win32com": convert_with_win32com,
        "antiword": convert_with_antiword,
        "wvText": convert_with_wvtext,
        "libreoffice": convert_with_libreoffice,
        "textract": convert_with_textract,
    }


def choose_method(preferred: str | None = None) -> str | None:
    methods = available_methods()
    if preferred:
        if preferred not in methods:
            print(f"Unknown method: {preferred}")
            return None
        return preferred
    for name, converter in methods.items():
        if name == "win32com":
            if sys.platform == "win32" and _has_win32com():
                return name
            continue
        if name in {"antiword", "wvText", "libreoffice"} and shutil.which(name):
            return name
        if name == "textract" and _has_textract():
            return name
    return None


def _has_win32com() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
        return True
    except ImportError:
        return False


def _has_textract() -> bool:
    try:
        import textract  # type: ignore
        return True
    except ImportError:
        return False


def convert_file(src: Path, dst: Path, method: str | None = None) -> bool:
    if src.suffix.lower() != ".doc":
        print(f"Skipping non-.doc file: {src}")
        return False
    if not dst.parent.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
    if method:
        if method not in available_methods():
            print(f"Unknown conversion method: {method}")
            return False
        return available_methods()[method](src, dst)

    for name, converter in available_methods().items():
        if name == "win32com" and sys.platform != "win32":
            continue
        if name in {"antiword", "wvText", "libreoffice"} and not shutil.which(name):
            continue
        if name == "textract" and not _has_textract():
            continue
        if converter(src, dst):
            return True
    print("No available conversion method succeeded.")
    return False


def build_range_paths(start: int, end: int, input_dir: Path, suffixes: list[str], use_suffixes: bool) -> list[tuple[Path, Path]]:
    paths: list[tuple[Path, Path]] = []
    for index in range(start, end + 1):
        if use_suffixes:
            for suffix in suffixes:
                filename = FILENAME_TEMPLATE.format(number=index, suffix=suffix)
                src = input_dir / filename
                dst = src.with_suffix(".txt")
                paths.append((src, dst))
        else:
            filename = FILENAME_TEMPLATE.format(number=index, suffix="")
            src = input_dir / filename
            dst = src.with_suffix(".txt")
            paths.append((src, dst))
    return paths


def process_path(input_path: Path, output_path: Path, recursive: bool, method: str | None, skip_existing: bool, force: bool) -> int:
    if input_path.is_file():
        if output_path.is_dir():
            output_file = output_path / f"{input_path.stem}.txt"
        else:
            output_file = output_path
        if output_file.exists() and not force:
            if skip_existing:
                print(f"Skipping existing file: {output_file}")
                return 0
            print(f"Skipped existing file: {output_file} (use --force to overwrite)")
            return 0
        return 0 if convert_file(input_path, output_file, method) else 1

    if not input_path.is_dir():
        print(f"Input path not found: {input_path}")
        return 1

    errors = 0
    for root, _, files in os.walk(input_path):
        for name in files:
            if not name.lower().endswith(".doc"):
                continue
            src = Path(root) / name
            rel = src.relative_to(input_path)
            dst = output_path / rel.with_suffix(".txt") if output_path.is_dir() else Path(output_path)
            if dst.exists() and not force:
                if skip_existing:
                    print(f"Skipping existing file: {dst}")
                    continue
                print(f"Skipped existing file: {dst} (use --force to overwrite)")
                continue
            print(f"Converting: {src} -> {dst}")
            if not convert_file(src, dst, method):
                errors += 1
        if not recursive:
            break
    return errors


def process_range(input_path: Path, output_path: Path, start: int, end: int, method: str | None, skip_existing: bool, force: bool, use_suffixes: bool) -> int:
    if output_path.exists() and not output_path.is_dir():
        print(f"Output path must be a directory when converting a range: {output_path}")
        return 1

    output_path.mkdir(parents=True, exist_ok=True)
    errors = 0
    paths = build_range_paths(start, end, input_path, SUFFIXES, use_suffixes)
    for src, dst in paths:
        dst = output_path / dst.name
        if not src.exists():
            print(f"Source not found: {src}")
            errors += 1
            continue
        if dst.exists() and not force:
            if skip_existing:
                print(f"Skipping existing file: {dst}")
                continue
            print(f"Skipped existing file: {dst} (use --force to overwrite)")
            continue
        print(f"Converting: {src} -> {dst}")
        if not convert_file(src, dst, method):
            errors += 1
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert .doc files to .txt",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", "-i", type=Path, default=Path("."), help="Input .doc file or directory")
    parser.add_argument("--output", "-o", type=Path, default=Path("output"), help="Output file or directory")
    parser.add_argument("--recursive", "-r", action="store_true", help="Recursively convert all .doc files in a directory")
    parser.add_argument("--start", type=int, help="Starting numeric index for range conversion")
    parser.add_argument("--end", type=int, help="Ending numeric index for range conversion")
    parser.add_argument("--method", "-m", choices=list(available_methods().keys()), help="Conversion method to use")
    parser.add_argument("--skip-existing", action="store_true", help="Skip files that already exist locally")
    parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing output files")
    parser.add_argument("--no-filter", action="store_true", help="Do not filter output to indented lines only")
    parser.add_argument(
        "--no-suffix",
        action="store_true",
        help="Use files without a/b suffixes (e.g., 14-004-0010.doc)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.start is not None or args.end is not None:
        if args.start is None or args.end is None:
            print("Error: both --start and --end are required for range conversion.")
            return 1
        if args.start < 1 or args.end < args.start:
            print("Error: invalid range. Ensure 1 <= start <= end.")
            return 1

    global FILTER_ONLY_INDENTED
    FILTER_ONLY_INDENTED = not args.no_filter

    method = args.method or choose_method()
    if method is None:
        print("No conversion method is available. Install antiword, wvText, LibreOffice, textract, or use pywin32+Word on Windows.")
        return 1

    if FILTER_ONLY_INDENTED:
        print(f"Using conversion method: {method} (filtering to indented lines only)")
    else:
        print(f"Using conversion method: {method} (no filtering)")
    if args.start is not None and args.end is not None:
        return process_range(args.input, args.output, args.start, args.end, method, args.skip_existing, args.force, not args.no_suffix)
    return process_path(args.input, args.output, args.recursive, method, args.skip_existing, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
