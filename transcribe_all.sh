#!/bin/bash
# ==============================================
# Script de transcripción masiva con Whisper
# Procesa videos 04-30 de stock6.teachable.com
# ==============================================

BASE="/Users/abgfdz93/Documents/CLAUDE/projects/download-multimedia/downloaded/stock6.teachable.com"
LOGFILE="/tmp/whisper_batch_log.txt"

echo "=== INICIO: $(date) ===" | tee "$LOGFILE"

for i in $(seq 4 30); do
    NUM=$(printf "%02d" $i)
    WAV="/tmp/whisper_${NUM}.wav"
    OUTDIR="/tmp/whisper_out_${NUM}"

    # Determinar carpeta del video
    if [ $i -le 18 ]; then
        VDIR="$BASE/Bootcamp"
    else
        VDIR="$BASE/Clases grupales"
    fi

    # Buscar archivo de video
    VIDEOFILE=$(ls "$VDIR/${NUM}_"*.mp4 2>/dev/null | head -1)
    if [ -z "$VIDEOFILE" ]; then
        echo "[$NUM] SKIP: No se encontró video" | tee -a "$LOGFILE"
        continue
    fi

    BASENAME=$(basename "$VIDEOFILE" .mp4)
    TRANSCRIPT_OUT="$VDIR/${BASENAME}_Transcripción.txt"

    # Si ya existe la transcripción, saltar
    if [ -f "$TRANSCRIPT_OUT" ]; then
        echo "[$NUM] SKIP: Ya existe transcripción" | tee -a "$LOGFILE"
        continue
    fi

    # Extraer audio si no existe
    if [ ! -f "$WAV" ]; then
        echo "[$NUM] Extrayendo audio..." | tee -a "$LOGFILE"
        ffmpeg -i "$VIDEOFILE" -ar 16000 -ac 1 -c:a pcm_s16le "$WAV" -y 2>/dev/null
    fi

    # Transcribir con Whisper
    mkdir -p "$OUTDIR"
    echo "[$NUM] Transcribiendo: $BASENAME - $(date '+%H:%M:%S')" | tee -a "$LOGFILE"
    whisper "$WAV" --model base --language es --output_format txt --output_dir "$OUTDIR" 2>/dev/null

    if [ $? -eq 0 ]; then
        echo "[$NUM] Whisper completado - $(date '+%H:%M:%S')" | tee -a "$LOGFILE"

        # Limpiar transcripción
        python3 /tmp/clean_whisper.py "$OUTDIR/whisper_${NUM}.txt" "$TRANSCRIPT_OUT"
        echo "[$NUM] ✅ Guardado: $TRANSCRIPT_OUT" | tee -a "$LOGFILE"

        # Limpiar archivos temporales
        rm -f "$WAV"
        rm -rf "$OUTDIR"
    else
        echo "[$NUM] ❌ ERROR en Whisper" | tee -a "$LOGFILE"
    fi

    echo "---" | tee -a "$LOGFILE"
done

echo "=== FIN: $(date) ===" | tee -a "$LOGFILE"
echo ""
echo "📋 Log completo en: $LOGFILE"
echo "✅ Transcripciones guardadas en las carpetas de cada video"
