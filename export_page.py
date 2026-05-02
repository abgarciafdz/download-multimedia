#!/usr/bin/env python3
"""
Export pages — exporta el contenido textual de páginas (con o sin login) a
HTML autocontenido o PDF. Pensado para lecciones de cursos online (Skool,
Teachable, masterclass.tradingmasivo.com) y artículos genéricos.

Características:
  - Reutiliza cookies en formato Netscape (cookies/<netloc>_cookies.txt).
  - Renderiza con Playwright (sirve para SPAs como Skool).
  - Skool: extrae lección desde __NEXT_DATA__ primero (robusto a cambios
    de CSS), fallback a selectores DOM, fallback final a trafilatura.
  - HTML autocontenido: imágenes embebidas en base64, CSS inline tipo
    "Reader Mode" (serif, max-width 700px).
  - PDF: generado con Playwright (mismo Chromium del venv).
  - Modo opcional --con-comentarios para incluir la discusión.

Uso:
  python scripts/export_page.py [URLS...] \\
      [--format html|pdf|ask]      # default: ask (pregunta interactivo)
      [--con-comentarios]          # default: False
      [--output-dir PATH]          # opcional
      [--timeout 60]               # segundos para wait_for_networkidle

Salida:
  downloaded/<netloc>/<slug-curso>/<slug-leccion>.html|pdf
"""

import argparse
import asyncio
import base64
import json
import re
import sys
import unicodedata
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
COOKIES_DIR = ROOT / "cookies"
DOWNLOAD_DIR = ROOT / "downloaded"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

IMG_MAX_EMBED_BYTES = 5 * 1024 * 1024
IMG_RECOMPRESS_BYTES = 2 * 1024 * 1024


# ─── Utilidades ────────────────────────────────────────────────────────────

def slugify(text, max_len=80):
    if not text:
        return "sin-titulo"
    s = unicodedata.normalize("NFD", text)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "sin-titulo"


def get_cookies_file(url):
    parsed = urlparse(url)
    f = COOKIES_DIR / f"{parsed.netloc}_cookies.txt"
    return f if f.exists() else None


def load_cookies_for_playwright(cookies_file):
    """Convierte un archivo Netscape a la lista de dicts que espera Playwright.

    Formato Netscape:
      [#HttpOnly_]domain\tinclude_subdomains\tpath\tsecure\texpiration\tname\tvalue
    """
    cookies = []
    with open(cookies_file) as f:
        for raw in f:
            line = raw.rstrip("\n")
            http_only = False
            if line.startswith("#HttpOnly_"):
                http_only = True
                line = line[len("#HttpOnly_"):]
            elif line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _flag, path, secure, expires, name, value = parts[:7]
            try:
                exp = int(expires)
            except ValueError:
                exp = -1
            cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "expires": exp,
                "httpOnly": http_only,
                "secure": secure.upper() == "TRUE",
            })
    return cookies


def extract_course_slug(url):
    """De https://www.skool.com/idall-lite-1529/classroom/... → 'idall-lite-1529'.

    Para otros sitios, devuelve el primer segmento no vacío de la ruta.
    """
    path = urlparse(url).path.strip("/")
    if not path:
        return "general"
    return slugify(path.split("/")[0])


# ─── ProseMirror JSON → HTML (formato de Skool y similares) ────────────────

# Acumulador global de tipos no reconocidos durante el parseo. Se reporta al
# final del export para que el usuario sepa qué se manejó con heurística (y si
# vale la pena agregar soporte explícito para esa plataforma).
_PROSEMIRROR_UNKNOWN_TYPES = set()


def prosemirror_to_html(raw):
    """Convierte ProseMirror JSON a HTML. Soporta:
      - Skool (`[v2]` prefix, tipos `unorderedList`, `listItem`, `desc`)
      - Notion-like (`bulletList`, `orderedList`)
      - Snake_case schemas (`bullet_list`, `ordered_list`, `list_item`)
      - Tablas (table, tableRow, tableCell, tableHeader)
      - Heurística: cualquier *List/*list → <ul>, *Item/*item → <li>
    """
    import html as html_lib
    if not raw or not isinstance(raw, str):
        return ""

    s = raw.strip()
    if s.startswith("[v"):
        end = s.find("]")
        if end != -1:
            s = s[end + 1:]
    s = s.strip()
    if not s:
        return ""

    try:
        nodes = json.loads(s)
    except json.JSONDecodeError:
        return ""

    if isinstance(nodes, dict):
        nodes = [nodes]

    def render_marks(text, marks):
        if not marks:
            return text
        out = text
        for mark in marks:
            mtype = mark.get("type")
            attrs = mark.get("attrs") or {}
            if mtype == "bold":
                out = f"<strong>{out}</strong>"
            elif mtype == "italic":
                out = f"<em>{out}</em>"
            elif mtype == "underline":
                out = f"<u>{out}</u>"
            elif mtype == "strike":
                out = f"<s>{out}</s>"
            elif mtype == "code":
                out = f"<code>{out}</code>"
            elif mtype == "link":
                href = attrs.get("href", "#")
                out = f'<a href="{html_lib.escape(href)}" target="_blank" rel="noopener">{out}</a>'
        return out

    def is_ordered_list(t):
        if not t:
            return False
        return t in ("orderedList", "ordered_list") or t.lower().startswith("ordered")

    def is_unordered_list(t):
        if not t:
            return False
        if t in ("bulletList", "unorderedList", "bullet_list", "unordered_list"):
            return True
        # Heurística: cualquier tipo que termine en "list" sin ser ordered
        lt = t.lower()
        return lt.endswith("list") and not lt.startswith("ordered")

    def is_list_item(t):
        if not t:
            return False
        return t in ("listItem", "list_item") or t.lower().endswith("item")

    def render_node(node):
        if not isinstance(node, dict):
            return ""
        ntype = node.get("type")
        attrs = node.get("attrs") or {}
        children = node.get("content") or []

        if ntype == "text":
            text = html_lib.escape(node.get("text", ""))
            return render_marks(text, node.get("marks") or [])

        inner = "".join(render_node(c) for c in children)

        # Bloques de texto
        if ntype == "paragraph":
            return f"<p>{inner}</p>" if inner.strip() else ""
        if ntype == "heading":
            level = max(1, min(6, int(attrs.get("level", 2))))
            return f"<h{level}>{inner}</h{level}>"
        if ntype == "blockquote":
            return f"<blockquote>{inner}</blockquote>"
        if ntype == "codeBlock":
            return f"<pre><code>{inner}</code></pre>"

        # Listas (con heurística para tipos desconocidos)
        if is_ordered_list(ntype):
            start = attrs.get("start", 1)
            start_attr = f' start="{start}"' if start and start != 1 else ""
            return f"<ol{start_attr}>{inner}</ol>"
        if is_unordered_list(ntype):
            return f"<ul>{inner}</ul>"
        if is_list_item(ntype):
            return f"<li>{inner}</li>"

        # Tablas
        if ntype == "table":
            return f"<table>{inner}</table>"
        if ntype in ("tableRow", "table_row"):
            return f"<tr>{inner}</tr>"
        if ntype in ("tableCell", "table_cell"):
            colspan = attrs.get("colspan")
            rowspan = attrs.get("rowspan")
            attrs_str = ""
            if colspan and colspan != 1: attrs_str += f' colspan="{colspan}"'
            if rowspan and rowspan != 1: attrs_str += f' rowspan="{rowspan}"'
            return f"<td{attrs_str}>{inner}</td>"
        if ntype in ("tableHeader", "table_header"):
            return f"<th>{inner}</th>"

        # Inline / atomic
        if ntype == "horizontalRule":
            return "<hr>"
        if ntype in ("hardBreak", "hard_break"):
            return "<br>"
        if ntype == "image":
            src = html_lib.escape(attrs.get("src", ""))
            alt = html_lib.escape(attrs.get("alt", ""))
            return f'<img src="{src}" alt="{alt}">'
        if ntype in ("embed", "iframe", "video"):
            src = attrs.get("src") or attrs.get("url") or ""
            if src:
                return f'<p><a href="{html_lib.escape(src)}" target="_blank" rel="noopener">{html_lib.escape(src)}</a></p>'
            return ""

        # Tipo desconocido: registrar y devolver el contenido interno
        # (mejor mostrar contenido que perderlo).
        if ntype:
            _PROSEMIRROR_UNKNOWN_TYPES.add(ntype)
        return inner

    return "".join(render_node(n) for n in nodes if isinstance(n, dict))


def collect_prosemirror_types(raw):
    """Recorre un ProseMirror JSON y devuelve el set de tipos usados.

    Usado por --inspect para diagnosticar sitios nuevos.
    """
    if not raw or not isinstance(raw, str):
        return set()
    s = raw.strip()
    if s.startswith("[v"):
        end = s.find("]")
        if end != -1:
            s = s[end + 1:]
    try:
        nodes = json.loads(s.strip())
    except (json.JSONDecodeError, ValueError):
        return set()
    if isinstance(nodes, dict):
        nodes = [nodes]
    types = set()
    def walk(n):
        if isinstance(n, dict):
            t = n.get("type")
            if t: types.add(t)
            for c in (n.get("content") or []):
                walk(c)
            for m in (n.get("marks") or []):
                mt = m.get("type") if isinstance(m, dict) else None
                if mt: types.add(f"mark:{mt}")
        elif isinstance(n, list):
            for c in n: walk(c)
    for n in nodes:
        walk(n)
    return types


# ─── Detección de sesión expirada ──────────────────────────────────────────

async def is_session_expired(page):
    final_url = page.url.lower()
    if "/login" in final_url or "/signin" in final_url:
        return True
    title = (await page.title()).lower()
    if title in ("log in", "sign in", "login", "iniciar sesión"):
        return True
    return False


# ─── Extracción de contenido (Skool) ───────────────────────────────────────

async def extract_skool_from_next_data(page):
    """Lee __NEXT_DATA__ y busca metadata.title + metadata.description (HTML)
    de la lección actual (identificada por ?md= si existe)."""
    try:
        raw = await page.evaluate(
            'document.getElementById("__NEXT_DATA__")?.textContent'
        )
    except Exception:
        raw = None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None

    md_id = None
    try:
        md_id = page.url.split("?md=", 1)[1].split("&")[0]
    except IndexError:
        pass

    candidates = []  # (id, title, body_html, video_link)

    def walk(obj):
        if isinstance(obj, dict):
            lid = obj.get("id")
            meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else None
            if lid and meta:
                title = (meta.get("title") or "").strip()
                # Skool guarda el cuerpo en `desc`. Mantenemos otros nombres
                # como fallback para sitios Next.js similares.
                body = (
                    meta.get("desc")
                    or meta.get("description")
                    or meta.get("text")
                    or meta.get("content")
                    or ""
                )
                video_link = meta.get("videoLink")
                if title or body or video_link:
                    candidates.append((lid, title, body, video_link))
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    if not candidates:
        return None

    def to_html(body):
        # Skool guarda `desc` como ProseMirror JSON (con prefijo "[v2]").
        # Si parece ser ese formato, conviértelo. Si no, devuelve tal cual.
        if isinstance(body, str) and (body.startswith("[v") or body.startswith("[{")):
            converted = prosemirror_to_html(body)
            if converted:
                return converted
        return body or ""

    if md_id:
        for cid, title, body, video in candidates:
            if cid == md_id:
                return {"title": title, "body_html": to_html(body), "video_link": video}

    candidates.sort(key=lambda c: len(c[2] or ""), reverse=True)
    cid, title, body, video = candidates[0]
    return {"title": title, "body_html": to_html(body), "video_link": video}


async def extract_skool_from_dom(page):
    """Fallback DOM: prueba selectores conocidos de Skool en orden."""
    selectors = [
        '[data-testid="lesson-content"]',
        'article [class*="LessonContent"]',
        'main [class*="lesson"]',
        'div[class*="post-content"]',
        'main article',
    ]
    for sel in selectors:
        node = await page.query_selector(sel)
        if not node:
            continue
        text = (await node.inner_text()).strip()
        if len(text) >= 300:
            html = await node.inner_html()
            return {"body_html": html, "selector": sel}
    return None


async def extract_generic(page):
    """Fallback final: trafilatura sobre el HTML completo de la página."""
    try:
        import trafilatura
    except ImportError:
        return None
    html = await page.content()
    extracted = trafilatura.extract(
        html,
        output_format="html",
        include_links=True,
        include_images=True,
        favor_recall=True,
    )
    if extracted and len(extracted) >= 200:
        return {"body_html": extracted}
    return None


# ─── Comentarios ───────────────────────────────────────────────────────────

async def extract_comments_html(page):
    """Intenta extraer la sección de comentarios. Hace scroll hasta estabilizar."""
    last_count = 0
    for _ in range(5):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)
        try:
            count = await page.evaluate(
                "document.querySelectorAll('article, [class*=comment]').length"
            )
        except Exception:
            count = 0
        if count == last_count:
            break
        last_count = count

    selectors = [
        '[data-testid="comments-section"]',
        'section[aria-label*="comment" i]',
        '[class*="CommentsSection"]',
        '[class*="comments-list"]',
    ]
    for sel in selectors:
        node = await page.query_selector(sel)
        if node:
            html = await node.inner_html()
            if html and len(html) > 100:
                return f'<aside class="comments"><h2>Comentarios</h2>{html}</aside>'
    return ""


# ─── Inline imágenes en base64 ─────────────────────────────────────────────

async def fetch_and_encode_image(request_context, url, referer):
    try:
        resp = await request_context.get(url, headers={"Referer": referer})
    except Exception as e:
        print(f"  ⚠ no se pudo descargar imagen {url}: {e}", file=sys.stderr)
        return None
    if resp.status != 200:
        return None
    body = await resp.body()
    if len(body) > IMG_MAX_EMBED_BYTES:
        print(f"  ⚠ imagen omitida (>5MB): {url}")
        return None

    if len(body) > IMG_RECOMPRESS_BYTES:
        try:
            from PIL import Image
            img = Image.open(BytesIO(body))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            body = buf.getvalue()
            mime = "image/jpeg"
        except Exception:
            mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
    else:
        mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
        if not mime.startswith("image/"):
            mime = "image/jpeg"

    b64 = base64.b64encode(body).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def inline_images_in_html(html, request_context, base_url):
    """Encuentra <img src="..."> y los reemplaza por data: URIs."""
    pattern = re.compile(r'<img\b[^>]*\bsrc=(["\'])([^"\']+)\1', re.IGNORECASE)

    matches = list(pattern.finditer(html))
    if not matches:
        return html

    cache = {}
    for m in matches:
        src = m.group(2)
        if src.startswith("data:"):
            continue
        if src.startswith("//"):
            src_full = "https:" + src
        elif src.startswith("/"):
            parsed = urlparse(base_url)
            src_full = f"{parsed.scheme}://{parsed.netloc}{src}"
        elif not src.startswith(("http://", "https://")):
            continue
        else:
            src_full = src

        if src_full in cache:
            continue
        data_uri = await fetch_and_encode_image(request_context, src_full, base_url)
        cache[src_full] = data_uri

    def repl(m):
        quote = m.group(1)
        src = m.group(2)
        if src.startswith("data:"):
            return m.group(0)
        if src.startswith("//"):
            key = "https:" + src
        elif src.startswith("/"):
            parsed = urlparse(base_url)
            key = f"{parsed.scheme}://{parsed.netloc}{src}"
        else:
            key = src
        replacement = cache.get(key)
        if not replacement:
            return m.group(0)
        return m.group(0).replace(f"src={quote}{src}{quote}", f"src={quote}{replacement}{quote}")

    return pattern.sub(repl, html)


# ─── Limpieza de HTML ──────────────────────────────────────────────────────

def clean_html(html):
    """Quita scripts/styles/iframes y agrega target=_blank a los links."""
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<iframe[\s\S]*?</iframe>", "", html, flags=re.IGNORECASE)

    def add_target(m):
        tag = m.group(0)
        if "target=" in tag.lower():
            return tag
        return tag[:-1] + ' target="_blank" rel="noopener">'

    html = re.sub(r'<a\b[^>]*\bhref=[^>]*>', add_target, html, flags=re.IGNORECASE)
    return html


# ─── Render del template HTML autocontenido ────────────────────────────────

CSS_READER = """
:root {
  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", Menlo, Monaco, Consolas, monospace;
  --color-text: #1f2328;
  --color-muted: #6e7681;
  --color-bg: #ffffff;
  --color-border: #e5e7eb;
  --color-link: #2563eb;
  --color-link-hover: #1d4ed8;
  --color-quote-border: #d4a017;
  --color-quote-bg: #fdf7e3;
  --color-code-bg: #f3f4f6;
}
* { box-sizing: border-box; }
body {
  font-family: var(--font-sans);
  font-size: 17px;
  line-height: 1.65;
  color: var(--color-text);
  background: var(--color-bg);
  margin: 0;
  padding: 0;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
main {
  max-width: 720px;
  margin: 2.5rem auto;
  padding: 0 1.5rem 4rem;
}
header.export-meta {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 1.4rem;
  margin-bottom: 2.2rem;
}
header.export-meta .course-tag {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--color-muted);
  margin-bottom: 0.6rem;
}
header.export-meta h1 {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0.2rem 0 1rem;
  line-height: 1.2;
}
header.export-meta .meta-line {
  font-size: 13px;
  color: var(--color-muted);
  margin-top: 0.2rem;
}
header.export-meta .meta-line a { color: var(--color-link); word-break: break-all; }
h1, h2, h3, h4 { line-height: 1.3; letter-spacing: -0.01em; font-weight: 700; }
h2 { font-size: 24px; margin-top: 2.4rem; margin-bottom: 0.7rem; }
h3 { font-size: 19px; margin-top: 1.8rem; margin-bottom: 0.5rem; }
h4 { font-size: 16px; margin-top: 1.4rem; margin-bottom: 0.4rem; }
p { margin: 1rem 0; }
strong { font-weight: 600; color: #111827; }
a { color: var(--color-link); text-decoration: underline; text-underline-offset: 2px; }
a:hover { color: var(--color-link-hover); }
img { max-width: 100%; height: auto; display: block; margin: 1.5rem auto; border-radius: 6px; }
ul, ol {
  padding-left: 1.5rem;
  margin: 1.4rem 0 1.4rem 1.5rem;
}
ul ul, ul ol, ol ul, ol ol { margin: 0.4rem 0 0.4rem 0.5rem; }
li {
  margin: 0.55rem 0;
  padding-left: 0.35rem;
}
li > p { margin: 0.2rem 0; }
li::marker { color: var(--color-muted); font-size: 0.9em; }
blockquote {
  border-left: 3px solid var(--color-quote-border);
  margin: 1.5rem 0;
  padding: 0.6rem 0 0.6rem 1.2rem;
  color: #4b5563;
  background: var(--color-quote-bg);
  border-radius: 0 4px 4px 0;
}
blockquote p { margin: 0.3rem 0; }
code {
  font-family: var(--font-mono);
  font-size: 0.88em;
  background: var(--color-code-bg);
  padding: 0.15em 0.4em;
  border-radius: 4px;
}
pre {
  background: #1f2937;
  color: #e5e7eb;
  padding: 1rem 1.2rem;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.55;
}
pre code { background: transparent; color: inherit; padding: 0; font-size: inherit; }
hr { border: none; border-top: 1px solid var(--color-border); margin: 2.5rem 0; }
aside.video-info {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 1rem 1.2rem;
  margin: 1.5rem 0;
}
aside.video-info .label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #b45309;
  margin-bottom: 0.4rem;
}
aside.comments {
  margin-top: 3rem;
  padding-top: 2rem;
  border-top: 1px solid var(--color-border);
  font-size: 15px;
}
aside.comments h2 { margin-top: 0; }
aside.comments article {
  border-left: 2px solid var(--color-border);
  padding-left: 1rem;
  margin: 1rem 0;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 1.4rem 0;
  font-size: 14px;
}
th, td {
  border: 1px solid var(--color-border);
  padding: 0.6rem 0.8rem;
  text-align: left;
  vertical-align: top;
}
th {
  background: var(--color-code-bg);
  font-weight: 600;
}
"""


def render_template(meta, body_html, comments_html=""):
    title = meta.get("title") or "Sin título"
    course = meta.get("course_slug") or ""
    url = meta.get("url") or ""
    today = date.today().isoformat()
    video_block = ""
    if meta.get("video_link"):
        video_block = (
            '<aside class="video-info">'
            '<div class="label">🎥 Video original (no incluido en el export)</div>'
            f'<a href="{meta["video_link"]}" target="_blank" rel="noopener">{meta["video_link"]}</a>'
            "</aside>"
        )
    course_tag = f'<div class="course-tag">Curso: {course}</div>' if course else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{CSS_READER}</style>
</head>
<body>
<main>
<header class="export-meta">
{course_tag}
<h1>{title}</h1>
<div class="meta-line">URL original: <a href="{url}" target="_blank" rel="noopener">{url}</a></div>
<div class="meta-line">Exportado: {today}</div>
</header>
{video_block}
<article class="content">
{body_html}
</article>
{comments_html}
</main>
</body>
</html>
"""


# ─── Pipeline principal ────────────────────────────────────────────────────

def ask_format_interactive():
    print("\n¿Formato de salida? [H]TML / [P]DF (default: HTML): ", end="", flush=True)
    try:
        ans = input().strip().lower()
    except EOFError:
        ans = ""
    return "pdf" if ans.startswith("p") else "html"


async def render_page(context, url, timeout=60):
    page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
    # Skool y otros SPAs tienen polling/websockets constantes; esperar fijo
    # en lugar de networkidle (que nunca se alcanza).
    await page.wait_for_timeout(8000)
    try:
        await page.wait_for_selector("h1, article, main", timeout=10000)
    except Exception:
        pass
    return page


async def extract_content(page, url):
    """Pipeline: __NEXT_DATA__ → DOM → trafilatura. Devuelve dict con title,
    body_html, video_link."""
    netloc = urlparse(url).netloc.lower()

    if "skool.com" in netloc:
        nd = await extract_skool_from_next_data(page)
        if nd and (nd.get("body_html") or "").strip():
            return nd

        dom = await extract_skool_from_dom(page)
        if dom:
            title = ""
            try:
                h1 = await page.query_selector("h1")
                if h1:
                    title = (await h1.inner_text()).strip()
            except Exception:
                pass
            if not title:
                title = (await page.title()).strip()
            return {"title": title, "body_html": dom["body_html"], "video_link": None}

    gen = await extract_generic(page)
    if gen:
        title = (await page.title()).strip()
        return {"title": title, "body_html": gen["body_html"], "video_link": None}

    title = (await page.title()).strip()
    body = await page.evaluate("document.body.innerText")
    return {
        "title": title,
        "body_html": f"<p>(No se pudo extraer contenido estructurado.)</p><pre>{body[:5000]}</pre>",
        "video_link": None,
    }


def build_output_path(url, title, fmt, override_dir=None):
    netloc = urlparse(url).netloc
    course_slug = extract_course_slug(url)
    lesson_slug = slugify(title)
    if override_dir:
        base = Path(override_dir)
    else:
        base = DOWNLOAD_DIR / netloc / course_slug
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{lesson_slug}.{fmt}"


async def export_one(context, url, fmt, with_comments, timeout, output_dir, warnings):
    """Exporta una URL. Devuelve (output_path, warning_msg or None).

    Detecta automáticamente problemas que afectan el resultado y los registra
    en `warnings` (lista compartida) para reportarlos al usuario al final.
    """
    print(f"\n→ {url}")
    page = await render_page(context, url, timeout=timeout)

    if await is_session_expired(page):
        netloc = urlparse(url).netloc
        msg = (
            f"Cookies expiradas para {netloc}. "
            f"Re-exportar con la extensión 'Get cookies.txt LOCALLY' "
            f"en cookies/{netloc}_cookies.txt"
        )
        print(f"  ✗ {msg}")
        warnings.append((url, msg))
        await page.close()
        return None

    content = await extract_content(page, url)
    title = content.get("title") or "Sin título"
    body = content.get("body_html") or ""
    video_link = content.get("video_link")

    # Auto-validación: contenido casi vacío
    plain_text_len = len(re.sub(r"<[^>]+>", "", body).strip())
    if plain_text_len < 200:
        warnings.append((
            url,
            f"La lección \"{title}\" tiene muy poco contenido textual "
            f"(~{plain_text_len} caracteres). El archivo se generó pero puede "
            f"estar prácticamente vacío — la lección puede ser solo un video."
        ))

    body = clean_html(body)
    body = await inline_images_in_html(body, context.request, url)

    comments_html = ""
    if with_comments:
        try:
            comments_html = await extract_comments_html(page)
        except Exception as e:
            warnings.append((url, f"No se pudieron extraer comentarios: {e}"))

    meta = {
        "title": title,
        "course_slug": extract_course_slug(url),
        "url": url,
        "video_link": video_link,
    }
    html_doc = render_template(meta, body, comments_html)

    out_path = build_output_path(url, title, fmt, output_dir)

    if fmt == "html":
        out_path.write_text(html_doc, encoding="utf-8")
    else:
        render = await context.new_page()
        await render.set_content(html_doc, wait_until="networkidle")
        await render.pdf(
            path=str(out_path),
            format="A4",
            print_background=True,
            margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"},
        )
        await render.close()

    await page.close()
    print(f"  ✓ {out_path}")
    return out_path


def parse_urls(args_urls):
    out = []
    for u in args_urls:
        for line in u.splitlines():
            line = line.strip()
            if line:
                out.append(line)
    return out


async def inspect_url(url, timeout=60):
    """Modo diagnóstico: analiza una URL sin exportar nada. Reporta tipos de
    contenido detectados, presencia de cookies, y sugiere si el sitio es
    Skool/genérico."""
    netloc = urlparse(url).netloc
    print(f"\n{'='*60}")
    print(f"Inspect: {url}")
    print(f"{'='*60}")
    print(f"Dominio: {netloc}")

    cookies_file = get_cookies_file(url)
    if cookies_file:
        print(f"Cookies: ✓ {cookies_file.name}")
    else:
        print(f"Cookies: ✗ No hay cookies/{netloc}_cookies.txt")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        if cookies_file:
            try:
                await context.add_cookies(load_cookies_for_playwright(cookies_file))
            except Exception as e:
                print(f"⚠ Error cargando cookies: {e}")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            await page.wait_for_timeout(8000)
        except Exception as e:
            print(f"✗ No se pudo cargar la página: {e}")
            await browser.close()
            return

        if await is_session_expired(page):
            print("✗ Sesión expirada — re-exportar cookies")
            await browser.close()
            return

        print(f"Status: ✓ página cargada ({page.url})")
        print(f"Título: {(await page.title()).strip()}")

        # Detección de __NEXT_DATA__ (Next.js / Skool / similares)
        try:
            nd_raw = await page.evaluate(
                'document.getElementById("__NEXT_DATA__")?.textContent'
            )
        except Exception:
            nd_raw = None

        if nd_raw:
            print(f"\n__NEXT_DATA__: ✓ presente ({len(nd_raw):,} bytes)")
            try:
                data = json.loads(nd_raw)
                if "skool.com" in netloc:
                    print("Plataforma detectada: Skool")
                elif "teachable.com" in netloc:
                    print("Plataforma detectada: Teachable (Next.js)")
                else:
                    print("Plataforma detectada: Next.js genérico")

                # Buscar lecciones con `desc` (ProseMirror), deduplicando por id
                seen_ids = set()
                lessons_with_desc = []
                def walk_lesson(obj):
                    if isinstance(obj, dict):
                        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else None
                        lid = obj.get("id")
                        if meta and meta.get("desc") and lid and lid not in seen_ids:
                            seen_ids.add(lid)
                            lessons_with_desc.append({
                                "id": lid,
                                "title": meta.get("title"),
                                "desc_len": len(meta.get("desc", "")),
                                "video_link": meta.get("videoLink"),
                            })
                        for v in obj.values():
                            walk_lesson(v)
                    elif isinstance(obj, list):
                        for v in obj:
                            walk_lesson(v)
                walk_lesson(data)

                if lessons_with_desc:
                    print(f"\nLecciones con contenido (`metadata.desc`): {len(lessons_with_desc)}")
                    all_types = set()
                    for l in lessons_with_desc[:5]:
                        # Re-encontrar el desc completo
                        def find_desc(o):
                            if isinstance(o, dict):
                                if o.get("id") == l["id"]:
                                    return (o.get("metadata") or {}).get("desc")
                                for v in o.values():
                                    r = find_desc(v)
                                    if r: return r
                            elif isinstance(o, list):
                                for v in o:
                                    r = find_desc(v)
                                    if r: return r
                            return None
                        desc = find_desc(data)
                        if desc:
                            all_types.update(collect_prosemirror_types(desc))
                        print(f"  • [{l['id'][:8]}…] {l['title'][:60]}  ({l['desc_len']:,} bytes)")

                    if all_types:
                        node_types = sorted(t for t in all_types if not t.startswith("mark:"))
                        mark_types = sorted(t.replace("mark:", "") for t in all_types if t.startswith("mark:"))
                        print(f"\nTipos de nodos detectados: {', '.join(node_types)}")
                        print(f"Tipos de marks detectados: {', '.join(mark_types) or '(ninguno)'}")
                else:
                    print("\nNo se encontraron lecciones con `metadata.desc`. "
                          "El sitio puede usar otra estructura — caerá a fallback genérico (trafilatura).")
            except json.JSONDecodeError:
                print("⚠ __NEXT_DATA__ no es JSON válido")
        else:
            print("\n__NEXT_DATA__: ✗ no presente — el sitio no es Next.js")
            print("Estrategia: fallback a trafilatura (Reader Mode genérico)")
            try:
                import trafilatura
                html = await page.content()
                preview = trafilatura.extract(html, output_format="txt", favor_recall=True)
                if preview:
                    print(f"Trafilatura extrae: {len(preview):,} chars")
                    print(f"Preview:\n  {preview[:300]}...")
                else:
                    print("⚠ Trafilatura no extrajo contenido — sitio puede no ser apto para export.")
            except Exception as e:
                print(f"⚠ Error en trafilatura: {e}")

        await browser.close()
    print(f"{'='*60}\n")


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="+", help="Una o varias URLs (separadas por espacio o saltos de línea)")
    ap.add_argument("--format", choices=["html", "pdf", "ask"], default="ask")
    ap.add_argument("--con-comentarios", action="store_true", default=False,
                    help="Incluir sección de comentarios al final")
    ap.add_argument("--output-dir", default=None,
                    help="Carpeta de salida. Default: downloaded/<dominio>/<curso>/")
    ap.add_argument("--timeout", type=int, default=60, help="Timeout por página en segundos")
    ap.add_argument("--inspect", action="store_true", default=False,
                    help="Modo diagnóstico: analiza la URL sin exportar nada")
    args = ap.parse_args()

    urls = parse_urls(args.urls)
    if not urls:
        print("✗ No se recibieron URLs", file=sys.stderr)
        sys.exit(1)

    if args.inspect:
        for url in urls:
            await inspect_url(url, timeout=args.timeout)
        return

    fmt = ask_format_interactive() if args.format == "ask" else args.format

    cookies_file = get_cookies_file(urls[0])
    if not cookies_file:
        print(f"⚠ No hay cookies para {urlparse(urls[0]).netloc}. "
              f"Procediendo sin login (puede no funcionar para contenido protegido).")

    print(f"\nFormato: {fmt.upper()} | URLs: {len(urls)} | "
          f"Comentarios: {'sí' if args.con_comentarios else 'no'}")
    if cookies_file:
        print(f"Cookies: {cookies_file.name}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 1800})
        if cookies_file:
            try:
                context_cookies = load_cookies_for_playwright(cookies_file)
                await context.add_cookies(context_cookies)
            except Exception as e:
                print(f"⚠ Error cargando cookies: {e}")

        outputs = []
        warnings = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}]", end=" ")
            try:
                out = await export_one(
                    context, url, fmt,
                    args.con_comentarios, args.timeout, args.output_dir,
                    warnings
                )
                if out:
                    outputs.append(out)
            except Exception as e:
                warnings.append((url, f"Error inesperado: {e}"))
                print(f"  ✗ Error: {e}")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"Resumen: {len(outputs)}/{len(urls)} exportadas")
    for p in outputs:
        try:
            rel = p.relative_to(Path.home())
            print(f"  → ~/{rel}")
        except ValueError:
            print(f"  → {p}")

    if warnings:
        print(f"\n⚠ Avisos ({len(warnings)}):")
        for url, msg in warnings:
            print(f"  • {msg}")
            print(f"    URL: {url}")

    if _PROSEMIRROR_UNKNOWN_TYPES:
        print(f"\nNota técnica: el contenido tenía elementos no soportados explícitamente "
              f"({', '.join(sorted(_PROSEMIRROR_UNKNOWN_TYPES))}). "
              f"Se manejaron con heurística — revisa el output por si hay algo extraño.")


if __name__ == "__main__":
    asyncio.run(main())
