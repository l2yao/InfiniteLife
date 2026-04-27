import os
import sys
import torch
from pydub import AudioSegment
import stable_whisper
from fuzzywuzzy import process

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
    rough1 = model.transcribe(audio_path, start=0, end=min(180, duration))
    rough1_text = " ".join([s.text for s in rough1.segments])
    
    # Transcribe last 3 minutes
    start_last = max(0, duration - 180)
    rough2 = model.transcribe(audio_path, start=start_last, end=duration)
    rough2_text = " ".join([s.text for s in rough2.segments])

    # 2. Load master transcript
    if not os.path.exists(transcript_path):
        print(f"❌ Transcript file not found: {transcript_path}")
        return

    with open(transcript_path, "r", encoding="utf-8") as f:
        master_text = f.read()

    # 3. Find the best matching chunk for the start and end segments separately
    # Splitting by double newline, common in transcripts. 
    # Adjust this logic if your text uses different formatting.
    chunks = [c for c in master_text.split('\n\n') if len(c) > 50]
    start_match, start_score = process.extractOne(rough1_text, chunks)
    end_match, end_score = process.extractOne(rough2_text, chunks)
    start_index = chunks.index(start_match)
    end_index = chunks.index(end_match)

    print(f"🎯 Found start segment (score: {start_score})")
    print(f"🎯 Found end segment (score: {end_score})")

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
