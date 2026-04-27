import os
import torch
import stable_whisper
from fuzzywuzzy import process

def find_fragment(audio_path, transcript_path):
    print(f"🔄 Processing {os.path.basename(audio_path)}...")

    # 1. Get a rough transcription of the audio for matching
    # Using 'tiny' model, which is efficient for local CPU usage
    print("🔄 Generating rough transcription for matching...")
    model = stable_whisper.load_model("tiny", device="cpu")
    rough = model.transcribe(audio_path)
    
    # Concatenate segments into a single string for matching
    rough_text = " ".join([s.text for s in rough.segments])

    # 2. Load master transcript
    if not os.path.exists(transcript_path):
        print(f"❌ Transcript file not found: {transcript_path}")
        return

    with open(transcript_path, "r", encoding="utf-8") as f:
        master_text = f.read()

    # 3. Find the best matching chunk
    # Splitting by double newline, common in transcripts. 
    # Adjust this logic if your text uses different formatting.
    chunks = [c for c in master_text.split('\n\n') if len(c) > 50] 
    best_match, score = process.extractOne(rough_text, chunks)

    print(f"🎯 Found best matching segment (score: {score})")
    
    # 4. Save the matched segment to a new text file
    # Based on the mp3 name (e.g., 1401001.mp3 -> 1401001_segment.txt)
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(os.path.dirname(transcript_path), f"{base_name}_segment.txt")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(best_match)
        
    print(f"✅ Extracted segment saved to: {output_path}")

if __name__ == "__main__":
    # Example usage:
    # Update paths to match your directory
    audio = r"C:\Users\Long\Documents\InfiniteLife\mp3\1401001.mp3"
    txt = r"C:\Users\Long\Documents\InfiniteLife\txt\140102.txt"
    
    find_fragment(audio, txt)
