#!/usr/bin/env bash
#
# Lance la démonstration locale.
#
# Variables d'environnement :
#   DEMO_PORT     port d'écoute (défaut : 7865)
#   DEMO_NO_OPEN  mettre à 1 pour ne pas ouvrir le navigateur
#   PYTHON_BIN    interpréteur à utiliser (défaut : .venv/bin/python s'il existe,
#                 sinon python3 — le chemin d'exécution n'utilise que la stdlib)
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_PORT="${DEMO_PORT:-7865}"
DEMO_URL="http://127.0.0.1:${DEMO_PORT}"

cd "${PROJECT_DIR}"

# Aucun environnement virtuel n'est requis : le projet n'a pas de dépendance
# externe. On utilise .venv s'il existe, par confort, jamais par nécessité.
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
fi
if [[ -z "${PYTHON_BIN}" || ! -x "${PYTHON_BIN}" ]]; then
  echo "Erreur : aucun interpréteur Python 3 trouvé. Installe Python 3.10 ou plus." >&2
  exit 1
fi

# Ouvre une URL sur macOS, Linux ou Windows/WSL, sans jamais faire échouer le
# script si aucun ouvreur n'est disponible.
open_browser() {
  local url="$1"
  if [[ "${DEMO_NO_OPEN:-0}" == "1" ]]; then
    return 0
  fi
  if command -v open >/dev/null 2>&1; then
    open "${url}" || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${url}" >/dev/null 2>&1 || true
  elif command -v wslview >/dev/null 2>&1; then
    wslview "${url}" >/dev/null 2>&1 || true
  else
    echo "Ouvre manuellement ${url}"
  fi
}

if ! curl -fsS http://127.0.0.1:11434/api/tags \
  | "${PYTHON_BIN}" -c \
    'import json,sys; d=json.load(sys.stdin); raise SystemExit(not any("gemma4:12b" in m.get("name","") for m in d.get("models",[])))'
then
  echo "Erreur : lance Ollama avec le modèle gemma4:12b." >&2
  exit 1
fi

echo "Préchargement de Gemma 4…"
curl -fsS http://127.0.0.1:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4:12b","prompt":"","stream":false,"keep_alive":"10m"}' \
  >/dev/null

# grep plutôt que rg : ripgrep n'est pas installé par défaut, et ce dépôt
# revendique de n'exiger aucune dépendance externe.
if curl -fsS "${DEMO_URL}" 2>/dev/null | grep -q "Droit de Retard"; then
  echo "Démo déjà disponible sur ${DEMO_URL}"
  open_browser "${DEMO_URL}"
  exit 0
fi

open_browser_delayed() { sleep 1; open_browser "${DEMO_URL}"; }
open_browser_delayed &

echo "Démarrage de la démo sur ${DEMO_URL}"
exec "${PYTHON_BIN}" app.py --port "${DEMO_PORT}"
