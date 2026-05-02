#!/usr/bin/env python3
"""
Wrapper sobre export_page.py específico para stacks de Skool ya descargados
con download_skool.py.

Itera URLs en el orden dado y renombra cada HTML generado al mismo nombre
que el video correspondiente (NN_Titulo.html ↔ NN_Titulo.mp4) dentro de la
carpeta del stack.

Uso:
  python scripts/export_skool_videos.py --dir CARPETA URL1 URL2 ...

CARPETA es relativa a downloaded/skool/ (ej: idall-lite/01-start-here).
Las URLs deben pasarse en el MISMO orden que los videos (01, 02, ...).
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOWNLOAD_DIR = ROOT / "downloaded" / "skool"
EXPORT_PAGE = ROOT / "scripts" / "export_page.py"


def list_videos(folder):
    """Lista videos en orden secuencial por prefijo NN_."""
    if not folder.exists():
        return []
    videos = []
    for f in folder.iterdir():
        m = re.match(r"^(\d{2})_(.+)\.mp4$", f.name)
        if m:
            videos.append((int(m.group(1)), m.group(2), f))
    return sorted(videos, key=lambda x: x[0])


def export_one(url, tmp_dir):
    """Llama export_page.py con --output-dir tmp_dir, devuelve el HTML generado."""
    before = set(p.name for p in Path(tmp_dir).iterdir())
    cmd = [
        sys.executable, str(EXPORT_PAGE),
        "--format", "html",
        "--output-dir", str(tmp_dir),
        url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  ✗ export_page falló: {res.stderr.strip().splitlines()[-1] if res.stderr.strip() else 'sin output'}")
        return None
    after = set(p.name for p in Path(tmp_dir).iterdir())
    new_files = after - before
    if not new_files:
        print(f"  ✗ no se generó HTML")
        return None
    new_html = next(iter(new_files))
    return Path(tmp_dir) / new_html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Carpeta relativa a downloaded/skool/")
    ap.add_argument("urls", nargs="+", help="URLs en el mismo orden que los videos NN_")
    args = ap.parse_args()

    folder = DOWNLOAD_DIR / args.dir
    if not folder.exists():
        print(f"✗ carpeta no existe: {folder}", file=sys.stderr)
        sys.exit(1)

    videos = list_videos(folder)
    if len(videos) != len(args.urls):
        print(f"⚠  {len(args.urls)} URLs vs {len(videos)} videos en la carpeta — los emparejo por índice")

    ok = fail = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, url in enumerate(args.urls):
            if i >= len(videos):
                print(f"[{i+1}/{len(args.urls)}] sin video correspondiente, salto")
                fail += 1
                continue
            seq, title, _ = videos[i]
            target = folder / f"{seq:02d}_{title}.html"
            print(f"[{i+1}/{len(args.urls)}] {seq:02d}_{title}")

            generated = export_one(url, tmp)
            if generated is None:
                fail += 1
                continue
            shutil.move(str(generated), str(target))
            print(f"  ✓ {target.name}")
            ok += 1

    print()
    print(f"Resumen: {ok} OK, {fail} fail. Carpeta: {folder}")


if __name__ == "__main__":
    main()
