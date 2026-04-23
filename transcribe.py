#!/usr/bin/env python3
"""
transcribe.py — Transcribe videos locales usando Whisper.

Uso:
    python transcribe.py "video.mp4"
    python transcribe.py --model small "video.mp4"
    python transcribe.py "v1.mp4" "v2.mp4" "v3.mp4"
    python transcribe.py --language es "video.mp4"

Genera <nombre_video>_transcripcion.md junto al archivo .mp4.
"""

import argparse
import os
import re
import sys
from pathlib import Path

LANG_NAMES = {
    "es": "español",
    "en": "inglés",
    "pt": "portugués",
    "fr": "francés",
    "it": "italiano",
    "de": "alemán",
}

MIN_FILE_SIZE = 1024  # bytes


def format_duration(seconds: float) -> str:
    """Formatea segundos como HH:MM:SS (si >= 1h) o MM:SS."""
    total = int(round(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours >= 1:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def clean_and_paragraphize(text: str, sentences_per_paragraph: int = 4) -> str:
    """Colapsa espacios, divide en oraciones y agrupa en párrafos."""
    # Colapsar espacios múltiples (incluye saltos de línea y tabs)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    # Dividir por .!? seguido de espacio, conservando el signo
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentences = [p.strip() for p in parts if p.strip()]

    paragraphs = []
    for i in range(0, len(sentences), sentences_per_paragraph):
        chunk = " ".join(sentences[i : i + sentences_per_paragraph])
        paragraphs.append(chunk)

    return "\n\n".join(paragraphs)


def get_duration_from_result(result: dict) -> float:
    """Obtiene la duración desde el último segmento de Whisper."""
    segments = result.get("segments") or []
    if not segments:
        return 0.0
    try:
        return float(segments[-1].get("end", 0.0))
    except (TypeError, ValueError):
        return 0.0


def transcribe_video(model, video_path: Path, language: str | None, model_name: str) -> bool:
    """Transcribe un video y genera el .md. Retorna True si tuvo éxito."""
    try:
        kwargs = {}
        if language:
            kwargs["language"] = language
        result = model.transcribe(str(video_path), **kwargs)
    except Exception as exc:
        print(f"  Error: {exc}")
        return False

    text = (result.get("text") or "").strip()
    detected_lang_code = language or result.get("language") or ""
    lang_display = LANG_NAMES.get(detected_lang_code, detected_lang_code or "desconocido")
    duration_str = format_duration(get_duration_from_result(result))
    body = clean_and_paragraphize(text)
    stem = video_path.stem

    md_path = video_path.with_name(f"{stem}_transcripcion.md")
    md_content = (
        f"# Transcripción: {stem}\n\n"
        f"**Duración:** {duration_str}\n"
        f"**Idioma detectado:** {lang_display}\n"
        f"**Modelo Whisper:** {model_name}\n\n"
        f"---\n\n"
        f"{body}\n"
    )

    try:
        md_path.write_text(md_content, encoding="utf-8")
    except Exception as exc:
        print(f"  Error al escribir {md_path}: {exc}")
        return False

    print(f"  OK -> {md_path.name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe videos locales a Markdown usando Whisper."
    )
    parser.add_argument(
        "videos",
        nargs="+",
        help="Rutas de videos a transcribir (uno o varios).",
    )
    parser.add_argument(
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Modelo Whisper a usar (default: base).",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Código de idioma ISO para forzar (ej: es, en, pt). Opcional.",
    )
    args = parser.parse_args()

    # Import tardío para poder validar y dar mensaje claro si falta
    try:
        import whisper  # type: ignore
    except ImportError:
        print(
            "Error: el paquete 'openai-whisper' no está instalado.\n"
            "Instálalo con: pip install openai-whisper"
        )
        return 1

    # Pre-validación: existencia y tamaño
    queue: list[Path] = []
    skipped: list[str] = []
    for raw in args.videos:
        p = Path(raw).expanduser()
        if not p.exists() or not p.is_file():
            print(f"✗ No existe: {raw}")
            skipped.append(raw)
            continue
        try:
            size = p.stat().st_size
        except OSError as exc:
            print(f"✗ No se pudo leer: {raw} ({exc})")
            skipped.append(raw)
            continue
        if size < MIN_FILE_SIZE:
            print(f"✗ Archivo muy pequeño o corrupto: {raw}")
            skipped.append(raw)
            continue
        queue.append(p)

    total = len(args.videos)

    if not queue:
        print("\nNo hay videos válidos para transcribir.")
        print(f"Transcritos: 0/{total}")
        if skipped:
            print("Fallaron:")
            for s in skipped:
                print(f"  - {s}")
        return 1

    # Cargar modelo una sola vez
    print(f"Cargando modelo Whisper: {args.model}...")
    try:
        model = whisper.load_model(args.model)
    except Exception as exc:
        print(f"Error al cargar el modelo '{args.model}': {exc}")
        return 1

    success = 0
    failed: list[str] = list(skipped)

    for idx, video_path in enumerate(queue, start=1):
        print(f"[{idx}/{total}] {video_path.name}")
        if transcribe_video(model, video_path, args.language, args.model):
            success += 1
        else:
            failed.append(str(video_path))

    # Resumen final
    print()
    print(f"Transcritos: {success}/{total}")
    if failed:
        print("Fallaron:")
        for f in failed:
            print(f"  - {f}")

    return 0 if success == total else 2


if __name__ == "__main__":
    sys.exit(main())
