#!/usr/bin/env python3
import os
import json
import time
import hashlib
import requests
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

def publish():
    html_file = "/Users/vietmac/Library/CloudStorage/Dropbox/Vietndj_CMS_Workspace/k/system-1-why-i-believe-ai-has-already-surpassed-me.html"
    if not os.path.exists(html_file):
        print(f"[!] HTML file not found: {html_file}")
        return
        
    sha = calculate_sha1(html_file)
    filename = os.path.basename(html_file)
    
    # 1. Update cms_db.json
    db_path = "/Users/vietmac/Library/CloudStorage/Dropbox/Vietndj_CMS_Workspace/vietndj.github.io/cms_db.json"
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)
        
    now = datetime.now()
    timestamp_ms = int(time.time() * 1000)
    full_date = now.strftime("%H:%M:%S %d/%m/%Y")
    
    new_entry = {
        "repoName": "k",
        "name": "Trí tuệ Hệ thống #1 | Kỷ Nguyên Siêu Máy & Bảy Vết Rách Nhân Loại",
        "fileName": filename,
        "sha": sha,
        "url": f"https://vietndj.github.io/k/{filename}",
        "timestamp": timestamp_ms,
        "fullDate": full_date,
        "preview": "[01] The Matrix Đám đông đang chìm đắm trong ảo ảnh về một tương lai AGI xa vời hoặc utopia giả tạo, hoàn toàn mù lòa trước ma trận kiểm soát và sự tích tụ quyền lực cực đoan đang âm thầm diễn ra."
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
        
    print(f"[*] Updated {db_path} with entry.")
    
    # 2. Update metadata.json
    meta_path = "/Users/vietmac/Library/CloudStorage/Dropbox/Vietndj_CMS_Workspace/vietndj.github.io/metadata.json"
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
        
    meta_key = f"k/{filename}"
    meta["tags"][meta_key] = ["sto", "Science"]
    
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        
    print(f"[*] Updated {meta_path} with tags.")
    
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
                
                sb_data["tags"][meta_key] = ["sto", "Science"]
                sb_data["titles"][meta_key] = new_entry["name"]
                
                sb_existing_idx = -1
                for idx, f_item in enumerate(sb_data["files"]):
                    if (f_item.get("url") and f_item["url"].endswith(f"/k/{filename}")) or (f_item.get("repoName") == "k" and f_item.get("fileName") == filename):
                        sb_existing_idx = idx
                        break
                        
                sb_entry = {
                    "repoName": "k",
                    "name": new_entry["name"],
                    "fileName": filename,
                    "sha": sha,
                    "url": new_entry["url"],
                    "timestamp": timestamp_ms,
                    "fullDate": full_date,
                    "preview": new_entry["preview"]
                }
                
                if sb_existing_idx != -1:
                    sb_data["files"][sb_existing_idx] = sb_entry
                else:
                    sb_data["files"].insert(0, sb_entry)
                    
                save_url = "https://hogksepvfxzhxyqllkxv.supabase.co/rest/v1/cms_store?id=eq.1"
                save_res = requests.patch(save_url, headers=headers, json={"data": sb_data}, timeout=15)
                if save_res.status_code in [200, 204]:
                    print("[+] Supabase synchronization successful!")
                else:
                    print(f"[!] Supabase save failed: {save_res.status_code} {save_res.text}")
            else:
                print("[!] Empty data returned from Supabase.")
        else:
            print(f"[!] Fetch from Supabase failed: {s_res.status_code} {s_res.text}")
    except Exception as sb_err:
        print(f"[!] Supabase exception: {sb_err}")
        
if __name__ == "__main__":
    publish()
