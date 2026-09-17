#!/usr/bin/env python3
import os
import sys
import argparse
import re
import yt_dlp
import requests
from concurrent.futures import ThreadPoolExecutor
from youtube_transcript_api import YouTubeTranscriptApi

cached_proxy_session = None

def sanitize_filename(name):
    # Remove invalid characters for filenames
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def format_time(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"

def generate_extractive_summary(text, num_sentences=4):
    import re
    # Simple extractive summarizer based on word frequency
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # Remove empty sentences
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

def generate_gemini_summary(text):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import urllib.request
        import json
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = f"Hãy tóm tắt ngắn gọn khoảng 3-5 câu chính từ nội dung transcript video sau đây bằng tiếng Việt:\n\n{text[:20000]}"
        data = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            summary = res_data['candidates'][0]['content']['parts'][0]['text']
            return summary.strip()
    except Exception as e:
        print(f"    [!] Failed to generate Gemini summary: {e}")
        return None

def get_working_session(video_id):
    global cached_proxy_session
    if cached_proxy_session is not None:
        return cached_proxy_session
        
    import socket
    socket.setdefaulttimeout(4)  # Ensure no socket hangs indefinitely (4s timeout)
    
    print("    [*] YouTube request blocked. Fetching public HTTP proxies to bypass block...")
    proxy_urls = [
        'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt',
        'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all'
    ]
    proxies = []
    for url in proxy_urls:
        try:
            r = requests.get(url, timeout=4)
            proxies.extend([p.strip() for p in r.text.split('\n') if p.strip()])
        except Exception:
            continue
            
    # De-duplicate
    proxies = list(set(proxies))
    print(f"    [*] Fetched {len(proxies)} proxies. Testing in parallel...")
    
    working_proxy = None
    
    def test_single_proxy(p):
        nonlocal working_proxy
        if working_proxy is not None:
            return
        session = requests.Session()
        session.proxies = {'http': f'http://{p}', 'https': f'http://{p}'}
        try:
            api = YouTubeTranscriptApi(http_client=session)
            api.list(video_id)
            working_proxy = p
        except Exception:
            pass

    # Test up to 100 proxies in parallel
    with ThreadPoolExecutor(max_workers=25) as executor:
        executor.map(test_single_proxy, proxies[:100])
        
    socket.setdefaulttimeout(15)  # Restore a longer timeout for general download phase
    
    if working_proxy:
        print(f"    [+] Success! Working proxy found: {working_proxy}")
        session = requests.Session()
        session.proxies = {'http': f'http://{working_proxy}', 'https': f'http://{working_proxy}'}
        cached_proxy_session = session
        return session
        
    return None

def get_transcript(video_id):
    global cached_proxy_session
    
    def attempt_fetch(session=None):
        api = YouTubeTranscriptApi(http_client=session) if session else YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        
        transcript = None
        lang_code = None
        is_generated = False
        is_translated = False
        
        # Priority 1: Manual Vietnamese
        try:
            transcript = transcript_list.find_transcript(['vi'])
            lang_code = 'vi'
        except Exception:
            # Priority 2: Generated Vietnamese
            try:
                transcript = transcript_list.find_generated_transcript(['vi'])
                lang_code = 'vi'
                is_generated = True
            except Exception:
                # Priority 3: Manual English translated to Vietnamese
                try:
                    transcript = transcript_list.find_manually_created_transcript(['en']).translate('vi')
                    lang_code = 'vi (translated from manual en)'
                    is_translated = True
                except Exception:
                    # Priority 4: Generated English translated to Vietnamese
                    try:
                        transcript = transcript_list.find_generated_transcript(['en']).translate('vi')
                        lang_code = 'vi (translated from auto en)'
                        is_translated = True
                    except Exception:
                        # Priority 5: Translate to Vietnamese from any manual/generated
                        try:
                            available_transcripts = list(transcript_list._manually_created_transcripts.values()) + list(transcript_list._generated_transcripts.values())
                            if available_transcripts:
                                first_avail = available_transcripts[0]
                                transcript = first_avail.translate('vi')
                                lang_code = f"vi (translated from {first_avail.language_code})"
                                is_translated = True
                        except Exception:
                            # Priority 6: Fallback to English (manual then generated)
                            try:
                                transcript = transcript_list.find_transcript(['en'])
                                lang_code = 'en'
                            except Exception:
                                # Priority 7: Any manual/generated as-is
                                try:
                                    available_transcripts = list(transcript_list._manually_created_transcripts.values()) + list(transcript_list._generated_transcripts.values())
                                    if available_transcripts:
                                        first_avail = available_transcripts[0]
                                        transcript = first_avail
                                        lang_code = f"{first_avail.language_code} (as-is)"
                                except Exception as e:
                                    raise Exception(f"Failed to get any transcript: {e}")
        
        if transcript:
            data = transcript.fetch()
            return data, lang_code, is_generated, is_translated
        else:
            raise Exception("No transcript available for this video.")

    try:
        # First try: with current cached proxy or default direct connection
        try:
            data, lang_code, is_generated, is_translated = attempt_fetch(cached_proxy_session)
        except Exception as e:
            # If rate limited / blocked, find a working proxy
            err_str = str(e)
            if "Too Many Requests" in err_str or "blocking requests" in err_str or "blocked" in err_str.lower() or "RequestBlocked" in err_str or "IPBlocked" in err_str or not cached_proxy_session:
                session = get_working_session(video_id)
                if session:
                    cached_proxy_session = session
                    data, lang_code, is_generated, is_translated = attempt_fetch(cached_proxy_session)
                else:
                    raise e
            else:
                raise e
                
        # Generate timestamped format
        timestamped_lines = []
        raw_text_parts = []
        
        for entry in data:
            start_time = format_time(entry.start)
            text = entry.text.replace('\n', ' ')
            timestamped_lines.append(f"[{start_time}] {text}")
            raw_text_parts.append(text)
        
        timestamped_text = "\n".join(timestamped_lines)
        raw_text = " ".join(raw_text_parts)
        
        # Generate summary (either via Gemini or extractive fallback)
        summary = generate_gemini_summary(raw_text)
        if not summary:
            summary = generate_extractive_summary(raw_text)
        
        # Format label
        label = f"Language: {lang_code}"
        if is_generated:
            label += " (Auto-generated)"
        if is_translated:
            label += " (Auto-translated)"
            
        return {
            'timestamped': timestamped_text,
            'raw': raw_text,
            'summary': summary,
            'label': label
        }, None
        
    except Exception as e:
        return None, str(e)

def extract_videos(url):
    # Adjust URL if it is a base channel URL to get the videos list
    channel_patterns = [
        r'youtube\.com/@[^/]+$',
        r'youtube\.com/channel/[^/]+$',
        r'youtube\.com/c/[^/]+$',
        r'youtube\.com/user/[^/]+$'
    ]
    
    clean_url = url.split('?')[0].rstrip('/')
    for pattern in channel_patterns:
        if re.search(pattern, clean_url):
            parts = url.split('?')
            base = parts[0].rstrip('/')
            query = f"?{parts[1]}" if len(parts) > 1 else ""
            url = f"{base}/videos{query}"
            print(f"[*] Base channel URL detected. Adjusting to: {url}")
            break

    ydl_opts = {
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    print(f"[*] Extracting video list from: {url}...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"[!] Error extracting URL info: {e}", file=sys.stderr)
            return None, None
            
        title = info.get('title', 'Unknown Playlist/Channel')
        
        videos = []
        if 'entries' in info:
            # It's a playlist or channel
            for entry in info['entries']:
                if entry:
                    videos.append({
                        'id': entry.get('id'),
                        'title': entry.get('title'),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id')}"
                    })
        else:
            # Single video
            videos.append({
                'id': info.get('id'),
                'title': info.get('title'),
                'url': f"https://www.youtube.com/watch?v={info.get('id')}"
            })
            
        return title, videos

def main():
    parser = argparse.ArgumentParser(description="Download YouTube Video, Playlist, or Channel Transcripts")
    parser.add_argument("url", help="YouTube video, playlist, or channel URL")
    parser.add_argument("-o", "--output-dir", default="aitool/transcripts", help="Output directory for transcripts")
    parser.add_argument("-l", "--limit", type=int, default=50, help="Limit maximum number of videos to fetch (default: 50)")
    
    args = parser.parse_args()
    
    playlist_title, videos = extract_videos(args.url)
    if not videos:
        print("[!] No videos found or failed to extract info.")
        sys.exit(1)
        
    total_videos = len(videos)
    print(f"[*] Found {total_videos} videos in '{playlist_title}'.")
    
    if total_videos > args.limit:
        print(f"[*] Limiting download to the first {args.limit} videos (use -l to increase).")
        videos = videos[:args.limit]
        
    # Create target directory
    safe_folder_name = sanitize_filename(playlist_title)
    target_dir = os.path.join(args.output_dir, safe_folder_name)
    os.makedirs(target_dir, exist_ok=True)
    
    print(f"[*] Transcripts will be saved to: {target_dir}\n")
    
    success_count = 0
    skipped_count = 0
    
    # We will create an index file
    index_lines = [
        f"# Transcripts for: {playlist_title}",
        f"Source URL: {args.url}",
        f"Total videos found: {total_videos}",
        f"Transcripts extracted: {len(videos)}",
        "",
        "## Videos List",
        ""
    ]
    
    for idx, video in enumerate(videos, 1):
        video_id = video['id']
        video_title = video['title']
        video_url = video['url']
        
        safe_title = sanitize_filename(video_title)
        if len(safe_title) > 100:
            safe_title = safe_title[:100]
            
        filename = f"{safe_title}.txt"
        filepath = os.path.join(target_dir, filename)
        
        # Skip if already exists
        if os.path.exists(filepath):
            print(f"[{idx}/{len(videos)}] {video_title} -> Already exists, skipping.")
            success_count += 1
            index_lines.append(f"{idx}. [{video_title}]({filename}) - `Already exists`")
            continue
            
        print(f"[{idx}/{len(videos)}] Processing: {video_title} (ID: {video_id})...")
        result, error = get_transcript(video_id)
        
        if result:
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"Title: {video_title}\n")
                f.write(f"URL: {video_url}\n")
                f.write(f"ID: {video_id}\n")
                f.write(f"Transcript Type: {result['label']}\n")
                f.write("="*80 + "\n\n")
                f.write("--- TÓM TẮT NỘI DUNG ---\n")
                f.write(result['summary'] + "\n\n")
                f.write("="*80 + "\n\n")
                f.write("--- RAW TEXT (FOR LLM INPUT) ---\n")
                f.write(result['raw'] + "\n\n")
                f.write("--- TIMESTAMPED TEXT ---\n")
                f.write(result['timestamped'] + "\n")
                
            print(f"    -> Saved successfully! ({result['label']})")
            success_count += 1
            
            index_lines.append(f"{idx}. [{video_title}]({filename}) - `{result['label']}`")
        else:
            print(f"    -> Failed: {error}")
            skipped_count += 1
            index_lines.append(f"{idx}. {video_title} (No Transcript) - Error: `{error}`")
            
    # Save index file
    index_path = os.path.join(target_dir, "README.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(index_lines))
        
    print("\n" + "="*50)
    print(f"Finished processing!")
    print(f"Successfully downloaded: {success_count} transcripts.")
    print(f"Failed/Skipped: {skipped_count} videos.")
    print(f"Summary index file written to: {index_path}")
    print("="*50)

if __name__ == "__main__":
    main()
