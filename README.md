# 📥 Download Multimedia — Skill para Claude Code

Skill de [Claude Code](https://docs.claude.com/claude-code) que descarga automáticamente **todas las imágenes y videos** de cualquier URL que le compartas. Sin importar protecciones anti-hotlink, cookies de sesión, contenido dinámico o streams HLS encriptados.

## ✨ Qué hace

- Descarga **imágenes y videos** de cualquier página web pública
- Soporta **videos embebidos** (YouTube, Vimeo, Dailymotion, etc.)
- Filtra miniaturas automáticamente (menores a 300x300px)
- **Anti-duplicados** por URL
- **Bypass** de protecciones anti-hotlink (Referer, cookies, headers completos)
- Soporte dedicado para **Teachable/Hotmart** (HLS encriptado con ffmpeg)
- **2 métodos de organización**: subcarpetas secuenciales o carpeta custom con `videos/` y `jpg/` separados
- Reintentos automáticos con backoff en errores 429/500/502/503/504

## 🎯 Casos de uso

- Respaldar contenido multimedia de blogs, portafolios o redes públicas
- Descargar cursos online a los que tienes acceso (Teachable, Hotmart)
- Guardar galerías de imágenes o álbumes completos
- Archivar videos embebidos de YouTube/Vimeo desde un artículo

## 📋 Requisitos

- **macOS o Linux** (probado principalmente en macOS)
- **Python 3.9+**
- **Claude Code** — [instalar aquí](https://docs.claude.com/claude-code)
- **ffmpeg** (opcional, solo necesario para descargas de Teachable/Hotmart) — `brew install ffmpeg`

## 🚀 Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/abgarciafdz/download-multimedia-skill.git
cd download-multimedia-skill

# 2. Ejecutar el instalador
chmod +x install.sh
./install.sh
```

El instalador se encarga de:
- Crear un entorno virtual de Python
- Instalar las dependencias (`requests`, `beautifulsoup4`, `yt-dlp`, `playwright`, `Pillow`, `lxml`)
- Instalar Chromium para Playwright
- Instalar el comando `/download-multimedia` en `~/.claude/commands/`

## 💻 Uso

### Opción 1 — Desde Claude Code (recomendado)

Abre Claude Code en cualquier conversación y escribe:

```
/download-multimedia
```

Claude te preguntará:
1. Qué URLs quieres descargar (una o varias)
2. Qué método de descarga prefieres (clásico o personalizado)

Y se encarga del resto automáticamente.

### Opción 2 — Terminal directo

**Método 1 — Clásico** (carpetas secuenciales por dominio):

```bash
cd download-multimedia-skill/scripts
source venv/bin/activate
python download.py "https://ejemplo.com/articulo"
```

**Método 2 — Personalizado** (carpeta custom con `videos/` y `jpg/`):

```bash
python download.py --method 2 --folder "MiCarpeta" "https://url1.com" "https://url2.com"
```

**Teachable / Hotmart** (requiere cookies exportadas):

```bash
python download_teachable.py --start 1 "https://curso.teachable.com/courses/XXX/lectures/YYY"
```

## 📁 Estructura de carpetas

### Método 1 (Clásico)
```
scripts/downloaded/
├── apple.com/
│   ├── 01/
│   │   ├── Titulo_de_pagina_01.jpg
│   │   └── Titulo_de_pagina_01.mp4
│   └── 02/
│       └── Otra_pagina_01.jpg
└── behance.net/
    └── 01/
```

### Método 2 (Personalizado)
```
scripts/downloaded/
└── sitio.com/
    └── MiCarpeta/
        ├── videos/
        │   ├── video_01.mp4
        │   └── video_02.mp4
        └── jpg/
            ├── imagen_01.jpg
            └── imagen_02.jpg
```

## 🍪 Descargar desde sitios con login (Teachable)

Para descargar videos de cursos que requieren login:

1. Instala la extensión de Chrome **[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)**
2. Entra al curso en tu navegador (inicia sesión)
3. Haz clic en la extensión → **Export**
4. Guarda el archivo en: `scripts/cookies/<subdominio>.teachable.com_cookies.txt`

Ejemplo de nombre correcto: `scripts/cookies/micursos.teachable.com_cookies.txt`

## 🛠️ Técnicas de respaldo

Si el script principal no logra descargar todo, Claude intenta automáticamente:

1. **yt-dlp directo** — para galerías/álbumes con referer custom
2. **curl con headers** — descarga manual con Referer y User-Agent
3. **Análisis del HTML** — busca URLs directamente en el DOM
4. **Playwright** — renderiza la página con JavaScript para sitios dinámicos

## ⚙️ Configuración avanzada

Puedes ajustar parámetros en [scripts/download.py](scripts/download.py):

| Parámetro | Valor default | Descripción |
|-----------|--------------|-------------|
| `MIN_IMAGE_SIZE` | 300x300px | Tamaño mínimo de imagen (menores se descartan) |
| `IMAGE_FORMAT` | JPG | Formato de salida para imágenes |
| `VIDEO_FORMAT` | MP4 | Formato de salida para videos |
| `MAX_RETRIES` | 3 | Intentos en errores de servidor |
| `DOWNLOAD_DIR` | `downloaded/` | Carpeta de descargas |

## ❓ FAQ

**¿Es legal descargar contenido con esta herramienta?**
Sí, siempre y cuando tengas derecho a acceder al contenido. La responsabilidad del uso recae en el usuario. No descargues contenido con copyright que no tengas autorización para guardar.

**¿Funciona en Windows?**
No está probado en Windows. Debería funcionar con WSL (Windows Subsystem for Linux). En Windows nativo, los scripts Python deberían correr pero `install.sh` no.

**¿Qué hago si un sitio no funciona?**
Comparte la URL con Claude y di "no funcionó". Claude intentará las 4 técnicas de respaldo automáticamente. Si nada funciona, es probable que el sitio tenga protecciones muy estrictas (Cloudflare premium, tokens de sesión temporales, etc.).

**¿Puedo usar esto sin Claude Code?**
Sí, los scripts Python funcionan de forma independiente. Lo que no tendrías es la orquestación inteligente y los fallbacks automáticos.

## 🤝 Contribuir

¿Encontraste un bug o quieres agregar soporte para otro sitio? ¡Abre un issue o manda un PR!

- Reporta bugs en [Issues](https://github.com/abgarciafdz/download-multimedia-skill/issues)
- Propuestas de features son bienvenidas

## 📄 Licencia

[MIT](LICENSE) — úsalo libremente, modifícalo, distribúyelo.

## ⚠️ Disclaimer

Esta herramienta es solo para uso personal y legítimo. No se apoya ni fomenta:
- Piratería de contenido con copyright
- Violación de términos de servicio de sitios web
- Descarga masiva que cause daño a los servidores

El autor no se hace responsable del uso que se le dé a la herramienta.

---

Hecho con ☕ por [@abgarciafdz](https://github.com/abgarciafdz)
