#!/bin/bash
# Rilascia il backend su PyPI e crea il tag.
#
# Il frontend NON viene pubblicato da qui: repository.toml ha
# `publish = false` in [frontend.package], e ci pensa la CI al push del tag
# (.github/workflows/npm.yml) autenticandosi via OIDC. Per questo qui non
# serve nessun token npm, che scadrebbe ogni 90 giorni.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "==============================================="
echo "Release rer-linkchecker"
echo "==============================================="

if [ -z "${UV_PUBLISH_TOKEN:-}" ]; then
    echo "❌ UV_PUBLISH_TOKEN non impostato (serve per pubblicare su PyPI)."
    echo "   export UV_PUBLISH_TOKEN='...'"
    echo "   export GITHUB_TOKEN='...'   # opzionale, per la GitHub release"
    exit 1
fi

# repoplone aggiorna anche versione e changelog del pacchetto frontend, quindi
# node serve comunque, pur senza pubblicare su npm.
if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
    # shellcheck disable=SC1091
    . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
    nvm use
else
    echo "⚠️  nvm non trovato, uso il node corrente: $(node --version)"
fi

node -e 'const [maj, min] = process.versions.node.split(".").map(Number); if (maj < 18 || (maj === 18 && min < 12)) process.exit(1);' || {
    echo "❌ Node $(node --version) troppo vecchio per pnpm (serve >= 18.12)."
    exit 1
}

echo "==> Installo le dipendenze del frontend"
cd "${REPO_ROOT}/frontend"
pnpm install

cd "${REPO_ROOT}"
echo "==> repoplone release"
uvx repoplone release

echo ""
echo "==============================================="
echo "✅ Backend rilasciato e tag creato."
echo ""
echo "Il frontend lo pubblica la CI al push del tag."
echo "Se il workflow npm fallisce, NON rifare la release: rilancia"
echo "'Release latest version on npm' da GitHub Actions indicando il tag."
echo "==============================================="
