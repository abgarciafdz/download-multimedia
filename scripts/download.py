#!/usr/bin/env python3
"""
Download Multimedia — Descarga imágenes y videos de cualquier URL.

Uso:
  Método 1 (clásico):       python download.py "URL1" "URL2"
  Método 2 (personalizado): python download.py --method 2 --folder MiCarpeta "URL1" "URL2"
"""

import sys
import os
import re
import hashlib
import subprocess
import time
import argparse
from urllib.parse import urlparse, urljoin
from pathlib import Path
from io import BytesIO

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from PIL import Image

# === CONFIGURACIÓN ===
MIN_IMAGE_SIZE = (300, 300)  # Ancho x Alto mínimo para filtrar miniaturas
IMAGE_FORMAT = "jpg"
VIDEO_FORMAT = "mp4"
DOWNLOAD_DIR = Path(__file__).parent / "downloaded"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Extensiones de imagen válidas
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg"}
# Extensiones de video válidas
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"}
# Dominios de video embebido
EMBED_DOMAINS = {"youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "streamable.com"}


def sanitize_filename(text, max_length=60):
    """Limpia un texto para usarlo como nombre de archivo."""
    # Quitar caracteres no válidos para filenames
    text = re.sub(r'[<>:"/\\|?*\n\r\t]', '', text)
    # Reemplazar espacios y caracteres especiales con guión bajo
    text = re.sub(r'[\s]+', '_', text.strip())
    # Quitar caracteres no ASCII excepto acentos comunes
    text = re.sub(r'[^\w\-_áéíóúñÁÉÍÓÚÑüÜ.]', '_', text)
    # Colapsar guiones bajos múltiples
    text = re.sub(r'_+', '_', text).strip('_')
    # Truncar
    if len(text) > max_length:
        text = text[:max_length].rstrip('_')
    return text or "sin-titulo"


def extract_page_title(soup, url):
    """Extrae el título de la página: primero H1, luego <title>, luego ID de URL."""
    # Intentar H1
    h1 = soup.find('h1')
    if h1 and h1.get_text(strip=True):
        return sanitize_filename(h1.get_text(strip=True))
    # Intentar <title>
    title = soup.find('title')
    if title and title.get_text(strip=True):
        raw = title.get_text(strip=True)
        # Quitar sufijos comunes tipo " - Sitio.com" o " | Sitio"
        raw = re.split(r'\s*[\-|–—]\s*(?=[^-|–—]*$)', raw)[0].strip()
        return sanitize_filename(raw)
    # Fallback: último segmento de la URL
    path = urlparse(url).path.rstrip('/')
    slug = path.split('/')[-1] if path else urlparse(url).netloc
    return sanitize_filename(slug) if slug else "descarga"


def get_domain_folder(url):
    """Genera nombre de carpeta a partir del dominio de la URL."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    return re.sub(r"[^a-zA-Z0-9\-.]", "-", domain).lower().rstrip("-")


def get_next_sequence(domain_folder):
    """Calcula el siguiente número secuencial dentro de la carpeta del dominio."""
    if not domain_folder.exists():
        return 1
    existing = sorted(
        [d for d in domain_folder.iterdir() if d.is_dir() and d.name.isdigit()],
        key=lambda d: int(d.name),
    )
    if not existing:
        return 1
    return int(existing[-1].name) + 1


def create_session(page_url=None):
    """Crea una sesión HTTP con reintentos, cookies y headers realistas."""
    session = requests.Session()
    # Reintentos automáticos en errores de servidor y conexión
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    # Headers base realistas
    session.headers.update(HEADERS)
    # Referer del sitio original
    if page_url:
        parsed = urlparse(page_url)
        session.headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        session.headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
    return session


def get_page_html(url):
    """Descarga el HTML de una página visitándola como un navegador real."""
    session = create_session(page_url=url)
    try:
        # Primera visita para obtener cookies
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text, session
    except requests.RequestException as e:
        print(f"  ✗ Error descargando {url}: {e}")
        return None, session


def extract_image_urls(soup, base_url):
    """Extrae todas las URLs de imágenes del HTML."""
    urls = set()

    # <img src="..."> y <img data-src="..."> (lazy loading)
    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy-src", "data-original", "data-srcset"]:
            val = img.get(attr)
            if val:
                # Si es srcset, tomar la URL más grande
                if "srcset" in attr:
                    parts = val.split(",")
                    for part in parts:
                        src = part.strip().split()[0]
                        if src:
                            urls.add(urljoin(base_url, src))
                else:
                    urls.add(urljoin(base_url, val))

    # <img srcset="...">
    for img in soup.find_all("img", srcset=True):
        parts = img["srcset"].split(",")
        # Tomar la versión más grande
        best = None
        best_size = 0
        for part in parts:
            tokens = part.strip().split()
            if len(tokens) >= 2:
                size_str = tokens[-1].replace("w", "").replace("x", "")
                try:
                    size = float(size_str)
                    if size > best_size:
                        best_size = size
                        best = tokens[0]
                except ValueError:
                    pass
            elif tokens:
                best = tokens[0]
        if best:
            urls.add(urljoin(base_url, best))

    # <picture> <source>
    for source in soup.find_all("source"):
        srcset = source.get("srcset")
        src = source.get("src")
        if srcset:
            parts = srcset.split(",")
            for part in parts:
                src_url = part.strip().split()[0]
                if src_url:
                    urls.add(urljoin(base_url, src_url))
        if src:
            urls.add(urljoin(base_url, src))

    # <meta property="og:image">
    for meta in soup.find_all("meta", property="og:image"):
        content = meta.get("content")
        if content:
            urls.add(urljoin(base_url, content))

    # <a href="..."> que apunten directamente a imágenes
    for a in soup.find_all("a", href=True):
        href = a["href"]
        parsed = urlparse(href)
        ext = Path(parsed.path).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            urls.add(urljoin(base_url, href))

    # CSS background-image en atributos style
    for tag in soup.find_all(style=True):
        style = tag["style"]
        bg_urls = re.findall(r'url\(["\']?(.*?)["\']?\)', style)
        for bg_url in bg_urls:
            if any(ext in bg_url.lower() for ext in IMAGE_EXTENSIONS):
                urls.add(urljoin(base_url, bg_url))

    # Filtrar URLs no válidas
    filtered = set()
    for url in urls:
        if url.startswith(("http://", "https://")) and not url.endswith(".svg"):
            # Excluir íconos y assets comunes
            lower = url.lower()
            skip_patterns = [
                "favicon", "icon", "logo", "sprite", "pixel",
                "tracking", "analytics", "badge", "button",
                "1x1", "spacer", "blank", "transparent",
                "avatar", "emoji", "smiley",
            ]
            if not any(p in lower for p in skip_patterns):
                filtered.add(url)

    return filtered


def extract_video_urls(soup, base_url):
    """Extrae URLs de videos directos y embebidos."""
    direct_videos = set()
    embed_videos = set()

    # <video src="..."> y <video> <source src="...">
    for video in soup.find_all("video"):
        src = video.get("src")
        if src:
            direct_videos.add(urljoin(base_url, src))
        for source in video.find_all("source"):
            src = source.get("src")
            if src:
                direct_videos.add(urljoin(base_url, src))

    # <iframe> con videos embebidos
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src") or iframe.get("data-src")
        if src:
            full_url = urljoin(base_url, src)
            parsed = urlparse(full_url)
            domain = parsed.netloc.replace("www.", "")
            if any(ed in domain for ed in EMBED_DOMAINS):
                # Limpiar URL de embed a URL normal
                clean_url = clean_embed_url(full_url)
                if clean_url:
                    embed_videos.add(clean_url)

    # <a href="..."> que apunten a videos
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        ext = Path(parsed.path).suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            direct_videos.add(full_url)

    return direct_videos, embed_videos


def clean_embed_url(url):
    """Convierte URL de embed a URL descargable."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")

    if "youtube.com" in domain:
        # /embed/VIDEO_ID -> https://www.youtube.com/watch?v=VIDEO_ID
        match = re.search(r"/embed/([a-zA-Z0-9_-]+)", parsed.path)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
    elif "youtu.be" in domain:
        return url
    elif "vimeo.com" in domain:
        match = re.search(r"/video/(\d+)", parsed.path)
        if match:
            return f"https://vimeo.com/{match.group(1)}"
        return url
    elif "dailymotion.com" in domain:
        match = re.search(r"/embed/video/([a-zA-Z0-9]+)", parsed.path)
        if match:
            return f"https://www.dailymotion.com/video/{match.group(1)}"

    return url


def is_large_enough(image_data):
    """Verifica que la imagen sea mayor al tamaño mínimo."""
    try:
        img = Image.open(BytesIO(image_data))
        w, h = img.size
        return w >= MIN_IMAGE_SIZE[0] and h >= MIN_IMAGE_SIZE[1]
    except Exception:
        return False


def download_image(url, folder, counter, session=None, title_prefix=None):
    """Descarga una imagen y la guarda como JPG."""
    try:
        s = session or requests
        response = s.get(url, timeout=REQUEST_TIMEOUT, stream=True)
        response.raise_for_status()

        content = response.content
        if not content or len(content) < 1000:
            return False

        if not is_large_enough(content):
            return False

        # Nombre con título de página
        prefix = f"{title_prefix}_" if title_prefix else "imagen-"
        filename = f"{prefix}{counter:02d}.{IMAGE_FORMAT}"

        # Convertir a JPG
        try:
            img = Image.open(BytesIO(content))
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            filepath = folder / filename
            img.save(filepath, "JPEG", quality=90)
            print(f"  ✓ {filename} ({img.size[0]}x{img.size[1]})")
            return True
        except Exception:
            parsed = urlparse(url)
            ext = Path(parsed.path).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                filename = f"{prefix}{counter:02d}{ext}"
                filepath = folder / filename
                filepath.write_bytes(content)
                print(f"  ✓ {filename}")
                return True
            return False

    except requests.RequestException:
        return False


def download_direct_video(url, folder, counter, session=None, title_prefix=None):
    """Descarga un video directo (no embebido). Reintenta si falla."""
    prefix = f"{title_prefix}_" if title_prefix else "video-"
    for attempt in range(MAX_RETRIES):
        try:
            s = session or requests
            response = s.get(url, timeout=120, stream=True)
            response.raise_for_status()

            filename = f"{prefix}{counter:02d}.{VIDEO_FORMAT}"
            filepath = folder / filename

            total = 0
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    total += len(chunk)

            if total < 10000:
                filepath.unlink()
                return False

            size_mb = total / (1024 * 1024)
            print(f"  ✓ {filename} ({size_mb:.1f} MB)")
            return True

        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
            continue
    return False


def download_embed_video(url, folder, counter, page_url=None, title_prefix=None):
    """Descarga video embebido usando yt-dlp."""
    prefix = f"{title_prefix}_" if title_prefix else "video-"
    venv_ytdlp = Path(__file__).parent / "venv" / "bin" / "yt-dlp"
    ytdlp_cmd = str(venv_ytdlp) if venv_ytdlp.exists() else "yt-dlp"

    cmd = [
        ytdlp_cmd,
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(folder / f"{prefix}{counter:02d}.%(ext)s"),
        "--no-playlist",
        "--quiet",
        "--user-agent", USER_AGENT,
    ]
    if page_url:
        parsed = urlparse(page_url)
        cmd.extend(["--referer", f"{parsed.scheme}://{parsed.netloc}/"])
    cmd.append(url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            for f in folder.iterdir():
                if f.name.startswith(f"{prefix}{counter:02d}"):
                    size_mb = f.stat().st_size / (1024 * 1024)
                    print(f"  ✓ {f.name} ({size_mb:.1f} MB)")
                    return True
        else:
            error = result.stderr.strip()
            if error:
                print(f"  ✗ No se pudo descargar video de {url}")
                print(f"    Razón: {error[:100]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  ✗ Timeout descargando video de {url}")
        return False
    except FileNotFoundError:
        print(f"  ✗ yt-dlp no encontrado. Instalar con: pip install yt-dlp")
        return False


def deduplicate_urls(urls):
    """Elimina URLs duplicadas que apuntan al mismo recurso."""
    seen = set()
    unique = []
    for url in urls:
        # Normalizar URL para comparación
        parsed = urlparse(url)
        # Quitar parámetros de tracking comunes
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean not in seen:
            seen.add(clean)
            unique.append(url)
    return unique


def process_url(url, method=1, custom_folder=None, seen_urls=None):
    """Procesa una URL completa: descarga HTML, extrae y descarga multimedia.

    Args:
        method: 1 = clásico (dominio/NN/), 2 = personalizado (dominio/carpeta/videos/ y jpg/)
        custom_folder: nombre de carpeta personalizada (solo método 2)
        seen_urls: set de URLs ya descargadas para evitar duplicados
    """
    if seen_urls is None:
        seen_urls = set()

    print(f"\n{'='*60}")
    print(f"Procesando: {url}")
    print(f"{'='*60}")

    domain = get_domain_folder(url)
    domain_folder = DOWNLOAD_DIR / domain

    if method == 2 and custom_folder:
        # Método 2: dominio/carpeta/videos/ y dominio/carpeta/jpg/
        base = domain_folder / custom_folder
        vid_folder = base / "videos"
        img_folder = base / "jpg"
        vid_folder.mkdir(parents=True, exist_ok=True)
        img_folder.mkdir(parents=True, exist_ok=True)
        print(f"Carpeta: {base}")
    else:
        # Método 1: dominio/01/, 02/, etc.
        domain_folder.mkdir(parents=True, exist_ok=True)
        seq = get_next_sequence(domain_folder)
        folder = domain_folder / f"{seq:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        vid_folder = folder
        img_folder = folder
        print(f"Carpeta: {folder}")

    # Descargar HTML
    result = get_page_html(url)
    html, session = result
    if not html:
        return 0, 0

    soup = BeautifulSoup(html, "lxml")

    # Extraer título de la página para nomenclatura
    title_prefix = extract_page_title(soup, url)

    # Extraer URLs
    image_urls = extract_image_urls(soup, url)
    direct_videos, embed_videos = extract_video_urls(soup, url)

    print(f"Título: {title_prefix}")
    print(f"Encontradas: {len(image_urls)} imágenes, "
          f"{len(direct_videos)} videos directos, "
          f"{len(embed_videos)} videos embebidos")

    # Calcular siguiente número secuencial en carpetas destino
    def next_num(directory):
        nums = []
        for f in directory.iterdir():
            m = re.search(r'_(\d+)\.\w+$', f.name)
            if m:
                nums.append(int(m.group(1)))
        return max(nums) + 1 if nums else 1

    # Descargar imágenes
    img_count = 0
    if image_urls:
        print(f"\n--- Descargando imágenes ---")
        unique_images = deduplicate_urls(image_urls)
        img_num = next_num(img_folder)
        for img_url in unique_images:
            clean = img_url.split('?')[0]
            if clean in seen_urls:
                continue
            if download_image(img_url, img_folder, img_num, session=session, title_prefix=title_prefix):
                seen_urls.add(clean)
                img_count += 1
                img_num += 1

    # Descargar videos directos
    vid_count = 0
    if direct_videos:
        print(f"\n--- Descargando videos directos ---")
        vid_num = next_num(vid_folder)
        for vid_url in direct_videos:
            clean = vid_url.split('?')[0]
            if clean in seen_urls:
                print(f"  [SKIP] Duplicado: {clean[-50:]}")
                continue
            if download_direct_video(vid_url, vid_folder, vid_num, session=session, title_prefix=title_prefix):
                seen_urls.add(clean)
                vid_count += 1
                vid_num += 1

    # Descargar videos embebidos
    if embed_videos:
        print(f"\n--- Descargando videos embebidos ---")
        if not direct_videos:
            vid_num = next_num(vid_folder)
        for vid_url in embed_videos:
            clean = vid_url.split('?')[0]
            if clean in seen_urls:
                continue
            if download_embed_video(vid_url, vid_folder, vid_num, page_url=url, title_prefix=title_prefix):
                seen_urls.add(clean)
                vid_count += 1
                vid_num += 1

    # Limpiar carpetas vacías (solo método 1)
    if method == 1 and img_count == 0 and vid_count == 0:
        try:
            folder.rmdir()
            domain_folder.rmdir()
        except OSError:
            pass
        print(f"\nNo se encontró multimedia válida en esta URL.")

    return img_count, vid_count


def main():
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(description="Download Multimedia")
    parser.add_argument("urls", nargs="+", help="URLs a descargar")
    parser.add_argument("--method", type=int, choices=[1, 2], default=1,
                        help="1=clásico (dominio/NN/), 2=personalizado (carpeta/videos/ y jpg/)")
    parser.add_argument("--folder", type=str, default=None,
                        help="Nombre de carpeta personalizada (solo método 2)")
    args = parser.parse_args()

    if args.method == 2 and not args.folder:
        print("Error: --folder es requerido con --method 2")
        sys.exit(1)

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    total_images = 0
    total_videos = 0
    seen_urls = set()  # Anti-duplicados global

    for url in args.urls:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        imgs, vids = process_url(url, method=args.method, custom_folder=args.folder,
                                 seen_urls=seen_urls)
        total_images += imgs
        total_videos += vids

    # Resumen final
    print(f"\n{'='*60}")
    print(f"RESUMEN")
    print(f"{'='*60}")
    print(f"URLs procesadas:      {len(args.urls)}")
    print(f"Imágenes descargadas: {total_images}")
    print(f"Videos descargados:   {total_videos}")
    print(f"Duplicados omitidos:  {len(seen_urls) - total_images - total_videos}")
    if args.method == 2:
        domain = get_domain_folder(args.urls[0])
        print(f"Guardado en: {DOWNLOAD_DIR / domain / args.folder}")
    else:
        print(f"Guardado en: {DOWNLOAD_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
