# Download Multimedia — Descargador de imágenes y videos desde URLs

## Qué es esta herramienta

Descarga automáticamente **todas las imágenes y videos** de cualquier página web que Abraham comparta. Funciona con blogs, redes sociales públicas, noticias, portafolios de diseño, tiendas en línea, y cualquier sitio público. También descarga videos embebidos de YouTube, Vimeo y otras plataformas.

**Qué NO descarga:** miniaturas, íconos, favicons, imágenes decorativas menores a 300x300px.

## Stack técnico

- **Python 3** — script principal
- **requests** — para descargar archivos
- **BeautifulSoup + lxml** — para extraer URLs de imágenes y videos del HTML
- **yt-dlp** — para descargar videos embebidos (YouTube, Vimeo, etc.)
- **Pillow** — para verificar tamaño de imágenes y filtrar miniaturas
- **Playwright + Chromium** — para sitios con contenido dinámico (Teachable/Hotmart)
- **ffmpeg** — para descargar streams HLS y convertir video
- **openai-whisper** — para transcripción local de videos (post-proceso opcional)

## Estructura del proyecto

```
~/Documents/CLAUDE/projects/download-multimedia/
├── CLAUDE.md                ← este archivo, documentación del proyecto
├── .gitignore               ← excluye downloaded/, __pycache__, venv/
├── download.py              ← script principal de descarga (sitios genéricos)
├── download_teachable.py    ← script dedicado para Teachable/Hotmart
├── transcribe.py            ← transcripción local con Whisper (post-proceso)
├── requirements.txt         ← dependencias Python
├── cookies/                 ← cookies exportadas del navegador (por dominio)
│   └── stock6.teachable.com_cookies.txt
├── venv/                    ← entorno virtual Python (no se sube a git)
└── downloaded/              ← carpeta de descargas (no se sube a git)
    ├── apple.com/           ← carpeta por dominio
    │   ├── 01/
    │   │   ├── imagen-01.jpg
    │   │   └── video-01.mp4
    │   └── 02/
    │       └── imagen-01.jpg
    ├── stock6.teachable.com/
    │   └── 01/
    │       ├── 54617679_01.mp4   ← lecture_id + secuencial
    │       └── 54617680_01.mp4
    └── behance.net/
        └── 01/
```

## Cómo ejecutar

### Opción principal: Skill de Claude Code
```
/download-multimedia
```
El skill te pedirá las URLs, el método de descarga y ejecutará automáticamente.

### Opción manual (terminal)

**Método 1 — Clásico** (carpetas secuenciales por dominio):
```bash
cd ~/Documents/CLAUDE/projects/download-multimedia
source venv/bin/activate
python download.py "https://ejemplo.com/articulo"
```

**Método 2 — Personalizado** (carpeta custom con videos/ y jpg/):
```bash
source venv/bin/activate
python download.py --method 2 --folder "MiCarpeta" "https://url1.com" "https://url2.com"
```

## Estrategia de descarga

1. **Crea sesión HTTP** con headers de navegador real (Chrome), cookies persistentes y reintentos automáticos
2. **Visita la página** para obtener cookies de sesión del sitio
3. **Extrae el título** de la página (H1 o `<title>`) para nombrar archivos
4. **Extrae** todas las URLs de imágenes (`<img>`, `<picture>`, `<source>`, `srcset`, `data-src`, CSS backgrounds, `og:image`)
5. **Extrae** todas las URLs de videos (`<video>`, `<source>`, iframes de YouTube/Vimeo/Dailymotion)
6. **Filtra miniaturas** — descarta imágenes menores a 300x300px
7. **Anti-duplicados** — rastrea URLs ya descargadas para no repetir archivos
8. **Descarga imágenes** con Referer y cookies del sitio, convierte a JPG
9. **Descarga videos directos** con Referer, reintentos con backoff incremental
10. **Descarga videos embebidos** con yt-dlp (incluye Referer y User-Agent)
11. **Organiza** según método elegido:
    - Método 1: `downloaded/dominio/01/`, `02/`, etc.
    - Método 2: `downloaded/dominio/carpeta/videos/` y `downloaded/dominio/carpeta/jpg/`

### Nomenclatura de archivos
Los archivos se nombran usando el título de la página + sufijo secuencial:
- `Titulo_de_pagina_01.jpg`, `Titulo_de_pagina_02.jpg`
- `Titulo_de_pagina_01.mp4`, `Titulo_de_pagina_02.mp4`

El título se obtiene del H1 de la página, o del `<title>`, o del slug de la URL como último recurso.

### Bypass de protecciones
- **Anti-hotlink (Referer):** se envía automáticamente el Referer del sitio origen
- **Cookies de sesión:** la sesión HTTP conserva cookies obtenidas al visitar la página
- **Headers completos:** simula Chrome con Sec-Fetch-*, Accept, Origin, etc.
- **Reintentos:** 3 intentos automáticos con pausa incremental en errores 429/500/502/503/504
- **Fallback en skill:** si el script falla, el skill tiene 4 técnicas de respaldo (yt-dlp, curl, análisis HTML, Playwright)

## Configuración ajustable

| Parámetro | Valor actual | Dónde cambiarlo | Descripción |
|-----------|-------------|-----------------|-------------|
| Tamaño mínimo de imagen | 300x300px | `download.py` (constante `MIN_IMAGE_SIZE`) | Imágenes menores se descartan como miniaturas |
| Formato de imagen | JPG | `download.py` (constante `IMAGE_FORMAT`) | Formato de salida para imágenes |
| Formato de video | MP4 | `download.py` (constante `VIDEO_FORMAT`) | Formato de salida para videos |
| Carpeta de descargas | `downloaded/` | `download.py` (constante `DOWNLOAD_DIR`) | Dónde se guardan los archivos |
| Reintentos máximos | 3 | `download.py` (constante `MAX_RETRIES`) | Intentos en errores de servidor |
| Timeout de request | 30s (imgs) / 120s (videos) | `download.py` | Tiempo máximo de espera por archivo |

## Convenciones

- **Idioma del código:** inglés (variables, funciones)
- **Idioma de la interfaz:** español (mensajes al usuario, skill)
- **Nombres de carpetas:** dominio del sitio (ej: `erome.com`, `apple.com`). Método 1: subcarpetas secuenciales (`01/`, `02/`). Método 2: carpeta custom con `videos/` y `jpg/` dentro
- **Nombres de archivos:** Título de página + secuencial. Ej: `Mi_Album_01.mp4`, `Mi_Album_02.jpg`. El título se extrae del H1 o `<title>` de la página automáticamente
- **Entorno virtual:** siempre activar con `source venv/bin/activate` antes de ejecutar

## Pendientes (roadmap)

### Fase 1 — Completada
- [x] Estructura del proyecto
- [x] Script principal de descarga (`download.py`)
- [x] Skill `/download-multimedia`
- [x] Extracción de imágenes directas (img, picture, source, srcset, data-src, og:image, CSS backgrounds)
- [x] Extracción de videos embebidos (yt-dlp) y directos
- [x] Filtro de miniaturas por tamaño (300x300px mínimo)
- [x] Conversión a JPG/MP4
- [x] Organización por dominio + carpetas secuenciales
- [x] Bypass de protecciones anti-hotlink (Referer, cookies, headers completos)
- [x] Reintentos automáticos con backoff

### Sitios con soporte dedicado
- **Teachable/Hotmart (*.teachable.com):** Script dedicado `download_teachable.py`. Los videos usan el player de Hotmart con HLS encriptado (AES-128). El script usa Playwright para cargar la página con cookies de sesión, intercepta la URL del master playlist HLS vía network listener, y descarga con ffmpeg (codec copy, sin re-encoding). Requiere cookies exportadas en `cookies/<subdominio>.teachable.com_cookies.txt`. Videos largos (1-2hrs) — ejecutar en background.
  - **Flags disponibles:**
    - `--start N` — Número secuencial inicial (default: auto-detecta del contenido existente)
    - `--dir SUBCARPETA` — Guardar en `downloaded/<dominio>/<SUBCARPETA>/` en vez de la raíz del dominio. Útil para agrupar series (ej: `--dir clases-grupales`)
  - **Ejemplo:** `python download_teachable.py --dir clases-grupales "URL1" "URL2"`
  - **Modo progresivo:** Para series grandes (varios videos), se puede ejecutar 1 URL a la vez con confirmación entre descargas y notificación de progreso N/total. No está automatizado en el script — se orquesta desde Claude cuando Abraham comparte una lista grande.

### Limitaciones conocidas
- **erome.com:** `download.py` no funciona (contenido cargado con JavaScript). Procedimiento correcto:
  - **Videos:** yt-dlp directo. OJO: descarga cada video 2 veces (SD+HD mismo contenido) → eliminar duplicados por MD5 después.
    ```bash
    yt-dlp --referer "https://www.erome.com/a/ALBUM_ID" -o "downloaded/erome.com/NN/ALBUM_ID_%(autonumber)02d.%(ext)s" "https://www.erome.com/a/ALBUM_ID"
    ```
  - **Imágenes:** yt-dlp NO descarga imágenes. Usar requests + HTML parsing con patrón `<div class="img" data-src="URL">` y `class="img-front" src="URL"`. Filtrar `/thumbs/` y deduplicar por URL base (sin `?v=`).
  - Con muchas descargas seguidas, erome aplica rate-limit — usar pausas de 0.5-1s entre álbumes
- **yt-dlp:** versión instalada es 2025.10.14 — considerar actualizar con `pip install -U yt-dlp`

### Fase 2 (futuro)
- [ ] Soporte para sitios con login vía cookies del navegador
- [ ] Descarga de galerías dinámicas (JavaScript/scroll infinito) con Playwright
- [ ] Detección de galerías/carruseles y descarga completa
- [ ] Resumen visual de lo descargado (conteo, tamaños, previews)
- [ ] Mejorar skill para usar yt-dlp directo como fallback automático para sitios JS

### Fase 2 — Completada (23/04/2026)
- [x] **Post-proceso opcional: transcripción y puntos clave**
  - Pregunta al inicio del skill: `1. Solo descarga / 2. + transcripción / 3. + transcripción + puntos clave / 4. + puntos clave`
  - Al terminar la descarga, lista interactiva de videos descargados para elegir cuáles procesar (todos / específicos por índice / ninguno)
  - Transcripción con Whisper local (modelo `base` por default), corre en la Mac sin costo externo
  - Archivo `<video>_transcripcion.md` generado junto al video
  - Puntos clave generados por Claude leyendo la transcripción → archivo `<video>_puntos-clave.md` junto al video (estructura de estudio: Resumen / Puntos clave / Conceptos / Conclusiones / Preguntas)
  - Script autónomo `transcribe.py` reutilizable: `python transcribe.py "video.mp4"` — genera solo la transcripción sin pasar por el skill
  - Flags: `--model {tiny,base,small,medium,large}` (default `base`), `--language es|en|pt|...` (opcional, auto-detect por default)
  - Tiempos: ~2 min por 10 min de video, ~10-15 min por hora, ~20-30 min por 2 horas (Mac M1/M2, modelo base)

### Fase 3 — App web local (idea, 19/04/2026)
Convertir el skill en una app web local con interfaz visual. Diseño completo en memoria `project_download_multimedia_app.md`. Incluye:
- [ ] UI con checkboxes: descargar imágenes, videos, transcripciones, puntos clave
- [ ] Selector de ruta de guardado
- [ ] Gestión de cookies por sitio (panel semáforo + alerta preventiva/reactiva)
- [ ] Preview de contenido antes de descargar + selección individual
- [ ] Procesamiento en lote (múltiples URLs con progreso)
- [ ] Barras de progreso, reintentos visibles, resumen post-descarga
- [ ] Historial de descargas
- [ ] Transcripciones por video individual, idioma auto-detectado
