#!/usr/bin/env python3
"""Extract the transcript portion that belongs to one MP3 file.

The script transcribes a short clip from the beginning and end of an MP3,
finds those clips inside a larger transcript, then writes the raw transcript
slice between those two matches.
"""

from __future__ import annotations

import argparse
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from pydub import AudioSegment

try:
    import stable_whisper
except ImportError as exc:  # pragma: no cover - exercised by CLI users
    raise SystemExit(
        "Missing dependency: stable-whisper/stable-ts. "
        "Install requirements with: pip install -r requirements.txt"
    ) from exc

try:
    import torch
except ImportError:  # pragma: no cover - torch is optional for device detection
    torch = None


DEFAULT_CLIP_SECONDS = 180
DEFAULT_MODEL = "medium"


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class Match:
    raw_start: int
    raw_end: int
    token_start: int
    token_end: int
    score: float
    preview: str


def iter_normalized_units(text: str) -> Iterable[tuple[str, int, int]]:
    """Yield searchable units while preserving raw string offsets.

    CJK characters are emitted individually because transcripts often omit
    reliable spaces. Latin letters and numbers are grouped into words.
    """

    word_start: int | None = None
    word_end: int | None = None
    word_chars: list[str] = []

    def flush_word() -> tuple[str, int, int] | None:
        nonlocal word_start, word_end, word_chars
        if word_start is None or word_end is None:
            return None
        value = "".join(word_chars)
        item = (value, word_start, word_end)
        word_start = None
        word_end = None
        word_chars = []
        return item

    for index, char in enumerate(text):
        normalized = unicodedata.normalize("NFKC", char).casefold()
        if not normalized:
            continue

        char = normalized[0]
        category = unicodedata.category(char)
        is_cjk = "\u4e00" <= char <= "\u9fff"
        is_word = category[0] in {"L", "N"}

        if is_cjk:
            item = flush_word()
            if item:
                yield item
            yield char, index, index + 1
        elif is_word:
            if word_start is None:
                word_start = index
            word_end = index + 1
            word_chars.append(char)
        else:
            item = flush_word()
            if item:
                yield item

    item = flush_word()
    if item:
        yield item


def tokenize(text: str) -> list[Token]:
    return [Token(value, start, end) for value, start, end in iter_normalized_units(text)]


def segment_text(result: object) -> str:
    segments = getattr(result, "segments", None)
    if segments:
        return " ".join(getattr(segment, "text", "") for segment in segments).strip()
    return str(getattr(result, "text", "")).strip()


def transcribe_audio_slice(
    model: object,
    audio: AudioSegment,
    *,
    language: str | None,
) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        temp_path = Path(temp_file.name)

    try:
        audio.export(temp_path, format="wav")
        kwargs = {"language": language} if language else {}
        return segment_text(model.transcribe(str(temp_path), **kwargs))
    finally:
        temp_path.unlink(missing_ok=True)


def build_ngram_index(values: list[str], ngram_size: int) -> dict[tuple[str, ...], list[int]]:
    index: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for pos in range(0, len(values) - ngram_size + 1):
        index[tuple(values[pos : pos + ngram_size])].append(pos)
    return index


def choose_ngram_size(query_len: int) -> int:
    if query_len >= 80:
        return 6
    if query_len >= 30:
        return 5
    return 3


def candidate_starts(
    query_values: list[str],
    master_index: dict[tuple[str, ...], list[int]],
    *,
    ngram_size: int,
    min_token_start: int,
    max_candidates: int = 40,
) -> list[int]:
    votes: Counter[int] = Counter()

    for query_pos in range(0, len(query_values) - ngram_size + 1):
        ngram = tuple(query_values[query_pos : query_pos + ngram_size])
        for master_pos in master_index.get(ngram, []):
            start = master_pos - query_pos
            if start >= min_token_start:
                votes[start] += 1

    if not votes:
        return [min_token_start]

    return [start for start, _ in votes.most_common(max_candidates)]


def score_window(query_values: list[str], window_values: list[str]) -> float:
    if not query_values or not window_values:
        return 0.0

    sequence_score = SequenceMatcher(None, query_values, window_values, autojunk=False).ratio()
    overlap_score = sum((Counter(query_values) & Counter(window_values)).values()) / max(
        len(query_values), len(window_values)
    )
    return (sequence_score * 0.75) + (overlap_score * 0.25)


def find_best_match(
    query_text: str,
    master_text: str,
    master_tokens: list[Token],
    master_values: list[str],
    master_indexes: dict[int, dict[tuple[str, ...], list[int]]],
    *,
    min_token_start: int = 0,
) -> Match | None:
    query_tokens = tokenize(query_text)
    query_values = [token.value for token in query_tokens]

    if len(query_values) < 8 or not master_values:
        return None

    ngram_size = choose_ngram_size(len(query_values))
    index = master_indexes.setdefault(ngram_size, build_ngram_index(master_values, ngram_size))
    starts = candidate_starts(
        query_values,
        index,
        ngram_size=ngram_size,
        min_token_start=min_token_start,
    )

    best: Match | None = None
    query_len = len(query_values)

    for rough_start in starts:
        refine_from = max(min_token_start, rough_start - max(20, query_len // 8))
        refine_to = min(len(master_values) - 1, rough_start + max(20, query_len // 8))

        for start in range(refine_from, refine_to + 1):
            for scale in (0.85, 1.0, 1.15):
                window_len = max(8, round(query_len * scale))
                end = min(len(master_values), start + window_len)
                if end <= start:
                    continue

                window_values = master_values[start:end]
                score = score_window(query_values, window_values)
                if best is None or score > best.score:
                    raw_start = master_tokens[start].start
                    raw_end = master_tokens[end - 1].end
                    preview = " ".join(master_text[raw_start:raw_end].split())[:160]
                    best = Match(raw_start, raw_end, start, end, score, preview)

    return best


def load_model(model_name: str, device: str | None) -> object:
    if device is None:
        device = "cuda" if torch is not None and torch.cuda.is_available() else "cpu"
    print(f"Loading Whisper model '{model_name}' on {device}...")
    return stable_whisper.load_model(model_name, device=device)


def extract_fragment(
    audio_path: Path,
    transcript_path: Path,
    output_path: Path | None,
    *,
    clip_seconds: int,
    model_name: str,
    device: str | None,
    language: str | None,
    min_score: float,
) -> Path:
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if not transcript_path.exists():
        raise FileNotFoundError(f"Transcript file not found: {transcript_path}")

    print(f"Processing audio: {audio_path}")
    audio = AudioSegment.from_file(audio_path)
    duration_seconds = len(audio) / 1000
    clip_seconds = max(10, min(clip_seconds, int(duration_seconds)))

    print(f"Transcribing first and last {clip_seconds} seconds for matching...")
    model = load_model(model_name, device)
    first_text = transcribe_audio_slice(
        model,
        audio[: clip_seconds * 1000],
        language=language,
    )
    last_text = transcribe_audio_slice(
        model,
        audio[max(0, len(audio) - clip_seconds * 1000) :],
        language=language,
    )

    transcript = transcript_path.read_text(encoding="utf-8")
    master_tokens = tokenize(transcript)
    master_values = [token.value for token in master_tokens]
    master_indexes: dict[int, dict[tuple[str, ...], list[int]]] = {}

    print("Locating audio start in transcript...")
    start_match = find_best_match(
        first_text,
        transcript,
        master_tokens,
        master_values,
        master_indexes,
    )
    if start_match is None:
        raise RuntimeError("Could not locate the start clip in the transcript.")

    print("Locating audio end in transcript...")
    end_match = find_best_match(
        last_text,
        transcript,
        master_tokens,
        master_values,
        master_indexes,
        min_token_start=start_match.token_start,
    )
    if end_match is None:
        raise RuntimeError("Could not locate the end clip in the transcript.")

    print(f"Start match score: {start_match.score:.3f}")
    print(f"End match score:   {end_match.score:.3f}")
    print(f"Start preview: {start_match.preview}")
    print(f"End preview:   {end_match.preview}")

    if min(start_match.score, end_match.score) < min_score:
        raise RuntimeError(
            "Match confidence is too low. "
            f"Best scores were {start_match.score:.3f} and {end_match.score:.3f}; "
            f"minimum is {min_score:.3f}. Try --clip-seconds 240 or a smaller Whisper model "
            "only if the transcript/audio language is clear."
        )

    if end_match.raw_end < start_match.raw_start:
        raise RuntimeError("Matched end appears before matched start.")

    if output_path is None:
        output_path = transcript_path.with_name(f"{audio_path.stem}.txt")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(transcript[start_match.raw_start : end_match.raw_end].strip() + "\n", encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one MP3's transcript fragment from a larger transcript."
    )
    parser.add_argument("audio", type=Path, help="MP3 file to identify in the transcript")
    parser.add_argument("transcript", type=Path, help="Large transcript text file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output txt path. Defaults to <transcript-dir>/<audio-stem>.txt",
    )
    parser.add_argument(
        "--clip-seconds",
        type=int,
        default=DEFAULT_CLIP_SECONDS,
        help=f"Seconds to transcribe from the start and end of the MP3 (default: {DEFAULT_CLIP_SECONDS})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Whisper model to use through stable-whisper (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--device", choices=("cpu", "cuda"), help="Model device. Defaults to cuda if available.")
    parser.add_argument("--language", help="Optional Whisper language code, for example zh or en.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.35,
        help="Minimum accepted match score between 0 and 1 (default: 0.35)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_path = extract_fragment(
            args.audio,
            args.transcript,
            args.output,
            clip_seconds=args.clip_seconds,
            model_name=args.model,
            device=args.device,
            language=args.language,
            min_score=args.min_score,
        )
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Extracted fragment saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
