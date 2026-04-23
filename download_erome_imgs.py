#!/usr/bin/env python3
"""Download images from erome.com albums using requests + HTML parsing.
yt-dlp handles videos but NOT images, so this script complements it."""

import sys
import os
import re
import time
import hashlib
import requests
from bs4 import BeautifulSoup

DOWNLOAD_BASE = os.path.join(os.path.dirname(__file__), "downloaded", "erome.com")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def extract_images(html, base_url):
    """Extract image URLs from erome page HTML."""
    soup = BeautifulSoup(html, 'lxml')
    urls = set()

    # Pattern 1: <div class="img" data-src="URL">
    for div in soup.select('div.img[data-src]'):
        src = div.get('data-src', '')
        if src and '/thumbs/' not in src:
            urls.add(src.split('?')[0])

    # Pattern 2: <img class="img-front" src="URL">
    for img in soup.select('img.img-front'):
        src = img.get('src', '')
        if src and '/thumbs/' not in src:
            urls.add(src.split('?')[0])

    # Pattern 3: any img inside media-group
    for img in soup.select('.media-group img'):
        src = img.get('src', '') or img.get('data-src', '')
        if src and '/thumbs/' not in src and 'avatar' not in src:
            urls.add(src.split('?')[0])

    return list(urls)


def download_image(url, dest, referer):
    """Download an image file."""
    try:
        headers = {**HEADERS, 'Referer': referer}
        r = requests.get(url, headers=headers, timeout=30, stream=True)
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return os.path.getsize(dest)
    except Exception as e:
        print(f"    Error: {e}")
        return 0


def main():
    urls = sys.argv[1:]
    if not urls:
        print("Uso: python download_erome_imgs.py URL1 URL2 ...")
        sys.exit(1)

    # Deduplicate
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    total_images = 0
    session = requests.Session()
    session.headers.update(HEADERS)

    for idx, url in enumerate(unique_urls, 1):
        album_id = url.rstrip('/').split('/')[-1]
        folder = os.path.join(DOWNLOAD_BASE, f"{idx:02d}")
        os.makedirs(folder, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"[{idx}/{len(unique_urls)}] {album_id}")
        print(f"{'='*60}")

        try:
            r = session.get(url, headers={**HEADERS, 'Referer': 'https://www.erome.com/'}, timeout=30)
            r.raise_for_status()
            images = extract_images(r.text, url)
            print(f"  Imágenes encontradas: {len(images)}")

            for i, img_url in enumerate(images, 1):
                ext = 'jpg'
                if '.png' in img_url.lower():
                    ext = 'png'
                elif '.gif' in img_url.lower():
                    ext = 'gif'
                fname = f"{album_id}_imagen-{i:02d}.{ext}"
                dest = os.path.join(folder, fname)
                print(f"  Descargando: {fname}...", end=' ')
                size = download_image(img_url, dest, url)
                if size > 5000:
                    total_images += 1
                    print(f"OK ({size/1024:.0f} KB)")
                elif size > 0:
                    os.remove(dest)
                    print("descartado (muy pequeño)")
                else:
                    if os.path.exists(dest):
                        os.remove(dest)
                    print("fallido")

        except Exception as e:
            print(f"  ERROR: {e}")

        time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"RESUMEN IMÁGENES")
    print(f"{'='*60}")
    print(f"URLs procesadas:      {len(unique_urls)}")
    print(f"Imágenes descargadas: {total_images}")
    print(f"Guardado en:          {DOWNLOAD_BASE}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
