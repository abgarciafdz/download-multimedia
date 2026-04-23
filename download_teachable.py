#!/usr/bin/env python3
"""
Download videos from Teachable/Hotmart courses.
Uses Playwright to intercept HLS master playlist + ffmpeg to download.

Requires:
  - cookies file in cookies/<subdomain>.teachable.com_cookies.txt
  - Playwright + Chromium installed
  - ffmpeg installed

Usage:
  python download_teachable.py --start 1 "URL1" "URL2" "URL3"
  python download_teachable.py --start 5 "URL"
  python download_teachable.py --dir clases-grupales "URL1" "URL2"

The script auto-detects each video's title from the page.
Files are named: 01_Título del video.mp4, 02_Otro título.mp4, etc.
--start sets the first sequence number (default: auto-detect from existing files).
--dir sets a subdirectory inside downloaded/<domain>/ (e.g. --dir clases-grupales).
"""

import asyncio
import subprocess
import sys
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).parent
COOKIES_DIR = BASE_DIR / "cookies"
DOWNLOAD_DIR = BASE_DIR / "downloaded"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def get_cookies_file(url):
    """Find cookies file for the given Teachable URL."""
    parsed = urlparse(url)
    domain = parsed.netloc
    cookies_file = COOKIES_DIR / f"{domain}_cookies.txt"
    if cookies_file.exists():
        return cookies_file
    for f in COOKIES_DIR.glob("*teachable*cookies*"):
        return f
    return None


def load_cookies(cookies_file):
    """Parse Netscape cookies.txt format into Playwright cookies."""
    with open(cookies_file) as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    browser_cookies = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 7:
            browser_cookies.append({
                "name": parts[5],
                "value": parts[6],
                "domain": parts[0],
                "path": parts[2],
                "secure": parts[3].upper() == "TRUE",
                "httpOnly": False,
            })
    return browser_cookies


def get_output_dir(url, subdir=None):
    """Get output directory: downloaded/<domain>/ or downloaded/<domain>/<subdir>/"""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    domain_dir = DOWNLOAD_DIR / domain
    if subdir:
        domain_dir = domain_dir / subdir
    domain_dir.mkdir(parents=True, exist_ok=True)
    return domain_dir


def get_next_sequence(output_dir):
    """Find the next sequence number based on existing files."""
    existing = []
    for f in output_dir.glob("*.mp4"):
        match = re.match(r"^(\d+)_", f.name)
        if match:
            existing.append(int(match.group(1)))
    return max(existing) + 1 if existing else 1


def sanitize_filename(title):
    """Clean title for use as filename."""
    # Remove characters not allowed in filenames
    clean = re.sub(r'[<>:"/\\|?*]', '', title)
    # Collapse multiple spaces
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


async def get_master_urls_and_title(lecture_url, cookies_file):
    """Use Playwright to load page, get video title and intercept ALL HLS master playlist URLs."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        await context.add_cookies(load_cookies(cookies_file))

        page = await context.new_page()
        master_urls = []
        seen_urls = set()

        async def handle_response(response):
            if "master" in response.url and ".m3u8" in response.url:
                # Deduplicate by base URL (ignore query params)
                base = response.url.split("?")[0]
                if base not in seen_urls:
                    seen_urls.add(base)
                    master_urls.append(response.url)

        page.on("response", handle_response)

        print(f"  Cargando página...")
        await page.goto(lecture_url, wait_until="domcontentloaded", timeout=30000)

        # Extract video title from the page
        title = None
        try:
            # Teachable puts the lecture title in an h2 inside the lecture content
            h2 = await page.query_selector("h2.section-title, h2.lecture-title, .course-mainbar h2")
            if h2:
                title = await h2.inner_text()
            if not title:
                # Fallback: page title
                page_title = await page.title()
                if page_title:
                    # Remove " | School Name" suffix
                    title = page_title.split("|")[0].strip()
        except Exception:
            pass

        # Wait for Hotmart video player to initialize and request HLS
        # Extra time to allow multiple players to load
        await asyncio.sleep(20)

        # Scroll down to trigger lazy-loaded video players
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(10)

        print(f"  Videos detectados: {len(master_urls)}")

        await browser.close()
        return master_urls, title


def download_with_ffmpeg(master_url, output_path):
    """Download HLS stream with ffmpeg (best quality, copy codecs)."""
    cmd = [
        "ffmpeg", "-y",
        "-headers", f"Referer: https://player.hotmart.com/\r\nUser-Agent: {USER_AGENT}\r\n",
        "-i", master_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        "-movflags", "+faststart",
        output_path
    ]

    print(f"  Descargando video con ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode == 0:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  ✓ {os.path.basename(output_path)} ({size_mb:.1f} MB)")
        return True
    else:
        print(f"  ✗ Error ffmpeg: {result.stderr[-300:]}")
        return False


async def main():
    # Parse arguments
    args = sys.argv[1:]
    start_seq = None
    subdir = None

    if "--start" in args:
        idx = args.index("--start")
        start_seq = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    if "--dir" in args:
        idx = args.index("--dir")
        subdir = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    urls = [a for a in args if a.startswith("http")]

    if not urls:
        print("Uso: python download_teachable.py [--start N] URL1 [URL2] [URL3] ...")
        print("  --start N  Número secuencial inicial (default: auto)")
        sys.exit(1)

    total_ok = 0
    total_fail = 0
    out_dir = None
    seq = None

    for i, url in enumerate(urls):
        print(f"\n{'='*60}")
        print(f"Video {i+1} de {len(urls)}")
        print(f"{'='*60}")

        # Find cookies
        cookies_file = get_cookies_file(url)
        if not cookies_file:
            parsed = urlparse(url)
            expected = f"{parsed.netloc}_cookies.txt"
            print(f"  ✗ No se encontró archivo de cookies: cookies/{expected}")
            print(f"    Exporta tus cookies con la extensión 'Get cookies.txt LOCALLY'")
            total_fail += 1
            continue

        # Output directory (same for all URLs of same domain)
        if out_dir is None:
            out_dir = get_output_dir(url, subdir)
            if start_seq is not None:
                seq = start_seq
            else:
                seq = get_next_sequence(out_dir)

        # Get HLS URLs and title via Playwright
        master_urls, title = await get_master_urls_and_title(url, cookies_file)

        if not master_urls:
            print(f"  ✗ No se encontró video. ¿Cookies expiradas?")
            total_fail += 1
            continue

        # Download each video found on the page
        for vid_idx, master_url in enumerate(master_urls):
            # Build filename: NN_Título del video.mp4 (add part suffix if multiple)
            if title:
                clean_title = sanitize_filename(title)
                if len(master_urls) > 1:
                    filename = f"{seq:02d}_{clean_title}_parte{vid_idx + 1}.mp4"
                else:
                    filename = f"{seq:02d}_{clean_title}.mp4"
            else:
                lecture_id = url.rstrip("/").split("/")[-1]
                if len(master_urls) > 1:
                    filename = f"{seq:02d}_{lecture_id}_parte{vid_idx + 1}.mp4"
                else:
                    filename = f"{seq:02d}_{lecture_id}.mp4"

            output_path = str(out_dir / filename)
            print(f"  Título: {title or '(no detectado)'}")
            print(f"  Archivo: {filename}")

            # Check if already exists
            if os.path.exists(output_path):
                print(f"  SKIP: ya existe")
                seq += 1
                continue

            # Download with ffmpeg
            if download_with_ffmpeg(master_url, output_path):
                total_ok += 1
            else:
                total_fail += 1

            seq += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"RESUMEN")
    print(f"{'='*60}")
    print(f"Videos descargados: {total_ok}")
    if total_fail:
        print(f"Errores: {total_fail}")
    if out_dir:
        print(f"Guardado en: {out_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
