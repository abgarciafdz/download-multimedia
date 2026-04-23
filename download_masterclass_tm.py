#!/usr/bin/env python3
"""
Download videos from masterclass.tradingmasivo.com (Systeme.io course platform).

Uses Playwright to render each lecture page (with cookies) and intercepts
direct CloudFront .mp4 URLs. Downloads with curl (direct MP4, no HLS).

Requires:
  - cookies file in cookies/masterclass.tradingmasivo.com_cookies.txt
  - Playwright + Chromium installed

Usage:
  python download_masterclass_tm.py "URL1" "URL2" "URL3"
  python download_masterclass_tm.py --start 3 "URL"
  python download_masterclass_tm.py --dir mi-carpeta "URL1" "URL2"

Files are named: NN_NombreDetectado.mp4 using the original CloudFront filename.
Pages with multiple videos generate NN_Titulo_parte1.mp4, NN_Titulo_parte2.mp4.
"""

import asyncio
import subprocess
import sys
import os
import re
from pathlib import Path
from urllib.parse import urlparse, unquote
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).parent
COOKIES_DIR = BASE_DIR / "cookies"
DOWNLOAD_DIR = BASE_DIR / "downloaded"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def get_cookies_file(url):
    parsed = urlparse(url)
    cookies_file = COOKIES_DIR / f"{parsed.netloc}_cookies.txt"
    return cookies_file if cookies_file.exists() else None


def load_cookies(cookies_file):
    with open(cookies_file) as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    out = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 7:
            out.append({
                "name": parts[5], "value": parts[6],
                "domain": parts[0], "path": parts[2],
                "secure": parts[3].upper() == "TRUE", "httpOnly": False,
            })
    return out


def get_output_dir(url, subdir=None):
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    d = DOWNLOAD_DIR / domain
    if subdir:
        d = d / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_next_sequence(output_dir):
    existing = []
    for f in output_dir.glob("*.mp4"):
        m = re.match(r"^(\d+)_", f.name)
        if m:
            existing.append(int(m.group(1)))
    return max(existing) + 1 if existing else 1


def sanitize_filename(title):
    clean = re.sub(r'[<>:"/\\|?*]', '', title)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def extract_title_from_mp4_url(mp4_url):
    """
    Extract meaningful title from CloudFront MP4 URL.
    Pattern: .../14643342/69da0a468afd39.90587596_CLASE0-PRESENTACION.mp4
    We want: CLASE0-PRESENTACION
    """
    path = urlparse(mp4_url).path
    filename = os.path.basename(path)
    filename = unquote(filename)  # decode %20, etc
    # Remove .mp4
    name = re.sub(r'\.mp4$', '', filename, flags=re.IGNORECASE)
    # Remove leading hash pattern (hex + dot + digits + underscore)
    name = re.sub(r'^[a-f0-9]+\.?\d*_', '', name)
    # Replace underscores with spaces
    name = name.replace('_', ' ').strip()
    return name if name else "video"


async def get_video_urls(lecture_url, cookies_file):
    """Load page with cookies and intercept all unique CloudFront MP4 URLs."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        await context.add_cookies(load_cookies(cookies_file))
        page = await context.new_page()

        mp4_urls = []
        seen = set()

        async def on_response(response):
            u = response.url
            if u.endswith(".mp4") or ".mp4?" in u:
                base = u.split("?")[0]
                if base not in seen:
                    seen.add(base)
                    mp4_urls.append(u)

        page.on("response", on_response)

        print("  Cargando página...")
        await page.goto(lecture_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(8)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(7)

        await browser.close()
        print(f"  Videos detectados: {len(mp4_urls)}")
        return mp4_urls


def download_mp4(mp4_url, output_path, referer):
    """Download direct MP4 with curl (supports large files + Referer)."""
    print("  Descargando con curl...")
    cmd = [
        "curl", "-L", "-f",
        "--retry", "3", "--retry-delay", "2",
        "-H", f"User-Agent: {USER_AGENT}",
        "-H", f"Referer: {referer}",
        "-o", output_path,
        mp4_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  ✓ {os.path.basename(output_path)} ({size_mb:.1f} MB)")
        return True
    print(f"  ✗ Error curl: {result.stderr[-300:]}")
    if os.path.exists(output_path):
        os.remove(output_path)
    return False


async def main():
    args = sys.argv[1:]
    start_seq = None
    subdir = None

    if "--start" in args:
        i = args.index("--start"); start_seq = int(args[i+1]); args = args[:i] + args[i+2:]
    if "--dir" in args:
        i = args.index("--dir"); subdir = args[i+1]; args = args[:i] + args[i+2:]

    urls = [a for a in args if a.startswith("http")]
    if not urls:
        print("Uso: python download_masterclass_tm.py [--start N] [--dir SUB] URL1 [URL2] ...")
        sys.exit(1)

    total_ok = total_fail = 0
    out_dir = None
    seq = None

    for i, url in enumerate(urls):
        print(f"\n{'='*60}\nLección {i+1} de {len(urls)}\n{'='*60}")
        print(f"URL: {url}")

        cookies_file = get_cookies_file(url)
        if not cookies_file:
            print(f"  ✗ Cookies no encontradas para {urlparse(url).netloc}")
            total_fail += 1
            continue

        if out_dir is None:
            out_dir = get_output_dir(url, subdir)
            seq = start_seq if start_seq is not None else get_next_sequence(out_dir)

        mp4_urls = await get_video_urls(url, cookies_file)
        if not mp4_urls:
            print("  ✗ No se detectaron MP4 — ¿cookies expiradas o la página no tiene video?")
            total_fail += 1
            continue

        for vid_idx, mp4_url in enumerate(mp4_urls):
            title = extract_title_from_mp4_url(mp4_url)
            clean = sanitize_filename(title)
            if len(mp4_urls) > 1:
                filename = f"{seq:02d}_{clean}_parte{vid_idx+1}.mp4"
            else:
                filename = f"{seq:02d}_{clean}.mp4"
            output_path = str(out_dir / filename)
            print(f"  Archivo: {filename}")

            if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
                print("  SKIP: ya existe")
                seq += 1
                continue

            if download_mp4(mp4_url, output_path, url):
                total_ok += 1
            else:
                total_fail += 1
            seq += 1

    print(f"\n{'='*60}\nRESUMEN\n{'='*60}")
    print(f"Videos descargados: {total_ok}")
    if total_fail:
        print(f"Errores: {total_fail}")
    if out_dir:
        print(f"Guardado en: {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
