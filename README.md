# 📥 download-tools

> Suite open-source de descarga: multimedia genérico (imágenes/videos/cursos) + redes sociales (Instagram/Facebook). Dos commands de Claude Code en un solo repo.

Suite con **dos herramientas** que comparten venv, dependencias y carpeta de cookies:

| Command | Qué descarga |
|---|---|
| `/download-multimedia` | Imágenes y videos de **cualquier URL** pública (blogs, portafolios, cursos, etc.) — bypass de protecciones, soporte HLS, fallback a yt-dlp |
| `/download-social` | Posts, reels, stories, highlights y perfiles de **Instagram y Facebook** (incluye cuentas privadas a las que ya sigues) usando cookies de sesión |

## ✨ download-multimedia

- Descarga **imágenes y videos** de cualquier página web pública
- Soporta **videos embebidos** (YouTube, Vimeo, Dailymotion, etc.)
- Filtra miniaturas automáticamente (menores a 300x300px)
- **Anti-duplicados** por URL
- **Bypass** de protecciones anti-hotlink (Referer, cookies, headers completos)
- Soporte dedicado para **Teachable/Hotmart** (HLS encriptado con ffmpeg)
- **2 métodos de organización**: subcarpetas secuenciales o carpeta custom con `videos/` y `jpg/` separados
- Reintentos automáticos con backoff en errores 429/500/502/503/504
- **Post-proceso opcional**: transcripción local con Whisper + apuntes de estudio

## ✨ download-social

- Descarga **posts, reels, stories, highlights y perfiles** de Instagram
- Descarga **posts y videos** públicos de Facebook
- Funciona con **cuentas privadas** a las que ya sigues (vía cookies)
- Convierte automáticamente videos VP9 → H.264 (compatibilidad QuickTime)
- Foto de perfil HD opcional como ítem independiente
- Filtros por fecha, cantidad de posts, inclusión de stories/highlights

## 🎯 Casos de uso

- Respaldar contenido multimedia de blogs, portafolios o redes públicas
- Descargar cursos online a los que tienes acceso (Teachable, Hotmart)
- Archivar perfiles completos de IG/FB antes de que se eliminen
- Guardar reels y stories para inspiración o referencia
- Descargar videos embebidos de YouTube/Vimeo desde un artículo

## 📋 Requisitos

- **macOS o Linux** (probado principalmente en macOS)
- **Python 3.9+**
- **ffmpeg** — `brew install ffmpeg`
- [Claude Code](https://docs.claude.com/claude-code) instalado
- Para `download-social`: cookies exportadas del navegador (ver instrucciones abajo)

## 🚀 Instalación

```bash
git clone https://github.com/abgarciafdz/download-tools.git
cd download-tools
./install.sh
```

El instalador:
- Crea un entorno virtual de Python
- Instala las dependencias (`requests`, `beautifulsoup4`, `yt-dlp`, `Pillow`, `lxml`, `gallery-dl`, `openai-whisper`)
- Instala los commands `/download-multimedia` y `/download-social` en `~/.claude/commands/`

## 💻 Uso

### Desde Claude Code (recomendado)

Abre Claude Code y escribe:

```
/download-multimedia
```

para descargar imágenes/videos de cualquier URL, o:

```
/download-social https://instagram.com/p/ABC/
```

para descargar de redes sociales.

### Desde terminal

**download-multimedia:**

```bash
source venv/bin/activate
python download.py "https://ejemplo.com/articulo"

# Con organización custom:
python download.py --method 2 --folder "MiCarpeta" "https://url1" "https://url2"

# Teachable/Hotmart (requiere cookies):
python download_teachable.py --start 1 "https://curso.teachable.com/lectures/YYY"
```

**download-social:**

```bash
source venv/bin/activate

# Post o reel directo:
python download_social.py "https://instagram.com/p/ABC/"

# Últimos 30 posts de un perfil:
python download_social.py --limit 30 --yes "https://instagram.com/usuario/"

# Perfil completo + stories + highlights:
python download_social.py --include stories,highlights "https://instagram.com/usuario/"
```

## 🍪 Configurar cookies

Algunas descargas requieren cookies de sesión (Teachable para cursos privados, Instagram para cuentas privadas).

1. Instala la extensión **[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** en tu navegador
2. Inicia sesión en el sitio (Instagram, Facebook, Teachable, etc.)
3. Click en la extensión → **Export As → Netscape**
4. Guarda el archivo en `cookies/` con el nombre del dominio:
   - `cookies/instagram.com_cookies.txt`
   - `cookies/facebook.com_cookies.txt`
   - `cookies/micursos.teachable.com_cookies.txt`

## 📁 Estructura de descargas

```
downloaded/
├── instagram.com/
│   └── @usuario/
│       ├── 2026-05-02_post-ABC.mp4
│       └── avatar/perfil-hd.jpg
├── apple.com/
│   └── 01/
│       └── pagina_01.jpg
└── teachable.com/
    └── 01/
        └── lecture_01.mp4
```

## ⚙️ Configuración avanzada

| Parámetro | Default | Dónde |
|-----------|---------|-------|
| `MIN_IMAGE_SIZE` | 300x300px | `download.py` |
| `IMAGE_FORMAT` | JPG | `download.py` |
| `VIDEO_FORMAT` | MP4 | `download.py` |
| `MAX_RETRIES` | 3 | `download.py` |
| `DOWNLOAD_DIR` | `downloaded/` | `download.py` |

## ❓ FAQ

**¿Es legal descargar contenido con esta herramienta?**
Sí, siempre y cuando tengas derecho a acceder al contenido. La responsabilidad del uso recae en el usuario. No descargues contenido con copyright que no tengas autorización para guardar.

**¿Funciona en Windows?**
No está probado. Debería funcionar con WSL. En Windows nativo, los scripts Python deberían correr pero `install.sh` no.

**¿Qué hago si un sitio no funciona?**
`download-multimedia` tiene 4 fallbacks automáticos (yt-dlp, curl, análisis HTML, Playwright). Si nada funciona, probablemente el sitio tiene protecciones avanzadas (Cloudflare premium, tokens temporales).

**¿Por qué Instagram pide cookies?**
Para acceder a contenido de cuentas privadas o tu propio feed. Sin cookies, solo se accede a contenido 100% público.

**¿Puedo usar esto sin Claude Code?**
Sí, los scripts Python funcionan independientemente. Solo pierdes la orquestación conversacional y los fallbacks automáticos.

## 🤝 Contribuir

- Reporta bugs en [Issues](https://github.com/abgarciafdz/download-tools/issues)
- Propuestas de features son bienvenidas

## 📜 Licencia

MIT — usa, modifica y comparte libremente.

## ⚠️ Disclaimer

Esta herramienta es solo para uso personal y legítimo. No se apoya ni fomenta:
- Piratería de contenido con copyright
- Violación de términos de servicio de sitios web
- Descarga masiva que cause daño a los servidores

El autor no se hace responsable del uso que se le dé a la herramienta.

---

Hecho por [@abgarciafdz](https://github.com/abgarciafdz)
