#!/usr/bin/env python3
import os
import sys
import json
import time
import hashlib
import requests
import re
from datetime import datetime

def calculate_sha1(filepath):
    sha1 = hashlib.sha1()
    with open(filepath, 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            sha1.update(data)
    return sha1.hexdigest()

def publish_file(html_file):
    if not os.path.exists(html_file):
        print(f"[!] HTML file not found: {html_file}")
        return False
        
    sha = calculate_sha1(html_file)
    filename = os.path.basename(html_file)
    
    # Read HTML content to extract title and preview
    with open(html_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Extract Title
    title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else filename
    
    # Extract Preview (e.g. text from section or paragraphs)
    preview = ""
    preview_match = re.search(r"<p.*?>(.*?)</p>", content, re.IGNORECASE)
    if preview_match:
        preview = re.sub(r"<.*?>", "", preview_match.group(1))
        preview = preview.strip()[:200]
        
    if not preview:
        preview = f"Phân tích chuyên sâu về video YouTube {filename}"
        
    print(f"[*] Publishing: {filename}")
    print(f"[*] Title: {title}")
    print(f"[*] SHA-1: {sha}")
    print(f"[*] Preview: {preview}")
    
    # 1. Update cms_db.json
    db_path = "/Users/vietmac/Library/CloudStorage/Dropbox/Vietndj_CMS_Workspace/vietndj.github.io/cms_db.json"
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)
        
    now = datetime.now()
    timestamp_ms = int(time.time() * 1000)
    full_date = now.strftime("%H:%M:%S %d/%m/%Y")
    
    new_entry = {
        "repoName": "k",
        "name": title,
        "fileName": filename,
        "sha": sha,
        "url": f"https://vietndj.github.io/k/{filename}",
        "timestamp": timestamp_ms,
        "fullDate": full_date,
        "preview": preview
    }
    
    # Check if entry already exists (by fileName)
    exists = False
    for idx, entry in enumerate(db["allFiles"]):
        if entry["fileName"] == filename:
            db["allFiles"][idx] = new_entry
            exists = True
            break
            
    if not exists:
        db["allFiles"].insert(0, new_entry)
        
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
        
    print(f"[+] Updated {db_path} with entry.")
    
    # Determine tag based on prompt type or file name
    tags = ["sto", "Science"]
    if "system-" in filename:
        tags = ["system", "Science"]
    elif "performance-" in filename:
        tags = ["performance", "Science"]
    elif "law-" in filename:
        tags = ["law", "Science"]
    elif "complex-" in filename:
        tags = ["complex", "Science"]
        
    # 2. Update metadata.json
    meta_path = "/Users/vietmac/Library/CloudStorage/Dropbox/Vietndj_CMS_Workspace/vietndj.github.io/metadata.json"
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
        
    meta_key = f"k/{filename}"
    meta["tags"][meta_key] = tags
    
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        
    print(f"[+] Updated {meta_path} with tags.")
    
    # 3. Sync to Supabase
    print("[*] Synchronizing with Supabase...")
    try:
        supabase_url = "https://hogksepvfxzhxyqllkxv.supabase.co/rest/v1/cms_store?id=eq.1&select=data"
        supabase_key = "sb_publishable_hvyjuTVE11__0IHZGHi_DQ_GylrEYoT"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
        
        s_res = requests.get(supabase_url, headers=headers, timeout=15)
        if s_res.status_code == 200:
            records = s_res.json()
            if records and len(records) > 0 and "data" in records[0]:
                sb_data = records[0]["data"]
                if "tags" not in sb_data: sb_data["tags"] = {}
                if "titles" not in sb_data: sb_data["titles"] = {}
                if "files" not in sb_data: sb_data["files"] = []
                
                sb_data["tags"][meta_key] = tags
                sb_data["titles"][meta_key] = title
                
                sb_existing_idx = -1
                for idx, f_item in enumerate(sb_data["files"]):
                    if (f_item.get("url") and f_item["url"].endswith(f"/k/{filename}")) or (f_item.get("repoName") == "k" and f_item.get("fileName") == filename):
                        sb_existing_idx = idx
                        break
                        
                sb_entry = {
                    "repoName": "k",
                    "name": title,
                    "fileName": filename,
                    "sha": sha,
                    "url": new_entry["url"],
                    "timestamp": timestamp_ms,
                    "fullDate": full_date,
                    "preview": preview
                }
                
                if sb_existing_idx != -1:
                    sb_data["files"][sb_existing_idx] = sb_entry
                else:
                    sb_data["files"].insert(0, sb_entry)
                    
                save_url = "https://hogksepvfxzhxyqllkxv.supabase.co/rest/v1/cms_store?id=eq.1"
                save_res = requests.patch(save_url, headers=headers, json={"data": sb_data}, timeout=15)
                if save_res.status_code in [200, 204]:
                    print("[+] Supabase synchronization successful!")
                    return True
                else:
                    print(f"[!] Supabase save failed: {save_res.status_code} {save_res.text}")
            else:
                print("[!] Empty data returned from Supabase.")
        else:
            print(f"[!] Fetch from Supabase failed: {s_res.status_code} {s_res.text}")
    except Exception as sb_err:
        print(f"[!] Supabase exception: {sb_err}")
    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 publish.py <html_filepath>")
        sys.exit(1)
    publish_file(sys.argv[1])
