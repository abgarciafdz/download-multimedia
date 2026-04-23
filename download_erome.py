#!/usr/bin/env python3
"""Download images and videos from erome.com albums using Playwright + curl."""

import sys
import os
import json
import subprocess
import time
from playwright.sync_api import sync_playwright

DOWNLOAD_BASE = os.path.join(os.path.dirname(__file__), "downloaded", "erome.com")

def get_next_folder():
    """Get next sequential folder number."""
    if not os.path.exists(DOWNLOAD_BASE):
        os.makedirs(DOWNLOAD_BASE)
        return 1
    existing = [int(d) for d in os.listdir(DOWNLOAD_BASE) if d.isdigit()]
    return max(existing) + 1 if existing else 1


def extract_media(page):
    """Extract all media URLs from a rendered erome page."""
    # Videos from source tags
    videos = page.eval_on_selector_all(
        'video source', 'els => els.map(e => e.src)'
    )
    # Videos from video tags directly
    vids_direct = page.eval_on_selector_all(
        'video', 'els => els.map(e => e.src).filter(s => s)'
    )
    # Images from img tags inside media groups
    imgs = page.eval_on_selector_all(
        'div.media-group img', 'els => els.map(e => e.src).filter(s => s && !s.includes("thumb") && !s.includes("avatar"))'
    )
    # Images with data-src
    imgs_lazy = page.eval_on_selector_all(
        'div.media-group img[data-src]',
        'els => els.map(e => e.getAttribute("data-src")).filter(s => s && !s.includes("thumb"))'
    )
    # Combine and deduplicate
    all_videos = list(dict.fromkeys(videos + vids_direct))
    all_images = list(dict.fromkeys(imgs + imgs_lazy))
    # Filter out tiny/placeholder images
    all_images = [u for u in all_images if u and 'data:image' not in u]
    return all_videos, all_images


def download_file(url, dest, referer):
    """Download a file using curl with proper headers."""
    cmd = [
        'curl', '-sL', '-o', dest,
        '-H', f'Referer: {referer}',
        '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        '-H', f'Origin: https://www.erome.com',
        url
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    return result.returncode == 0


def main():
    urls = sys.argv[1:]
    if not urls:
        print("Uso: python download_erome.py URL1 URL2 ...")
        sys.exit(1)

    # Deduplicate URLs preserving order
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    total_images = 0
    total_videos = 0
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        for url in unique_urls:
            album_id = url.rstrip('/').split('/')[-1]
            folder_num = get_next_folder()
            folder = os.path.join(DOWNLOAD_BASE, f"{folder_num:02d}")
            os.makedirs(folder, exist_ok=True)

            print(f"\n{'='*60}")
            print(f"Descargando: {url}")
            print(f"Album ID: {album_id}")
            print(f"Carpeta: {folder}")
            print(f"{'='*60}")

            try:
                page = context.new_page()
                page.goto(url, wait_until='networkidle', timeout=30000)
                time.sleep(2)  # Extra wait for lazy-loaded content

                videos, images = extract_media(page)
                print(f"Encontrados: {len(videos)} videos, {len(images)} imágenes")

                # Download videos
                for i, vid_url in enumerate(videos, 1):
                    fname = f"{album_id}_video-{i:02d}.mp4"
                    dest = os.path.join(folder, fname)
                    print(f"  Descargando video: {fname}...")
                    if download_file(vid_url, dest, url):
                        size = os.path.getsize(dest) if os.path.exists(dest) else 0
                        if size > 1000:
                            total_videos += 1
                            print(f"    OK ({size / 1024 / 1024:.1f} MB)")
                        else:
                            os.remove(dest)
                            print(f"    Archivo muy pequeño, descartado")
                    else:
                        print(f"    Error descargando")

                # Download images
                for i, img_url in enumerate(images, 1):
                    ext = 'jpg'
                    if '.png' in img_url.lower():
                        ext = 'png'
                    elif '.gif' in img_url.lower():
                        ext = 'gif'
                    fname = f"{album_id}_imagen-{i:02d}.{ext}"
                    dest = os.path.join(folder, fname)
                    print(f"  Descargando imagen: {fname}...")
                    if download_file(img_url, dest, url):
                        size = os.path.getsize(dest) if os.path.exists(dest) else 0
                        if size > 5000:  # Skip tiny files (< 5KB)
                            total_images += 1
                            print(f"    OK ({size / 1024:.0f} KB)")
                        else:
                            os.remove(dest)
                            print(f"    Archivo muy pequeño, descartado")
                    else:
                        print(f"    Error descargando")

                page.close()

                # Remove folder if empty
                if not os.listdir(folder):
                    os.rmdir(folder)
                    print("  Sin contenido encontrado")

            except Exception as e:
                errors.append((url, str(e)))
                print(f"  ERROR: {e}")

            time.sleep(1)  # Be polite between requests

        browser.close()

    print(f"\n{'='*60}")
    print(f"RESUMEN")
    print(f"{'='*60}")
    print(f"URLs procesadas:      {len(unique_urls)}")
    print(f"Imágenes descargadas: {total_images}")
    print(f"Videos descargados:   {total_videos}")
    print(f"Guardado en:          {DOWNLOAD_BASE}")
    if errors:
        print(f"\nErrores:")
        for url, err in errors:
            print(f"  {url}: {err}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
