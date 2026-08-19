#!/bin/sh
set -u

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FFMPEG="$BASE_DIR/tools/ffmpeg/ffmpeg"
if [ ! -x "$FFMPEG" ]; then
    FFMPEG=$(command -v ffmpeg 2>/dev/null || true)
fi
if [ -z "$FFMPEG" ]; then
    echo "[ERROR] FFmpeg was not found."
    echo "Put the Linux ARM64 ffmpeg binary at tools/ffmpeg/ffmpeg,"
    echo "or install FFmpeg in PATH, then run this tool again."
    exit 1
fi

if [ "$#" -ne 1 ]; then
    echo "Usage:"
    echo "  ./convert_video.sh /path/to/sample.mov"
    echo "  ./convert_video.sh /path/to/videos"
    exit 2
fi

INPUT=$1
if [ ! -e "$INPUT" ]; then
    echo "[ERROR] Input does not exist: $INPUT"
    exit 2
fi

convert_one() {
    source_file=$1
    output_file=$2
    echo "[INFO] Converting: $(basename "$source_file")"
    if "$FFMPEG" -y -i "$source_file" -map 0:v:0 -map '0:a:0?' \
        -c:v libx264 -pix_fmt yuv420p -preset medium -crf 23 \
        -c:a aac -b:a 128k -movflags +faststart "$output_file"; then
        echo "[OK] Created: $output_file"
    else
        echo "[ERROR] Conversion failed: $source_file" >&2
        return 1
    fi
}

if [ -d "$INPUT" ]; then
    OUTPUT_DIR=$INPUT/converted
    mkdir -p "$OUTPUT_DIR"
    found=0
    failed=0
    for source_file in "$INPUT"/*; do
        [ -f "$source_file" ] || continue
        case $(printf '%s' "${source_file##*.}" | tr '[:upper:]' '[:lower:]') in
            mp4|mov|m4v|webm|ogv|avi|wmv|mkv)
                found=1
                base_name=$(basename "$source_file")
                output_name=${base_name%.*}.mp4
                convert_one "$source_file" "$OUTPUT_DIR/$output_name" || failed=1
                ;;
        esac
    done
    if [ "$found" -eq 0 ]; then
        echo "[ERROR] No supported video files were found in: $INPUT"
        exit 2
    fi
    [ "$failed" -eq 0 ] || exit 1
else
    OUTPUT_DIR=$(dirname "$INPUT")/converted
    mkdir -p "$OUTPUT_DIR"
    base_name=$(basename "$INPUT")
    convert_one "$INPUT" "$OUTPUT_DIR/${base_name%.*}.mp4" || exit 1
fi

echo "[DONE] Compatible videos are in: $OUTPUT_DIR"
