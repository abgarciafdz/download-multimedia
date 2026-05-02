#!/usr/bin/env python3
"""
Skool downloader — descarga videos de classroom de Skool.com.

Skool sirve videos por dos rutas:
  1. Embeds externos (Loom/Vimeo/YouTube) → metadata.videoLink
  2. Player nativo basado en Mux → metadata.videoId + objeto "video" con
     playbackId y playbackToken (JWT firmado, requiere Referer skool.com)

El parámetro ?md=<id> identifica la lección dentro del classroom.

Uso:
  python scripts/download_skool.py --dir CARPETA URL1 URL2 ...
  python scripts/download_skool.py --dir CARPETA --start 5 URL1 URL2 ...

Requiere:
  - cookies/www.skool.com_cookies.txt (formato Netscape)
  - yt-dlp (descarga Loom/Vimeo/YouTube + HLS de Mux con headers)
"""

import argparse
import http.cookiejar
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
COOKIES = ROOT / "cookies" / "www.skool.com_cookies.txt"
DOWNLOAD_DIR = ROOT / "downloaded" / "skool"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def sanitize(text, max_len=80):
    text = re.sub(r"[<>:\"/\\|?*\n\r\t]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[^\w\-\.\s áéíóúñÁÉÍÓÚÑüÜ¡¿!?'’“”\(\)\[\]&,]", "", text)
    text = text.strip(" .")
    return (text[:max_len] if len(text) > max_len else text) or "video"


def open_authenticated():
    if not COOKIES.exists():
        print(f"✗ Cookies no encontradas: {COOKIES}", file=sys.stderr)
        sys.exit(1)
    cj = http.cookiejar.MozillaCookieJar(str(COOKIES))
    cj.load(ignore_discard=True, ignore_expires=True)
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [
        ("User-Agent", USER_AGENT),
        ("Accept-Language", "en-US,en;q=0.9,es;q=0.8"),
    ]
    return op


def fetch_lesson_data(opener, page_url):
    """Devuelve (lessons_index, mux_video) para la página dada.

    lessons_index: dict {md_id: {title, videoLink, videoId}} con todas las
    lecciones que tengan videoLink o videoId.

    mux_video: dict con {playbackId, playbackToken} de la lección actual si
    usa Mux, o None. Cada visita a una URL ?md=X devuelve solo el mux_video
    de esa lección específica.
    """
    html = opener.open(page_url, timeout=30).read().decode("utf-8", errors="ignore")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("No se encontró __NEXT_DATA__ en la página")
    data = json.loads(m.group(1))

    index = {}
    mux_video = None

    def walk(obj):
        nonlocal mux_video
        if isinstance(obj, dict):
            lid = obj.get("id")
            meta = obj.get("metadata")
            if lid and isinstance(meta, dict):
                title = (meta.get("title") or "").strip() or lid
                if meta.get("videoLink"):
                    index[lid] = {"title": title, "videoLink": meta["videoLink"], "videoId": meta.get("videoId")}
                elif meta.get("videoId"):
                    index[lid] = {"title": title, "videoLink": None, "videoId": meta["videoId"]}
            if "playbackId" in obj and "playbackToken" in obj:
                mux_video = obj
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return index, mux_video


def get_md(url):
    qs = parse_qs(urlparse(url).query)
    md = qs.get("md", [None])[0]
    if not md:
        raise ValueError(f"URL sin parámetro ?md=: {url}")
    return md


def get_next_seq(folder):
    if not folder.exists():
        return 1
    nums = []
    for f in folder.iterdir():
        m = re.match(r"^(\d{2})_", f.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def download_embed(video_link, out_path):
    """Descarga un Loom/Vimeo/YouTube con yt-dlp."""
    cmd = [
        "yt-dlp", "--no-warnings", "--no-playlist",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", str(out_path),
        video_link,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        last = res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "sin output"
        print(f"  ✗ yt-dlp (embed) falló: {last}")
        return False
    return True


def download_mux(playback_id, playback_token, out_path):
    """Descarga un HLS de Mux con yt-dlp + Referer skool.com."""
    hls_url = f"https://stream.mux.com/{playback_id}.m3u8?token={playback_token}"
    cmd = [
        "yt-dlp", "--no-warnings",
        "--add-header", "Referer:https://www.skool.com/",
        "--add-header", "Origin:https://www.skool.com",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", str(out_path),
        hls_url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        last = res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "sin output"
        print(f"  ✗ yt-dlp (mux) falló: {last}")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Subcarpeta dentro de downloaded/skool/")
    ap.add_argument("--start", type=int, default=None, help="Forzar secuencial inicial")
    ap.add_argument("urls", nargs="+", help="URLs de Skool con ?md=")
    args = ap.parse_args()

    out_dir = DOWNLOAD_DIR / args.dir
    out_dir.mkdir(parents=True, exist_ok=True)
    seq = args.start if args.start is not None else get_next_seq(out_dir)

    opener = open_authenticated()

    # Cachear índice del classroom de la primera carga
    index_cache = {}
    ok = fail = 0

    for i, url in enumerate(args.urls, 1):
        parsed = urlparse(url)
        classroom_key = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Para cualquier visita, traemos índice + mux_video específico de la URL
        # (el cache solo evita recomputar el índice si el classroom es el mismo y
        # ya cubre la lección; el mux_video sí cambia por URL)
        if classroom_key not in index_cache:
            print(f"[{i}/{len(args.urls)}] Cargando classroom {parsed.path}...")
            index, mux_video = fetch_lesson_data(opener, url)
            index_cache[classroom_key] = index
        else:
            index = index_cache[classroom_key]
            mux_video = None  # se re-obtendrá si es Mux

        md = get_md(url)
        lesson = index.get(md)

        # Si la lección no está en el cache, recargamos esta URL específica
        if not lesson:
            fresh_index, mux_video = fetch_lesson_data(opener, url)
            index_cache[classroom_key].update(fresh_index)
            lesson = fresh_index.get(md)

        if not lesson:
            print(f"  ✗ md={md} no encontrado en classroom")
            fail += 1
            continue

        title = sanitize(lesson["title"])
        out_path = out_dir / f"{seq:02d}_{title}.mp4"
        print(f"[{i}/{len(args.urls)}] {seq:02d}_{title}")

        # Decidir el método de descarga
        if lesson["videoLink"]:
            print(f"      → embed: {lesson['videoLink']}")
            success = download_embed(lesson["videoLink"], out_path)
        elif lesson["videoId"]:
            # Necesitamos el mux_video de esta lección — recargar URL específica
            if mux_video is None or not mux_video.get("playbackId"):
                _, mux_video = fetch_lesson_data(opener, url)
            if not mux_video or not mux_video.get("playbackToken"):
                print(f"  ✗ no se obtuvo playbackToken de Mux para md={md}")
                fail += 1
                seq += 1
                continue
            print(f"      → mux: {mux_video['playbackId']}")
            success = download_mux(mux_video["playbackId"], mux_video["playbackToken"], out_path)
        else:
            print("  ✗ lección sin videoLink ni videoId")
            fail += 1
            seq += 1
            continue

        if success:
            print(f"  ✓ {out_path.name}")
            ok += 1
        else:
            fail += 1
        seq += 1

    print()
    print(f"Resumen: {ok} OK, {fail} fail. Carpeta: {out_dir}")


if __name__ == "__main__":
    main()
