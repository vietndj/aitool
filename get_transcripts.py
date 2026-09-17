import json
import os
import sys
import re
from datetime import datetime

try:
    import browser_cookie3
    import requests
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError as e:
    print(f"Missing dependency: {e}")
    sys.exit(1)

DROPBOX_BASE = os.path.expanduser("~/Library/CloudStorage/Dropbox/Vietndj_CMS_Workspace")
QUEUE_FILE = os.path.join(DROPBOX_BASE, "aitool", "transcripts", "YT-Gom", "_queue.json")
OUTPUT_DIR = os.path.join(DROPBOX_BASE, "aitool", "transcripts", "YT-Gom")

def sanitize_filename(name):
    clean = re.sub(r'[\\/*?:"<>|]', '', name).strip()
    return clean[:100]

def main():
    if not os.path.exists(QUEUE_FILE):
        print("Queue file not found.")
        return

    with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
        queue = json.load(f)

    pending_items = [item for item in queue if item.get('status') == 'pending']
    if not pending_items:
        print("No pending videos in queue.")
        return

    print(f"Found {len(pending_items)} pending videos. Loading Chrome cookies...")
    try:
        chrome_cookies = browser_cookie3.chrome(domain_name='.youtube.com')
        session = requests.Session()
        session.cookies.update({c.name: c.value for c in chrome_cookies})
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        })
        api = YouTubeTranscriptApi(http_client=session)
    except Exception as e:
        print(f"Failed to load cookies: {e}")
        return

    for item in pending_items:
        video_id = item['id']
        title = item['title']
        url = item['url']
        print(f"\nFetching transcript for: {title} ({video_id})...")
        
        try:
            # Try Vietnamese first, then English
            transcript_list = api.list(video_id)
            try:
                transcript = transcript_list.find_transcript(['vi'])
            except:
                try:
                    transcript = transcript_list.find_transcript(['en'])
                except:
                    # Translate any available to vi
                    avail = list(transcript_list._manually_created_transcripts.values()) + list(transcript_list._generated_transcripts.values())
                    if avail:
                        transcript = avail[0].translate('vi')
                    else:
                        raise Exception("No transcripts available")

            data = transcript.fetch()
            
            raw_text = " ".join([t['text'].replace('\n', ' ') for t in data])
            timestamped_lines = []
            for t in data:
                start = t['start']
                mins = int(start // 60)
                secs = int(start % 60)
                timestamped_lines.append(f"[{mins:02d}:{secs:02d}] {t['text'].replace('\n', ' ')}")
            
            timestamped_text = "\n".join(timestamped_lines)
            
            # Save file
            safe_title = sanitize_filename(title)
            filepath = os.path.join(OUTPUT_DIR, f"{safe_title}.txt")
            
            with open(filepath, 'w', encoding='utf-8') as out_f:
                out_f.write(f"Title: {title}\n")
                out_f.write(f"URL: {url}\n")
                out_f.write(f"ID: {video_id}\n")
                out_f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                out_f.write("="*80 + "\n\n")
                out_f.write("--- RAW TEXT (FOR LLM INPUT) ---\n")
                out_f.write(raw_text + "\n\n")
                out_f.write("--- TIMESTAMPED TEXT ---\n")
                out_f.write(timestamped_text + "\n")
                
            print(f"Saved transcript to: {filepath}")
            item['status'] = 'downloaded'
            item['file_path'] = filepath
            
        except Exception as e:
            print(f"Failed to fetch transcript for {video_id}: {e}")
            item['status'] = 'failed'
            item['error'] = str(e)

    # Save queue back
    with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
