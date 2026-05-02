#!/bin/bash
# Instalador de download-tools (download-multimedia + download-social) para Claude Code

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
COMMAND_DEST_DIR="$HOME/.claude/commands"
COMMANDS_SOURCE="$SCRIPT_DIR/commands"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Instalador: download-tools${NC}"
echo -e "${BLUE}  (download-multimedia + download-social)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 1. Verificar Python 3
echo -e "${YELLOW}[1/5]${NC} Verificando Python 3..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 no está instalado.${NC}"
    echo "   Instálalo con: brew install python3"
    exit 1
fi
echo -e "   ✓ $(python3 --version)"

# 2. Verificar ffmpeg
echo -e "${YELLOW}[2/5]${NC} Verificando ffmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}   ⚠️  ffmpeg no está instalado.${NC}"
    echo "   Es necesario para descargas de Teachable/Hotmart y conversión de videos VP9."
    echo "   Instálalo con: brew install ffmpeg"
    echo ""
    read -p "   ¿Continuar sin ffmpeg? (s/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        exit 1
    fi
else
    echo -e "   ✓ ffmpeg instalado"
fi

# 3. Crear entorno virtual e instalar dependencias
echo -e "${YELLOW}[3/5]${NC} Creando entorno virtual e instalando dependencias..."
cd "$SCRIPT_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo -e "   ✓ Dependencias Python instaladas (incluye gallery-dl, yt-dlp, whisper)"

# 4. Instalar Chromium para Playwright (opcional, para sitios JS)
echo -e "${YELLOW}[4/5]${NC} Instalando Chromium para Playwright..."
pip install playwright --quiet
playwright install chromium 2>/dev/null || echo "   (Playwright/Chromium falló — opcional, instala manualmente si lo necesitas)"
echo -e "   ✓ Playwright preparado"

# 5. Instalar los commands de Claude Code
echo -e "${YELLOW}[5/5]${NC} Instalando commands de Claude Code..."
mkdir -p "$COMMAND_DEST_DIR"

# Reemplazar placeholder {INSTALL_PATH} con la ruta real
for cmd_file in "$COMMANDS_SOURCE"/*.md; do
    cmd_name=$(basename "$cmd_file")
    sed "s|{INSTALL_PATH}|$SCRIPT_DIR|g" "$cmd_file" > "$COMMAND_DEST_DIR/$cmd_name"
    echo -e "   ✓ /$( basename "$cmd_name" .md ) instalado"
done

# Crear carpetas de trabajo
mkdir -p "$SCRIPT_DIR/cookies"
mkdir -p "$SCRIPT_DIR/downloaded"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Instalación completa${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Uso desde Claude Code:"
echo "  /download-multimedia    — descargar imágenes y videos de cualquier URL"
echo "  /download-social        — descargar de Instagram y Facebook"
echo ""
echo "Carpetas:"
echo "  Descargas: $SCRIPT_DIR/downloaded/"
echo "  Cookies:   $SCRIPT_DIR/cookies/  (necesarias para Instagram/Teachable privados)"
echo ""
