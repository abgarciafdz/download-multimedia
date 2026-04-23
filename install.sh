#!/bin/bash
# Instalador de la skill download-multimedia para Claude Code
# Detecta su propia ubicación y configura todo automáticamente

set -e

# Colores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Detectar ruta del script (funciona aunque se llame desde otro directorio)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SCRIPTS_PATH="$SCRIPT_DIR/scripts"
COMMAND_SOURCE="$SCRIPT_DIR/commands/download-multimedia.md"
COMMAND_DEST_DIR="$HOME/.claude/commands"
COMMAND_DEST="$COMMAND_DEST_DIR/download-multimedia.md"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Instalador: download-multimedia skill${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 1. Verificar Python 3
echo -e "${YELLOW}[1/5]${NC} Verificando Python 3..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 no está instalado.${NC}"
    echo "   Instálalo desde https://www.python.org/downloads/ o con: brew install python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo -e "   ✓ $PYTHON_VERSION"

# 2. Verificar ffmpeg (necesario para descargas de Teachable)
echo -e "${YELLOW}[2/5]${NC} Verificando ffmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}   ⚠️  ffmpeg no está instalado.${NC}"
    echo "   Es opcional, pero se necesita para descargas de Teachable/Hotmart."
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
cd "$SCRIPTS_PATH"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo -e "   ✓ Dependencias Python instaladas"

# 4. Instalar Chromium para Playwright
echo -e "${YELLOW}[4/5]${NC} Instalando Chromium para Playwright..."
pip install playwright --quiet
playwright install chromium
echo -e "   ✓ Chromium instalado"

# 5. Instalar el comando de Claude Code
echo -e "${YELLOW}[5/5]${NC} Instalando comando de Claude Code..."
mkdir -p "$COMMAND_DEST_DIR"

# Reemplazar placeholder {INSTALL_PATH} con la ruta real
sed "s|{INSTALL_PATH}|$SCRIPTS_PATH|g" "$COMMAND_SOURCE" > "$COMMAND_DEST"
echo -e "   ✓ Comando instalado en $COMMAND_DEST"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Instalación completa${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Uso:"
echo "  Abre Claude Code y escribe: /download-multimedia"
echo ""
echo "Ubicación de scripts:"
echo "  $SCRIPTS_PATH"
echo ""
echo "Ubicación del comando:"
echo "  $COMMAND_DEST"
echo ""
