# InfiniteLife

A small utility collection for downloading and processing files from masterhnz.com.

## Requirements

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Scripts

### `download_mp3.py`

Download MP3 files in sequential sub-index ranges.

Usage:

```bash
python download_mp3.py --start 1 --end 5 --output mp3
```

This downloads files like `140101001.mp3`, `140101002.mp3`, etc., from `https://www.masterhnz.com/Video`.

### `download_pdf.py`

Download PDF documents for a range of codes.

Usage:

```bash
python download_pdf.py --start 1 --end 5 --output pdf
```

This downloads files like `140102.pdf`, `140202.pdf`, ..., from `https://www.masterhnz.com/Pdf/14`.

### `pdf_to_txt.py`

Convert all PDF files in a directory to text files, with simple cleanup to remove page numbers.

Usage:

```bash
python pdf_to_txt.py --input pdf --output txt
```

Converted `.txt` files are written to the `--output` directory.

### `extract_fragment.py`

Extract a transcript fragment from an audio file by matching rough transcriptions against a master transcript.

Usage:

```bash
python extract_fragment.py <audio_path> <transcript_path>
```

Example:

```bash
python extract_fragment.py mp3/140101001.mp3 txt/master_transcript.txt
```

The script creates a `.txt` file next to the transcript containing the matched text segment.

## Notes

- `extract_fragment.py` requires a local speech model and uses `stable-whisper`, `pydub`, `torch`, and `fuzzywuzzy`.
- `pdf_to_txt.py` uses `pypdf` for PDF extraction.
- Make sure you have `ffmpeg` installed if `pydub` needs it for audio conversions.
