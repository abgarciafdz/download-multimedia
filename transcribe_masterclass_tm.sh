#!/bin/bash
# ==============================================
# Transcripción masiva de masterclass.tradingmasivo.com
# Usa Whisper directamente sobre MP4 (sin extracción WAV intermedia)
# ==============================================

BASE="/Users/abgfdz93/Documents/CLAUDE/projects/download-multimedia/downloaded/masterclass.tradingmasivo.com"
MODEL="${WHISPER_MODEL:-base}"
LOGFILE="/tmp/whisper_tm_log.txt"

echo "=== INICIO: $(date) | modelo=$MODEL ===" | tee "$LOGFILE"

for VIDEOFILE in "$BASE"/*.mp4; do
    [ -f "$VIDEOFILE" ] || continue

    BASENAME=$(basename "$VIDEOFILE" .mp4)
    TRANSCRIPT_OUT="$BASE/${BASENAME}_Transcripción.txt"

    if [ -f "$TRANSCRIPT_OUT" ]; then
        echo "[$BASENAME] SKIP: Ya existe transcripción" | tee -a "$LOGFILE"
        continue
    fi

    OUTDIR="/tmp/whisper_tm_out_$$_${RANDOM}"
    mkdir -p "$OUTDIR"

    echo "[$BASENAME] Transcribiendo - $(date '+%H:%M:%S')" | tee -a "$LOGFILE"

    # Whisper acepta MP4 directamente (usa ffmpeg internamente)
    whisper "$VIDEOFILE" \
        --model "$MODEL" \
        --language es \
        --output_format txt \
        --output_dir "$OUTDIR" \
        --verbose False 2>>"$LOGFILE"

    RC=$?
    if [ $RC -eq 0 ]; then
        GENERATED="$OUTDIR/${BASENAME}.txt"
        if [ -f "$GENERATED" ]; then
            mv "$GENERATED" "$TRANSCRIPT_OUT"
            echo "[$BASENAME] ✅ $(date '+%H:%M:%S') — Guardado" | tee -a "$LOGFILE"
        else
            echo "[$BASENAME] ⚠️  Whisper OK pero no se encontró el txt generado" | tee -a "$LOGFILE"
            ls "$OUTDIR" | tee -a "$LOGFILE"
        fi
    else
        echo "[$BASENAME] ❌ ERROR Whisper (rc=$RC)" | tee -a "$LOGFILE"
    fi

    rm -rf "$OUTDIR"
    echo "---" | tee -a "$LOGFILE"
done

echo "=== FIN: $(date) ===" | tee -a "$LOGFILE"
