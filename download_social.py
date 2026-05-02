#!/usr/bin/env python3
"""
download_social.py — Descarga contenido de Instagram y Facebook
usando cookies de sesión del usuario.

Soporta: posts, carruseles, reels, stories, highlights, perfiles completos.
NO soporta: IGTV (excluido por decisión del usuario).

Motor: gallery-dl (principal) + yt-dlp (fallback para videos).
Cookies: formato Netscape en ../download-multimedia/cookies/

Uso:
    python download_social.py [opciones] URL1 [URL2 ...]

Ejemplos:
    python download_social.py https://instagram.com/p/SHORTCODE/
    python download_social.py --limit 20 https://instagram.com/usuario/
    python download_social.py --include stories,highlights https://instagram.com/usuario/
    python download_social.py --yes --limit 10 https://instagram.com/usuario/
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


# ─── Rutas ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MULTIMEDIA_ROOT = PROJECT_ROOT.parent / "download-multimedia"
COOKIES_DIR = MULTIMEDIA_ROOT / "cookies"
OUTPUT_ROOT = PROJECT_ROOT / "downloaded"

COOKIES_FILES = {
    "instagram": COOKIES_DIR / "instagram.com_cookies.txt",
    "facebook": COOKIES_DIR / "facebook.com_cookies.txt",
}


# ─── Detección de plataforma y tipo ───────────────────────────────────────────
def detect_platform(url: str) -> str | None:
    host = urlparse(url).netloc.lower().lstrip("www.")
    if "instagram.com" in host:
        return "instagram"
    if any(d in host for d in ("facebook.com", "fb.com", "fb.watch")):
        return "facebook"
    return None


def detect_type(url: str, platform: str) -> str:
    """Detecta tipo de contenido por patrón de URL."""
    path = urlparse(url).path.rstrip("/")

    if platform == "instagram":
        if re.search(r"/p/[^/]+", path):
            return "post"
        if re.search(r"/reel/[^/]+", path):
            return "reel"
        if re.search(r"/stories/highlights/", path) or re.search(r"/highlights/", path):
            return "highlights"
        if re.search(r"/stories/[^/]+", path):
            return "story"
        if re.search(r"/tv/[^/]+", path):
            return "igtv"
        # /<username>/ → perfil
        parts = [p for p in path.split("/") if p]
        if len(parts) == 1 and parts[0] not in ("explore", "accounts", "direct"):
            return "profile"
        return "unknown"

    if platform == "facebook":
        if "/posts/" in path or "/photos/" in path:
            return "post"
        if "/videos/" in path or "/reel/" in path or "fb.watch" in url:
            return "video"
        if "/stories/" in path:
            return "story"
        parts = [p for p in path.split("/") if p]
        if len(parts) == 1:
            return "profile"
        return "unknown"

    return "unknown"


def extract_username(url: str, platform: str) -> str:
    """Saca el @username de una URL para nombrar carpetas."""
    path = urlparse(url).path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "unknown"

    if platform == "instagram":
        if parts[0] in ("p", "reel", "tv", "explore"):
            return "unknown"
        if parts[0] == "stories" and len(parts) >= 2:
            return parts[1] if parts[1] != "highlights" else "highlights"
        return parts[0]

    if platform == "facebook":
        return parts[0]

    return "unknown"


# ─── Validaciones ─────────────────────────────────────────────────────────────
def check_cookies(platform: str) -> Path:
    """Valida que el archivo de cookies exista y no esté vacío."""
    cookie_file = COOKIES_FILES[platform]
    if not cookie_file.exists():
        print(f"\n❌ No se encontró el archivo de cookies para {platform}.")
        print(f"   Esperado: {cookie_file}")
        print(f"\n   Cómo exportar:")
        print(f"   1. Inicia sesión en {platform}.com en Chrome")
        print(f"   2. Instala extensión 'Get cookies.txt LOCALLY'")
        print(f"   3. Click en la extensión → Export As → Netscape")
        print(f"   4. Guarda como: {cookie_file.name}")
        print(f"   5. Colócalo en: {COOKIES_DIR}/")
        sys.exit(1)

    if cookie_file.stat().st_size < 100:
        print(f"\n⚠️  El archivo {cookie_file.name} parece vacío o corrupto.")
        sys.exit(1)

    return cookie_file


def check_gallery_dl():
    if shutil.which("gallery-dl") is None:
        print("\n❌ gallery-dl no está instalado.")
        print("   Instala con: pip install gallery-dl")
        sys.exit(1)


# ─── Conteo de posts (para confirmación interactiva) ──────────────────────────
def count_profile_posts(url: str, cookies: Path, platform: str) -> int | None:
    """Cuenta posts de un perfil sin descargar (solo metadata)."""
    if platform != "instagram":
        return None
    try:
        result = subprocess.run(
            [
                "gallery-dl",
                "--cookies", str(cookies),
                "--simulate",
                "--print", "{shortcode}",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return None
        return len([l for l in result.stdout.splitlines() if l.strip()])
    except (subprocess.TimeoutExpired, Exception):
        return None


def confirm_profile_download(url: str, cookies: Path, platform: str, username: str) -> int | None:
    """Pregunta interactiva: cuántos posts bajar. Retorna límite (0 = todos) o None si cancela."""
    print(f"\n📊 Contando posts de @{username}…", flush=True)
    count = count_profile_posts(url, cookies, platform)

    if count is None:
        msg = f"No pude contar exactamente. ¿Cuántos posts descargas? [todos/N/cancelar]"
    else:
        msg = f"@{username} tiene aprox. {count} posts. ¿Cuántos descargas? [todos/N/cancelar]"

    print(f"\n{msg}")
    answer = input("> ").strip().lower()

    if not answer or answer in ("c", "cancel", "cancelar", "n", "no"):
        print("Cancelado.")
        return None
    if answer in ("todos", "all", "todo", "*"):
        return 0
    if answer.isdigit():
        return int(answer)

    print(f"Respuesta no entendida ('{answer}'). Cancelado.")
    return None


# ─── Construcción del comando gallery-dl ──────────────────────────────────────
def build_gallerydl_cmd(
    url: str,
    platform: str,
    cookies: Path,
    output_dir: Path,
    limit: int | None = None,
    since: str | None = None,
) -> list[str]:
    cmd = [
        "gallery-dl",
        "--cookies", str(cookies),
        "--directory", str(output_dir),
        "--no-mtime",
    ]

    if limit and limit > 0:
        cmd += ["--range", f"1-{limit}"]

    if since:
        try:
            d = datetime.strptime(since, "%Y-%m-%d")
            cmd += ["--filter", f"date >= datetime({d.year},{d.month},{d.day})"]
        except ValueError:
            print(f"⚠️  --since '{since}' no es fecha válida (YYYY-MM-DD). Ignorando.")

    cmd.append(url)
    return cmd


def run_command(cmd: list[str], label: str) -> bool:
    print(f"\n▶  {label}")
    print(f"   {' '.join(cmd[:3])} … {cmd[-1]}")
    result = subprocess.run(cmd)
    return result.returncode == 0


# ─── URLs auxiliares para stories/highlights ──────────────────────────────────
def stories_url(username: str, platform: str) -> str:
    if platform == "instagram":
        return f"https://www.instagram.com/stories/{username}/"
    return ""


def highlights_url(username: str, platform: str) -> str:
    if platform == "instagram":
        return f"https://www.instagram.com/{username}/"
    return ""


# ─── Post-procesamiento: conversión VP9 → H.264 ───────────────────────────────
def convert_vp9_to_h264(file_path: Path) -> bool:
    """Si el .mp4 está en VP9, lo recodifica a H.264 (compatible con QuickTime)."""
    if not file_path.exists() or file_path.suffix.lower() != ".mp4":
        return False
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        return False

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
             str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
        codec = result.stdout.strip().lower()
    except Exception:
        return False

    if codec != "vp9":
        return False

    print(f"   🎞️  VP9 detectado en {file_path.name} → convirtiendo a H.264…")
    temp_path = file_path.with_name(file_path.stem + ".h264.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(file_path),
             "-c:v", "libx264", "-preset", "fast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart",
             "-loglevel", "error",
             str(temp_path)],
            check=True, timeout=600,
        )
        file_path.unlink()
        temp_path.rename(file_path)
        print(f"   ✅ Convertido: {file_path.name}")
        return True
    except Exception as e:
        print(f"   ⚠️  Falló conversión de {file_path.name}: {e}")
        if temp_path.exists():
            temp_path.unlink()
        return False


def post_process_directory(directory: Path) -> int:
    """Recorre videos del directorio y convierte VP9 a H.264 si aplica. Retorna # convertidos."""
    if not directory.exists():
        return 0
    converted = 0
    for mp4 in directory.rglob("*.mp4"):
        if convert_vp9_to_h264(mp4):
            converted += 1
    return converted


# ─── Foto de perfil ───────────────────────────────────────────────────────────
def download_profile_pic(username: str, platform: str, cookies: Path, user_dir: Path) -> bool:
    """Descarga la foto de perfil HD del usuario (solo Instagram por ahora)."""
    if platform != "instagram":
        print(f"   ⚠️  Foto de perfil no soportada para {platform}.")
        return False
    if username in ("unknown", "highlights"):
        print(f"   ⚠️  No pude detectar username para foto de perfil.")
        return False

    avatar_dir = user_dir / "avatar"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    avatar_url = f"https://www.instagram.com/{username}/avatar/"
    cmd = [
        "gallery-dl",
        "--cookies", str(cookies),
        "--directory", str(avatar_dir),
        "--no-mtime",
        avatar_url,
    ]
    return run_command(cmd, f"Descargando foto de perfil de @{username}")


# ─── Procesamiento principal ──────────────────────────────────────────────────
def process_url(url: str, args) -> bool:
    platform = detect_platform(url)
    if platform is None:
        print(f"\n⚠️  URL no reconocida (solo Instagram y Facebook): {url}")
        return False

    content_type = detect_type(url, platform)

    if content_type == "igtv":
        print(f"\n⚠️  IGTV no soportado por diseño. Saltando: {url}")
        return False

    if content_type == "unknown":
        print(f"\n⚠️  No pude detectar el tipo de contenido en: {url}")
        print(f"   Lo intentaré igualmente con gallery-dl.")

    cookies = check_cookies(platform)
    username = extract_username(url, platform)

    print(f"\n{'─' * 60}")
    print(f"🌐 Plataforma: {platform}")
    print(f"📦 Tipo:       {content_type}")
    print(f"👤 Usuario:    @{username}")
    print(f"🔗 URL:        {url}")

    domain_dir = OUTPUT_ROOT / f"{platform}.com"
    user_dir = domain_dir / f"@{username}"
    today = datetime.now().strftime("%Y-%m-%d")

    if content_type == "profile":
        target_dir = user_dir / f"{today}_perfil"
    elif content_type in ("post", "reel"):
        target_dir = user_dir / f"{today}_{content_type}"
    elif content_type == "story":
        target_dir = user_dir / f"{today}_story"
    elif content_type == "highlights":
        target_dir = user_dir / f"{today}_highlights"
    else:
        target_dir = user_dir / f"{today}"

    target_dir.mkdir(parents=True, exist_ok=True)

    # Confirmación interactiva en perfil
    limit = args.limit
    if content_type == "profile" and limit is None and not args.yes:
        result = confirm_profile_download(url, cookies, platform, username)
        if result is None:
            return False
        limit = result

    cmd = build_gallerydl_cmd(
        url=url,
        platform=platform,
        cookies=cookies,
        output_dir=target_dir,
        limit=limit,
        since=args.since,
    )

    ok = run_command(cmd, f"Descargando {content_type} de @{username}")

    if not ok:
        print(f"\n❌ gallery-dl falló para {url}")
        return False

    print(f"\n✅ Descargado en: {target_dir}")

    # Post-proceso: convertir VP9 → H.264 para compatibilidad con QuickTime
    converted = post_process_directory(target_dir)
    if converted:
        print(f"   🎬 {converted} video(s) convertido(s) a H.264.")

    # Foto de perfil (si se pidió)
    if getattr(args, "profile_pic", False):
        download_profile_pic(username, platform, cookies, user_dir)

    # Stories y highlights opcionales (solo si se pidieron explícito)
    if content_type == "profile" and args.include:
        extras = [e.strip().lower() for e in args.include.split(",")]

        if "stories" in extras and platform == "instagram":
            extras_url = stories_url(username, platform)
            extras_dir = user_dir / f"{today}_stories"
            extras_dir.mkdir(parents=True, exist_ok=True)
            extras_cmd = build_gallerydl_cmd(
                extras_url, platform, cookies, extras_dir
            )
            run_command(extras_cmd, f"Descargando stories de @{username}")
            post_process_directory(extras_dir)

        if "highlights" in extras and platform == "instagram":
            # gallery-dl extrae highlights pasando la URL del perfil con flag específico
            extras_dir = user_dir / f"{today}_highlights"
            extras_dir.mkdir(parents=True, exist_ok=True)
            extras_cmd = [
                "gallery-dl",
                "--cookies", str(cookies),
                "--directory", str(extras_dir),
                "--no-mtime",
                f"https://www.instagram.com/{username}/highlights/",
            ]
            run_command(extras_cmd, f"Descargando highlights de @{username}")
            post_process_directory(extras_dir)

    return True


def parse_args():
    parser = argparse.ArgumentParser(
        description="Descarga contenido de Instagram y Facebook con cookies de sesión.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("urls", nargs="+", help="URLs a descargar (1 o más)")
    parser.add_argument(
        "--type",
        choices=["auto", "post", "reel", "story", "highlights", "profile"],
        default="auto",
        help="Forzar tipo de contenido (default: auto-detección)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Límite de posts en perfil (0 = todos). Si se omite y es perfil, pregunta interactivo.",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Solo posts desde fecha (formato YYYY-MM-DD)",
    )
    parser.add_argument(
        "--include",
        type=str,
        default=None,
        help="Extras al bajar perfil. Lista separada por comas: stories,highlights",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="No preguntar confirmación (modo no-interactivo)",
    )
    parser.add_argument(
        "--profile-pic",
        action="store_true",
        help="Descargar también la foto de perfil HD del usuario (solo Instagram)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    check_gallery_dl()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"\n{'═' * 60}")
    print(f"🎬 download-social — {len(args.urls)} URL(s)")
    print(f"{'═' * 60}")

    successes = 0
    for url in args.urls:
        if process_url(url, args):
            successes += 1

    print(f"\n{'═' * 60}")
    print(f"📊 Resumen: {successes}/{len(args.urls)} URLs descargadas")
    print(f"📂 Output:  {OUTPUT_ROOT}")
    print(f"{'═' * 60}\n")

    sys.exit(0 if successes == len(args.urls) else 1)


if __name__ == "__main__":
    main()
