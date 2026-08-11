#!/bin/zsh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  osascript -e 'display alert "water-regime-gis" message "Docker не найден. Установите Docker Desktop и запустите файл снова."'
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  open -a Docker || true
  osascript -e 'display alert "water-regime-gis" message "Docker Desktop запускается. Повторите запуск через минуту, когда Docker будет готов."'
  exit 1
fi

docker compose up --build -d
open http://127.0.0.1:8765
