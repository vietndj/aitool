#!/usr/bin/env python3
import os
import re
import sys
import time
from deep_translator import GoogleTranslator

def generate_extractive_summary(text, num_sentences=4):
    # Simple extractive summarizer based on word frequency
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= num_sentences:
        return text
        
    words = re.findall(r'\w+', text.lower())
    freqs = {}
    stopwords = {'tôi', 'và', 'là', 'cho', 'của', 'trong', 'được', 'có', 'một', 'những', 'này', 'với', 'khi', 'đã', 'đang', 'sẽ', 'nhưng', 'thì', 'the', 'a', 'to', 'and', 'of', 'in', 'is', 'that', 'it', 'for', 'you', 'on', 'this', 'with', 'i', 'my', 'we', 'they', 'he', 'she'}
    for w in words:
        if w not in stopwords:
            freqs[w] = freqs.get(w, 0) + 1
            
    sentence_scores = {}
    for i, sent in enumerate(sentences):
        sent_words = re.findall(r'\w+', sent.lower())
        if len(sent_words) < 10:  # Skip short phrases
            continue
        score = sum(freqs.get(w, 0) for w in sent_words)
        sentence_scores[i] = score
        
    if not sentence_scores:
        # Fallback if all sentences are short
        return " ".join(sentences[:num_sentences])
            
    top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:num_sentences]
    top_indices.sort()
    summary = " ".join([sentences[idx] for idx in top_indices])
    return summary

def translate_large_text(text, translator, chunk_size=3500):
    # Split text by sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = []
    current_len = 0
    
    for sent in sentences:
        if current_len + len(sent) + 1 > chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sent]
            current_len = len(sent)
        else:
            current_chunk.append(sent)
            current_len += len(sent) + 1
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    translated_chunks = []
    for idx, chunk in enumerate(chunks, 1):
        if not chunk.strip():
            continue
        try:
            # Add delay to avoid rate limiting
            time.sleep(0.5)
            trans = translator.translate(chunk)
            translated_chunks.append(trans)
        except Exception as e:
            print(f"      [!] Error translating raw chunk {idx}: {e}")
            translated_chunks.append(chunk) # Fallback to original
            
    return " ".join(translated_chunks)

def translate_timestamped_text(text, translator, lines_per_chunk=60):
    lines = text.split('\n')
    chunks = []
    for i in range(0, len(lines), lines_per_chunk):
        chunks.append("\n".join(lines[i:i+lines_per_chunk]))
        
    translated_chunks = []
    for idx, chunk in enumerate(chunks, 1):
        if not chunk.strip():
            continue
        try:
            # Add delay to avoid rate limiting
            time.sleep(0.5)
            trans = translator.translate(chunk)
            translated_chunks.append(trans)
        except Exception as e:
            print(f"      [!] Error translating timestamped chunk {idx}: {e}")
            translated_chunks.append(chunk) # Fallback to original
            
    return "\n".join(translated_chunks)

def process_file(filepath, translator):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    already_translated = "vi (translated" in content
    
    # Parse sections
    lines = content.split('\n')
    header_lines = []
    
    mode = "header"
    raw_lines = []
    time_lines = []
    
    for line in lines:
        if line.startswith("--- RAW TEXT"):
            mode = "raw"
            continue
        elif line.startswith("--- TIMESTAMPED TEXT"):
            mode = "timestamped"
            continue
        elif line.startswith("--- TÓM TẮT NỘI DUNG ---"):
            mode = "summary"
            continue
        elif line.startswith("==="):
            # Skip divider lines
            continue
            
        if mode == "header":
            if line.strip() and not line.startswith("Title:") and not line.startswith("URL:") and not line.startswith("ID:") and not line.startswith("Transcript Type:"):
                continue
            header_lines.append(line)
        elif mode == "summary":
            # Skip summary lines
            continue
        elif mode == "raw":
            raw_lines.append(line)
        elif mode == "timestamped":
            time_lines.append(line)
            
    raw_text = "\n".join(raw_lines).strip()
    timestamped_text = "\n".join(time_lines).strip()
    
    # Extract header variables
    title = ""
    url = ""
    vid_id = ""
    t_type = "Language: en"
    
    for hl in header_lines:
        if hl.startswith("Title:"):
            title = hl.replace("Title:", "").strip()
        elif hl.startswith("URL:"):
            url = hl.replace("URL:", "").strip()
        elif hl.startswith("ID:"):
            vid_id = hl.replace("ID:", "").strip()
        elif hl.startswith("Transcript Type:"):
            t_type = hl.replace("Transcript Type:", "").strip()
            
    if already_translated:
        print(f"    [*] Already translated. Regenerating summary...")
        vi_raw = raw_text
        vi_time = timestamped_text
        new_label = t_type
    else:
        print(f"    [*] Translating RAW text...")
        vi_raw = translate_large_text(raw_text, translator)
        
        print(f"    [*] Translating TIMESTAMPED text...")
        vi_time = translate_timestamped_text(timestamped_text, translator)
        new_label = f"{t_type} -> vi (translated via deep-translator)"
        
    print(f"    [*] Generating summary...")
    summary = generate_extractive_summary(vi_raw)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Title: {title}\n")
        f.write(f"URL: {url}\n")
        f.write(f"ID: {vid_id}\n")
        f.write(f"Transcript Type: {new_label}\n")
        f.write("="*80 + "\n\n")
        f.write("--- TÓM TẮT NỘI DUNG ---\n")
        f.write(summary + "\n\n")
        f.write("="*80 + "\n\n")
        f.write("--- RAW TEXT (FOR LLM INPUT) ---\n")
        f.write(vi_raw + "\n\n")
        f.write("--- TIMESTAMPED TEXT ---\n")
        f.write(vi_time + "\n")
        
    return True

def main():
    target_dir = "aitool/transcripts/Mo Gawdat - Videos"
    if not os.path.exists(target_dir):
        print(f"[!] Directory not found: {target_dir}")
        sys.exit(1)
        
    files = [os.path.join(target_dir, f) for f in os.listdir(target_dir) if f.endswith('.txt')]
    print(f"[*] Found {len(files)} transcript files to translate.")
    
    translator = GoogleTranslator(source='en', target='vi')
    
    success_count = 0
    for idx, filepath in enumerate(files, 1):
        filename = os.path.basename(filepath)
        print(f"[{idx}/{len(files)}] Processing: {filename}...")
        try:
            if process_file(filepath, translator):
                print(f"    -> Done!")
                success_count += 1
        except Exception as e:
            print(f"    -> Failed: {e}")
            
    print(f"\n[*] Successfully processed {success_count}/{len(files)} files.")

if __name__ == "__main__":
    main()
