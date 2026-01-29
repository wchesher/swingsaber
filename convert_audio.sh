#!/usr/bin/env bash
# =============================================================================
# SwingSaber WAV Conversion Script
#
# Converts all WAV files in sounds/ to 16-bit signed PCM, 22050 Hz, mono
# for optimal audio quality on the HalloWing M4 Class D amplifier.
#
# Requirements: sox (install via: brew install sox / apt install sox)
#
# Usage:
#   ./convert_audio.sh              # convert in-place (backs up originals)
#   ./convert_audio.sh --dry-run    # preview what would happen
# =============================================================================

set -euo pipefail

SOUNDS_DIR="$(dirname "$0")/sounds"
BACKUP_DIR="$(dirname "$0")/sounds_backup_8bit"
TARGET_RATE=22050
TARGET_BITS=16
TARGET_CHANNELS=1
DRY_RUN=false

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN (no files will be modified) ==="
    echo
fi

if ! command -v sox &>/dev/null; then
    echo "ERROR: sox not found. Install it:"
    echo "  macOS:  brew install sox"
    echo "  Linux:  sudo apt install sox"
    echo "  Win:    choco install sox"
    exit 1
fi

if [[ ! -d "$SOUNDS_DIR" ]]; then
    echo "ERROR: sounds/ directory not found at $SOUNDS_DIR"
    exit 1
fi

# Count files
count=$(find "$SOUNDS_DIR" -maxdepth 1 -name '*.wav' | wc -l)
if [[ "$count" -eq 0 ]]; then
    echo "No WAV files found in $SOUNDS_DIR"
    exit 0
fi

echo "Found $count WAV files in $SOUNDS_DIR"
echo "Target: ${TARGET_BITS}-bit ${TARGET_RATE}Hz ${TARGET_CHANNELS}ch signed PCM"
echo

# Show current format
echo "Current formats:"
for f in "$SOUNDS_DIR"/*.wav; do
    info=$(soxi -r -b -c "$f" 2>/dev/null || echo "unknown")
    echo "  $(basename "$f"): $info"
done
echo

if $DRY_RUN; then
    echo "Would convert all files to ${TARGET_BITS}-bit ${TARGET_RATE}Hz mono."
    echo "Originals would be backed up to: $BACKUP_DIR/"
    exit 0
fi

# Backup originals
if [[ ! -d "$BACKUP_DIR" ]]; then
    echo "Backing up originals to $BACKUP_DIR/"
    mkdir -p "$BACKUP_DIR"
    cp "$SOUNDS_DIR"/*.wav "$BACKUP_DIR/"
else
    echo "Backup already exists at $BACKUP_DIR/ — skipping backup"
fi

# Convert each file
converted=0
skipped=0
for f in "$SOUNDS_DIR"/*.wav; do
    name=$(basename "$f")
    tmp="${f}.tmp"

    # Check if already correct format
    rate=$(soxi -r "$f" 2>/dev/null || echo 0)
    bits=$(soxi -b "$f" 2>/dev/null || echo 0)
    channels=$(soxi -c "$f" 2>/dev/null || echo 0)

    if [[ "$rate" == "$TARGET_RATE" && "$bits" == "$TARGET_BITS" && "$channels" == "$TARGET_CHANNELS" ]]; then
        echo "  SKIP $name (already ${TARGET_BITS}-bit ${TARGET_RATE}Hz)"
        skipped=$((skipped + 1))
        continue
    fi

    echo "  CONVERT $name: ${bits}bit ${rate}Hz ${channels}ch -> ${TARGET_BITS}bit ${TARGET_RATE}Hz mono"
    sox "$f" -b "$TARGET_BITS" -r "$TARGET_RATE" -c "$TARGET_CHANNELS" -e signed-integer "$tmp"
    mv "$tmp" "$f"
    converted=$((converted + 1))
done

echo
echo "Done: $converted converted, $skipped already correct"
echo
echo "Verify with: soxi sounds/*.wav"
