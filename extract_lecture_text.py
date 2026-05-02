#!/usr/bin/env python3
"""Extract lecture text content from Teachable course pages."""

import asyncio
import re
import sys
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
    parsed = urlparse(url)
    cookies_file = COOKIES_DIR / f"{parsed.netloc}_cookies.txt"
    return cookies_file if cookies_file.exists() else None


def load_cookies(cookies_file):
    with open(cookies_file) as f:
        lines = f.readlines()
    cookies = []
    for line in lines:
        if line.startswith("#") or not line.strip():
            continue
        parts = line.strip().split("\t")
        if len(parts) >= 7:
            cookies.append({
                "name": parts[5],
                "value": parts[6],
                "domain": parts[0],
                "path": parts[2],
                "expires": int(parts[4]) if parts[4].isdigit() else -1,
                "httpOnly": False,
                "secure": parts[3].upper() == "TRUE",
            })
    return cookies


async def extract_text(url, cookies_file):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        await context.add_cookies(load_cookies(cookies_file))
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(15000)

        # Try lecture title from sidebar (current selected lecture)
        title = await page.title()
        title = re.sub(r"\s*\|\s*.*$", "", title).strip()
        try:
            sel_lect = await page.query_selector(
                ".SIO-course-modules-list__lecture--selected"
            )
            if sel_lect:
                lect_title = (await sel_lect.inner_text()).strip()
                if lect_title:
                    title = lect_title.split("\n")[0].strip()
        except Exception:
            pass

        # Find lecture iframe with text content (Teachable embeds via srcdoc)
        html_content = None
        text_content = None
        iframe_handle = await page.query_selector(
            'iframe[data-test-id="course-lecture-iframe"]'
        )
        if iframe_handle:
            frame = await iframe_handle.content_frame()
            if frame:
                try:
                    await frame.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await page.wait_for_timeout(3000)
                body = await frame.query_selector("body")
                if body:
                    text_content = (await body.inner_text()).strip()
                    html_content = await body.inner_html()

        # Fallback: container or body
        if not text_content or len(text_content) < 100:
            container = await page.query_selector(".SIO-course-lecture__container")
            if container:
                t = (await container.inner_text()).strip()
                if t and len(t) > 50:
                    html_content = await container.inner_html()
                    text_content = t

        await browser.close()
        return title, html_content, text_content


def html_to_markdown(html):
    """Very simple HTML-to-Markdown conversion preserving structure."""
    import html as html_lib
    s = html
    # Remove script/style
    s = re.sub(r"<script[\s\S]*?</script>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<style[\s\S]*?</style>", "", s, flags=re.IGNORECASE)
    # Headings
    for n in range(6, 0, -1):
        s = re.sub(rf"<h{n}[^>]*>([\s\S]*?)</h{n}>",
                   lambda m: "\n\n" + "#" * n + " " + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "\n\n",
                   s, flags=re.IGNORECASE)
    # Lists
    s = re.sub(r"<li[^>]*>([\s\S]*?)</li>",
               lambda m: "- " + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "\n",
               s, flags=re.IGNORECASE)
    s = re.sub(r"</?(ul|ol)[^>]*>", "\n", s, flags=re.IGNORECASE)
    # Paragraphs / breaks
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<p[^>]*>", "", s, flags=re.IGNORECASE)
    # Bold / italic
    s = re.sub(r"<(strong|b)[^>]*>([\s\S]*?)</\1>", r"**\2**", s, flags=re.IGNORECASE)
    s = re.sub(r"<(em|i)[^>]*>([\s\S]*?)</\1>", r"*\2*", s, flags=re.IGNORECASE)
    # Links
    s = re.sub(r'<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>',
               r"[\2](\1)", s, flags=re.IGNORECASE)
    # Strip remaining tags
    s = re.sub(r"<[^>]+>", "", s)
    # Decode entities
    s = html_lib.unescape(s)
    # Clean whitespace
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return s.strip()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_lecture_text.py URL [output.md]")
        sys.exit(1)
    url = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else None

    cookies_file = get_cookies_file(url)
    if not cookies_file:
        print(f"✗ No cookies found for {urlparse(url).netloc}")
        sys.exit(1)

    print(f"Cargando: {url}")
    title, html_content, text_content = await extract_text(url, cookies_file)
    print(f"Título: {title}")
    print(f"Largo del texto: {len(text_content)} caracteres")

    md = html_to_markdown(html_content)
    md_full = f"# {title}\n\n**Fuente:** {url}\n\n---\n\n{md}\n"

    if not output:
        domain = urlparse(url).netloc
        safe = re.sub(r"[^\w\-]+", "_", title)[:80].strip("_")
        out_dir = DOWNLOAD_DIR / domain
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / f"{safe}_texto.md"
    output = Path(output)
    output.write_text(md_full, encoding="utf-8")
    print(f"✓ Guardado: {output}")


if __name__ == "__main__":
    asyncio.run(main())
