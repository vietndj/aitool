#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_repo_hub.py — Universal Repo Hub Manifest & Poster Indexing Engine
========================================================================
Chuẩn hóa 2 logic cốt lõi của repo `k` để áp dụng cho `k`, `course` và mọi repo mới:
  1. Auto-Discovery & Manifest Indexing:
     - Quét 100% file .html trong repo (không bao giờ sót bài mới).
     - Lấy ngày cập nhật chuẩn xác qua 1 lần chạy `git log` (hoạt động đúng cả trên GitHub Actions CI lẫn Local).
     - Trích xuất title, excerpt, read_time, category, smart tags.
  2. Auto-Poster & Cover Banner Resolution:
     - Đọc `posters-map.json` (chuẩn hóa key theo stem không có `.html`, chống trượt key 100%).
     - Tự động kiểm tra `assets/covers/`, ảnh nhúng trong bài (nếu bật), và Deterministic Hash Fallback Cover.
     - Hỗ trợ `--verify-posters` kiểm tra HTTP 200 cho toàn bộ ảnh bìa.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from urllib.parse import quote
from bs4 import BeautifulSoup


DEFAULT_EXCLUDE = [
    "index.html",
    "404.html",
    "fix-url.html",
    "rajchannel.html",
    "skills.html",
    "admin.html",
    "temp_template.html",
    "algolia-test.html",
    "test-search.html",
]

DEFAULT_FALLBACK_COVERS = [
    "https://media.fedu.vn/k_covers/poster_the_dark_knight_rises_1790915630558.webp",
    "https://media.fedu.vn/k_covers/poster_bloodborne_1790915839906.webp",
    "https://media.fedu.vn/k_covers/poster_skyrim_1790915855678.webp",
    "https://media.fedu.vn/k_covers/harvey_specter_poster_1791005427104.webp",
    "https://media.fedu.vn/k_covers/v_cyberpunk_poster_1791005532729.webp",
    "https://media.fedu.vn/k_covers/walter_white_poster_1790936796056.webp",
    "https://media.fedu.vn/k_covers/bruce_wayne_poster_1790936369227.webp",
    "https://media.fedu.vn/k_covers/poster_nier_automata_1790917224295.webp",
    "https://media.fedu.vn/k_covers/poster_heat_1790916780101.webp",
    "https://media.fedu.vn/k_covers/akira_kaneda_poster_1790935387833.webp",
]


def load_json_safe(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Cảnh báo đọc {path}: {e}", file=sys.stderr)
    return default


def get_git_file_times(repo_dir: Path) -> Dict[str, str]:
    """
    Lấy thời gian commit cuối cùng của tất cả file trong repo bằng 1 lệnh git log duy nhất.
    Nếu file đang modified/untracked ở local thì dùng mtime hiện tại để nổi lên đầu.
    """
    file_times: Dict[str, str] = {}
    try:
        res = subprocess.run(
            ["git", "-c", "core.quotepath=off", "log", "--name-only", "--format=COMMIT_DATE:%cI"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            current_date = None
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("COMMIT_DATE:"):
                    current_date = line.split("COMMIT_DATE:", 1)[1].strip()
                elif current_date and line not in file_times:
                    # Chỉ ghi nhận lần xuất hiện đầu tiên (commit mới nhất của file đó)
                    file_times[line] = current_date

        # Kiểm tra các file mới sửa hoặc untracked ở local
        st_res = subprocess.run(
            ["git", "-c", "core.quotepath=off", "status", "--porcelain"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if st_res.returncode == 0:
            for line in st_res.stdout.splitlines():
                if len(line) > 3:
                    fname = line[3:].strip().strip('"')
                    fpath = repo_dir / fname
                    if fpath.exists() and fpath.suffix == ".html":
                        file_times[fname] = datetime.fromtimestamp(fpath.stat().st_mtime).astimezone().isoformat()
    except Exception as e:
        print(f"⚠️ Cảnh báo git log time: {e}", file=sys.stderr)

    return file_times


def clean_title(title_raw: str, filename: str) -> str:
    stem = filename[:-5] if filename.endswith(".html") else filename
    if not title_raw:
        return stem.replace("-", " ").replace("_", " ").title()
    title = re.sub(r"\s*\|\s*.*$", "", title_raw)
    title = re.sub(r"\s*-\s*Khóa Học.*$", "", title, flags=re.I)
    title = re.sub(r"\s*-\s*The Ultimate Guide.*$", "", title, flags=re.I)
    title = re.sub(r"^[ổỗô]\s*Tay", "Sổ Tay", title)
    title = title.strip()
    return title if len(title) > 2 else stem.replace("-", " ").title()


def extract_metadata(filepath: Path, filename: str) -> Tuple[str, str, int, Optional[str]]:
    """Trích xuất (title, excerpt, read_mins, embedded_cover) từ file HTML."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as fp:
            content = fp.read()
    except Exception:
        return clean_title("", filename), "Tài liệu chuyên sâu.", 5, None

    soup = BeautifulSoup(content, "html.parser")
    raw_title = ""
    if soup.title and soup.title.string:
        raw_title = soup.title.string.strip()
    elif soup.h1:
        raw_title = soup.h1.get_text(" ", strip=True)
    title = clean_title(raw_title, filename)

    # Trích xuất excerpt
    excerpt = ""
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if meta_desc and meta_desc.get("content") and len(meta_desc["content"].strip()) > 35:
        excerpt = meta_desc["content"].strip()
    else:
        for p in soup.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if len(txt) > 45 and not txt.startswith("http") and not txt.startswith("<"):
                excerpt = txt
                break
    if not excerpt:
        excerpt = "Tài liệu hướng dẫn chuyên sâu về kịch bản, tư duy thị giác và hệ thống vận hành thực chiến."
    if len(excerpt) > 165:
        excerpt = excerpt[:162].rstrip() + "..."

    # Ước tính thời gian đọc
    full_text = soup.get_text(" ", strip=True)
    word_count = len(re.findall(r"\w+", full_text))
    read_mins = max(2, min(25, round(word_count / 180)))

    # Tìm ảnh nhúng hợp lệ (og:image hoặc img trong bài)
    embedded_cover = None
    og_img = soup.find("meta", attrs={"property": "og:image"})
    if og_img and og_img.get("content", "").strip().startswith("http"):
        embedded_cover = og_img["content"].strip()
    else:
        img_urls = re.findall(r'https?://[^\s\"\'\(\)<>]+\.(?:jpg|jpeg|png|webp)', content, re.I)
        for u in img_urls:
            u_low = u.lower()
            if not any(skip in u_low for skip in ("icon", "avatar", "logo", "svg", "favicon", "badge")):
                embedded_cover = u
                break

    return title, excerpt, read_mins, embedded_cover


def _match_kw(haystack: str, kw: str) -> bool:
    kw_clean = kw.strip().lower()
    if not kw_clean:
        return False
    pattern = re.escape(kw_clean).replace(r"\-", r"[\s\-_]*")
    return bool(re.search(rf"\b{pattern}\b", haystack, flags=re.I))


def classify_post(filename: str, title: str, excerpt: str, config: Dict[str, Any]) -> Tuple[str, str]:
    """Phân loại category_key và category_label dựa trên smart_tags/categories trong config."""
    haystack = f"{filename} {title} {excerpt}".lower()
    smart_tags = config.get("smart_tags", {})
    if isinstance(smart_tags, dict):
        for tag_key, tag_info in smart_tags.items():
            keywords = tag_info.get("keywords", [])
            if any(_match_kw(haystack, kw) for kw in keywords):
                return tag_key, tag_info.get("label", tag_key)

    categories = config.get("categories", [])
    for cat in categories:
        keywords = cat.get("keywords", [])
        if any(_match_kw(haystack, kw) for kw in keywords):
            return cat["key"], cat["label"]

    # Fallback mặc định có ranh giới từ
    if any(_match_kw(haystack, k) for k in ("case", "học viên", "kenhmau", "kênh mẫu", "7 màn", "offline")):
        return "casestudy", "🏆 Case Study & Kênh Mẫu"
    if any(_match_kw(haystack, k) for k in ("broll", "b-roll", "cảnh trám", "shot-list", "quay")):
        return "broll", "🎬 B-Roll & Cảnh Trám"
    if any(_match_kw(haystack, k) for k in ("kich-ban", "kịch bản", "script", "kb3k4", "quangcao", "quảng cáo")):
        return "script", "📝 Kịch Bản Thực Chiến"
    if any(_match_kw(haystack, k) for k in ("logic", "tam-ly", "tâm lý", "nao-bo", "não bộ", "science", "dopamine")):
        return "science", "🧠 Kho Logic & Tâm Lý"
    if any(_match_kw(haystack, k) for k in ("ai", "aiedit", "aihook", "motion", "claude", "prompt", "agent", "skill")):
        return "ai_tech", "🤖 AI & Tự Động Hóa"
    if any(_match_kw(haystack, k) for k in ("podcast", "story", "xay-kenh", "xây kênh")):
        return "storytelling", "🚀 Podcast & Xây Kênh"
    return "other", "📌 Tài Liệu Chuyên Đề"


def resolve_cover_image(
    stem: str,
    filename: str,
    embedded_cover: Optional[str],
    repo_dir: Path,
    posters_map: Dict[str, str],
    fallbacks: List[str],
    allow_embedded: bool = True,
    cover_base_url: str = "https://media.fedu.vn/k_covers",
) -> Tuple[str, str]:
    """
    Trả về (cover_url, cover_source) theo thứ tự ưu tiên:
      1. posters-map.json (mapped)
      2. File có sẵn trong assets/covers/ (local_asset)
      3. Ảnh nhúng trong bài HTML nếu allow_embedded=True (embedded)
      4. Deterministic Hash Fallback từ fallbacks (fallback)
    """
    base_url = (cover_base_url or "https://media.fedu.vn/k_covers").rstrip("/")
    # 1. Tra trong posters-map.json (theo stem hoặc filename)
    if stem in posters_map and posters_map[stem]:
        return posters_map[stem], "mapped"
    if filename in posters_map and posters_map[filename]:
        return posters_map[filename], "mapped"

    # 2. Kiểm tra file local trong assets/covers/
    covers_dir = repo_dir / "assets" / "covers"
    if covers_dir.exists():
        for candidate in (f"poster_batch_{stem}.webp", f"{stem}.webp", f"poster_{stem}.webp"):
            if (covers_dir / candidate).exists():
                return f"{base_url}/{candidate}", "local_asset"

    # 3. Ảnh nhúng trong bài (nếu không phải ảnh unsplash chung chung hoặc nếu repo cho phép)
    if allow_embedded and embedded_cover:
        return embedded_cover, "embedded"

    # 4. Deterministic Fallback theo MD5 của stem
    pool = fallbacks if fallbacks else DEFAULT_FALLBACK_COVERS
    idx = int(hashlib.md5(stem.encode("utf-8")).hexdigest(), 16) % len(pool)
    return pool[idx], "fallback"


def verify_poster_urls(posts: List[Dict[str, Any]], repo_dir: Path) -> Tuple[int, List[Tuple[str, str, Any]]]:
    """Kiểm tra HTTP 200 / tồn tại file local cho tất cả cover_image trong manifest."""
    unique_urls = {}
    for p in posts:
        url = p.get("cover_image", "")
        if url not in unique_urls:
            unique_urls[url] = p["filename"]

    def check_one(item: Tuple[str, str]) -> Tuple[str, str, Any]:
        url, sample_file = item
        if not url:
            return (sample_file, url, "EMPTY_URL")
        if not url.startswith("http"):
            local_p = repo_dir / url.lstrip("./")
            return (sample_file, url, 200 if local_p.exists() else 404)
        try:
            safe_url = quote(url, safe=":/?&=%")
            req = urllib.request.Request(safe_url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                return (sample_file, url, resp.status)
        except Exception as e:
            return (sample_file, url, str(e))

    with ThreadPoolExecutor(max_workers=24) as ex:
        results = list(ex.map(check_one, unique_urls.items()))

    failed = [r for r in results if r[2] != 200]
    return len(unique_urls), failed


def build_repo_hub(repo_dir: Path, verify_posters: bool = False) -> Dict[str, Any]:
    repo_dir = repo_dir.resolve()
    config = load_json_safe(repo_dir / "repo-config.json", {})
    posters_data = load_json_safe(repo_dir / "posters-map.json", {"map": {}, "fallbacks": DEFAULT_FALLBACK_COVERS})

    # Chuẩn hóa mọi key trong posters-map về stem (bỏ .html)
    raw_map = posters_data.get("map", {})
    posters_map: Dict[str, str] = {}
    for k, v in raw_map.items():
        st = k[:-5] if k.endswith(".html") else k
        posters_map[st] = v
    fallbacks: List[str] = posters_data.get("fallbacks", DEFAULT_FALLBACK_COVERS) or DEFAULT_FALLBACK_COVERS

    # Nếu có thư mục đồng bộ phụ (ví dụ BAI GIANG VIDEO -> course_repo)
    sync_dirs = config.get("sync_html_from", [])
    for sdir_str in sync_dirs:
        sdir = Path(sdir_str)
        if sdir.exists() and sdir.resolve() != repo_dir:
            for src_html in sdir.glob("*.html"):
                if src_html.name in ("index.html", "404.html") or src_html.stat().st_size == 0:
                    continue
                dst_html = repo_dir / src_html.name
                if not dst_html.exists() or src_html.stat().st_mtime > dst_html.stat().st_mtime:
                    shutil.copy2(src_html, dst_html)

    exclude_set = set(config.get("exclude_files", DEFAULT_EXCLUDE))
    exclude_set.add("hub.html")
    allow_embedded = bool(config.get("allow_embedded_cover", True))
    cover_base_url = config.get("cover_base_url", "https://media.fedu.vn/k_covers")

    git_times = get_git_file_times(repo_dir)
    html_paths = sorted(repo_dir.glob("*.html"))

    posts: List[Dict[str, Any]] = []
    source_stats = {"mapped": 0, "local_asset": 0, "embedded": 0, "fallback": 0}
    unmapped_files: List[str] = []

    for fpath in html_paths:
        fname = fpath.name
        if fname in exclude_set:
            continue
        if fpath.stat().st_size == 0:
            # Bỏ qua file 0 byte rỗng
            continue

        stem = fname[:-5] if fname.endswith(".html") else fname
        title, excerpt, read_mins, embedded_cover = extract_metadata(fpath, fname)
        cat_key, cat_label = classify_post(fname, title, excerpt, config)
        cover_img, cover_source = resolve_cover_image(
            stem=stem,
            filename=fname,
            embedded_cover=embedded_cover,
            repo_dir=repo_dir,
            posters_map=posters_map,
            fallbacks=fallbacks,
            allow_embedded=allow_embedded,
            cover_base_url=cover_base_url,
        )
        source_stats[cover_source] = source_stats.get(cover_source, 0) + 1
        if cover_source == "fallback":
            unmapped_files.append(fname)

        updated_at = git_times.get(fname)
        if not updated_at:
            try:
                updated_at = datetime.fromtimestamp(fpath.stat().st_mtime).astimezone().isoformat()
            except Exception:
                updated_at = datetime.now().astimezone().isoformat()

        posts.append(
            {
                "filename": fname,
                "title": title,
                "excerpt": excerpt,
                "category_key": cat_key,
                "category_label": cat_label,
                "cover_image": cover_img,
                "cover_source": cover_source,
                "updated_at": updated_at,
                "read_time": f"{read_mins} phút đọc",
                "file_size_kb": round(fpath.stat().st_size / 1024, 1),
            }
        )

    # Sắp xếp bài mới nhất lên đầu
    posts.sort(key=lambda x: x["updated_at"], reverse=True)

    manifest_payload = {
        "site_id": config.get("site_id", repo_dir.name),
        "generated_at": datetime.now().astimezone().isoformat(),
        "total_posts": len(posts),
        "cover_stats": source_stats,
        "unmapped_count": len(unmapped_files),
        "posts": posts,
    }

    manifest_path = repo_dir / "posts-manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as out_fp:
        json.dump(manifest_payload, out_fp, ensure_ascii=False, indent=2)

    print(
        f"✅ [{repo_dir.name}] Đã xuất {len(posts)} bài vào {manifest_path.name} "
        f"(mapped={source_stats['mapped']}, local={source_stats['local_asset']}, "
        f"embedded={source_stats['embedded']}, fallback={source_stats['fallback']})"
    )

    # Nếu có mirror_to_dirs (ví dụ đồng bộ posts-manifest.json sang /Users/vietmac/Documents/CODE/course)
    for mdir_str in config.get("mirror_manifest_to", []):
        mdir = Path(mdir_str)
        if mdir.exists() and mdir.resolve() != repo_dir:
            try:
                shutil.copy2(manifest_path, mdir / "posts-manifest.json")
                if (repo_dir / "index.html").exists():
                    shutil.copy2(repo_dir / "index.html", mdir / "index.html")
            except Exception as e:
                print(f"⚠️ Mirror sang {mdir} warning: {e}", file=sys.stderr)

    if verify_posters:
        total_u, failed = verify_poster_urls(posts, repo_dir)
        if failed:
            print(f"❌ [VERIFY POSTERS FAIL] Phát hiện {len(failed)}/{total_u} URL ảnh bìa lỗi:")
            for sf, u, err in failed[:20]:
                print(f"   - {sf}: {u} -> {err}")
            sys.exit(2)
        else:
            print(f"🛡️ [VERIFY POSTERS PASS] 100% ({total_u}/{total_u}) URL ảnh bìa đều trả về HTTP 200 OK!")

    return manifest_payload


def main():
    parser = argparse.ArgumentParser(description="Universal Repo Hub Manifest & Poster Indexing Engine")
    parser.add_argument("--repo", type=str, default=".", help="Đường dẫn thư mục repo cần build")
    parser.add_argument("--verify-posters", action="store_true", help="Kiểm tra HTTP 200 cho toàn bộ ảnh bìa")
    args = parser.parse_args()

    build_repo_hub(Path(args.repo), verify_posters=args.verify_posters)


if __name__ == "__main__":
    main()
