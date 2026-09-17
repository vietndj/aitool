import os
import json

db_path = "vietndj.github.io/cms_db.json"
transcripts_dir = "aitool/transcripts/Mo Gawdat - Videos/"

with open(db_path, "r") as f:
    db = json.load(f)

# Collect all published names from db
published_names = set(item.get("name", "") for item in db.get("allFiles", []))

remaining = []
for file in os.listdir(transcripts_dir):
    if file.endswith(".txt"):
        with open(os.path.join(transcripts_dir, file), "r") as f:
            video_id = ""
            for line in f:
                if line.startswith("ID: "):
                    video_id = line.strip().split("ID: ")[1]
                    break
        # Also let's check if the URL or something is already in db.
        # Wait, the publish script puts the HTML file name in cms_db.json "fileName"
        # We don't have the video id in cms_db.json directly, but the file was generated.
        # Let's just check the html files in `k/` dir.
        
html_dir = "k/"
html_files = os.listdir(html_dir)

for file in os.listdir(transcripts_dir):
    if file.endswith(".txt"):
        # We can map the filename to a potential HTML slug
        # Or just read it
        remaining.append(file)

print("Let's check which transcripts haven't been processed based on my memory:")
