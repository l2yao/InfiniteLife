#!/usr/bin/env python3
"""Convert PDF files to plain text (.txt), attempting to remove page numbers."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import pypdf

def clean_text(text: str) -> str:
    # Remove lines that are just a single number (common page number pattern)
    # Also attempt to remove headers/footers that might be just numbers
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # If line is empty or just a number, skip it
        if not stripped or re.fullmatch(r'\d+', stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)

def convert_pdf_to_txt(src: Path, dst: Path) -> bool:
    try:
        reader = pypdf.PdfReader(src)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        cleaned_text = clean_text(text)
        dst.write_text(cleaned_text, encoding="utf-8")
        return True
    except Exception as exc:
        print(f"Failed to convert {src}: {exc}")
        return False

def main() -> int:
    parser = argparse.ArgumentParser(description="Convert PDF files to text")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Input directory")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    
    pdf_files = list(args.input.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {args.input}")
        return 0

    for pdf_file in pdf_files:
        txt_file = args.output / pdf_file.with_suffix(".txt").name
        print(f"Converting {pdf_file} -> {txt_file}")
        convert_pdf_to_txt(pdf_file, txt_file)
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
