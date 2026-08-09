#!/bin/zsh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  osascript -e 'display alert "water-regime-gis" message "Python 3 не найден. Установите Python 3 и запустите панель снова."'
  exit 1
fi

python3 scripts/run_app.py
