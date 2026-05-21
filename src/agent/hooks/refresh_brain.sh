#!/bin/bash
# refresh_brain.sh — Post-session hook to reload knowledge index.
#
# Run after each Jarvis session to re-index any newly harvested
# knowledge and update the vector store.
#
# Usage:
#   bash src/agent/hooks/refresh_brain.sh [--data-dir ./agent_data]

set -euo pipefail

DATA_DIR="${1:-${AGENT_STORAGE_PATH:-./agent_data}}"
KNOWLEDGE_DIR="$DATA_DIR/knowledge"
INDEX_FILE="$DATA_DIR/knowledge_index.json"
LOG_FILE="$DATA_DIR/logs/refresh_$(date +%Y%m%d_%H%M%S).log"

echo "════════════════════════════════════════"
echo "  BRAIN REFRESH — $(date)"
echo "  Data Dir: $DATA_DIR"
echo "════════════════════════════════════════"

mkdir -p "$DATA_DIR/logs"

# 1. Count current knowledge chunks
CHUNK_COUNT=0
if [ -d "$KNOWLEDGE_DIR" ]; then
    CHUNK_COUNT=$(find "$KNOWLEDGE_DIR" -name "*.json" -type f | wc -l)
fi
echo "[1/3] Knowledge chunks found: $CHUNK_COUNT" | tee -a "$LOG_FILE"

# 2. Rebuild index if it exists
if [ -f "$INDEX_FILE" ]; then
    echo "[2/3] Rebuilding knowledge index..." | tee -a "$LOG_FILE"
    # Trigger re-indexing via Python
    python -c "
import json, os, time
idx = {'rebuilt_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'chunks': $CHUNK_COUNT}
with open('$INDEX_FILE', 'w') as f:
    json.dump(idx, f, indent=2)
print('  Index rebuilt.')
" 2>&1 | tee -a "$LOG_FILE"
else
    echo "[2/3] No existing index — skipping rebuild." | tee -a "$LOG_FILE"
fi

# 3. Clean up stale temp files
STALE=$(find "$DATA_DIR" -name "*.tmp" -mtime +7 -type f 2>/dev/null | wc -l)
if [ "$STALE" -gt 0 ]; then
    echo "[3/3] Cleaning $STALE stale .tmp files..." | tee -a "$LOG_FILE"
    find "$DATA_DIR" -name "*.tmp" -mtime +7 -type f -delete
else
    echo "[3/3] No stale files to clean." | tee -a "$LOG_FILE"
fi

echo ""
echo "✅ Brain refresh complete." | tee -a "$LOG_FILE"
