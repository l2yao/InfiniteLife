import os
import sys
import tempfile
import torch
from pydub import AudioSegment
import stable_whisper
from fuzzywuzzy import process

def _transcribe_segment(model, segment, format="wav"):
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{format}") as tmp:
        segment.export(tmp.name, format=format)
        tmp_path = tmp.name
    try:
        result = model.transcribe(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return result

def find_fragment(audio_path, transcript_path):
    print(f"🔄 Processing {os.path.basename(audio_path)}...")

    # 1. Get audio duration
    audio = AudioSegment.from_file(audio_path)
    duration = len(audio) / 1000  # duration in seconds
    
    # Get a rough transcription of the first 3 min and last 3 min for matching
    print("🔄 Generating rough transcription for matching...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = stable_whisper.load_model("medium", device=device)
    
    # Transcribe first 3 minutes
    end_first_ms = int(min(180, duration) * 1000)
    rough1 = _transcribe_segment(model, audio[:end_first_ms])
    rough1_text = " ".join([s.text for s in rough1.segments])
    
    # Transcribe last 3 minutes
    start_last_ms = int(max(0, duration - 180) * 1000)
    rough2 = _transcribe_segment(model, audio[start_last_ms:])
    rough2_text = " ".join([s.text for s in rough2.segments])

    # 2. Load master transcript
    if not os.path.exists(transcript_path):
        print(f"❌ Transcript file not found: {transcript_path}")
        return

    with open(transcript_path, "r", encoding="utf-8") as f:
        master_text = f.read()

    # 3. Find the best matching chunk for the start and end segments separately
    # Splitting by double newline, common in transcripts. 
    chunks = [c for c in master_text.split('\n\n') if len(c) > 50]

    # Restrict search space: Start match in first 25%, end match in last 25%
    total_chunks = len(chunks)
    search_start_space = chunks[:max(1, total_chunks // 4)]
    search_end_space = chunks[max(0, 3 * total_chunks // 4):]

    start_match, start_score = process.extractOne(rough1_text, search_start_space)
    end_match, end_score = process.extractOne(rough2_text, search_end_space)
    
    start_index = chunks.index(start_match)
    # Find index of end_match in the original chunks list
    end_index = chunks.index(end_match)

    print(f"🎯 Found start segment (score: {start_score}, index: {start_index})")
    print(f"🎯 Found end segment (score: {end_score}, index: {end_index})")

    if start_index <= end_index:
        matched_text = "\n\n".join(chunks[start_index:end_index + 1])
    else:
        print("⚠️ Start segment matches after end segment in transcript. Saving both matches separately.")
        matched_text = f"--- START MATCH ---\n{start_match}\n\n--- END MATCH ---\n{end_match}"
    
    # 4. Save the matched segment to a new text file
    # Based on the mp3 name (e.g., 1401001.mp3 -> 1401001.txt)
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(os.path.dirname(transcript_path), f"{base_name}.txt")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(matched_text)
        
    print(f"✅ Extracted segment saved to: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python extract_fragment.py <audio_path> <transcript_path>")
        sys.exit(1)
    
    audio_path = sys.argv[1]
    transcript_path = sys.argv[2]
    
    find_fragment(audio_path, transcript_path)
