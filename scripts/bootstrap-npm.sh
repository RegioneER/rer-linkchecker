#!/bin/bash
# Bootstrap npm: da eseguire UNA SOLA VOLTA, subito dopo aver creato il repo.
#
# npm non permette di configurare un trusted publisher su un pacchetto che non
# esiste ancora, quindi la primissima pubblicazione deve essere manuale. Da li'
# in poi pubblica la CI via OIDC e nessuno deve piu' rinnovare token.
#
# Lo script e' idempotente: se il pacchetto esiste gia' non ripubblica, se il
# trusted publisher e' gia' configurato non lo riconfigura.
#
# Gestisce da se' login e logout, ma solo della sessione che apre lui: se eri
# gia' autenticato la lascia intatta, perche' `npm logout` invalida il token
# lato registry e ti butterebbe fuori anche dove lo stavi usando.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PACKAGE_PATH="frontend/packages/volto-rer-linkchecker"
NPM_NAME="volto-rer-linkchecker"
GITHUB_SLUG="RegioneER/rer-linkchecker"
WORKFLOW="npm.yml"

OWNED_SESSION=0

cleanup() {
    if [ "${OWNED_SESSION}" = "1" ]; then
        echo ""
        echo "==> npm logout (chiudo la sessione aperta da questo script)"
        npm logout || echo "⚠️  logout non riuscito: chiudila a mano con 'npm logout'."
    fi
}
trap cleanup EXIT

cd "${REPO_ROOT}/${PACKAGE_PATH}"
VERSION="$(node -p "require('./package.json').version")"

echo "==============================================="
echo "Bootstrap npm: ${NPM_NAME}@${VERSION}"
echo "  repo CI:  ${GITHUB_SLUG}  (workflow ${WORKFLOW})"
echo "==============================================="
echo ""

# Autenticazione. Serve comunque: `npm trust list` legge le impostazioni del
# pacchetto e non funziona da anonimo.
if npm whoami > /dev/null 2>&1; then
    echo "✅ Gia' autenticato come $(npm whoami)."
    echo "   Sessione preesistente: la lascio aperta a fine script."
else
    echo "==> npm login (flusso web nel browser)"
    npm login
    OWNED_SESSION=1
    echo "✅ Autenticato come $(npm whoami). La chiudo io a fine script."
fi
echo ""

# 1. Pubblicazione iniziale, solo se il pacchetto non esiste ancora.
if npm view "${NPM_NAME}" version > /dev/null 2>&1; then
    echo "✅ ${NPM_NAME} esiste gia' su npm, salto la publish."
else
    # Stesso criterio del workflow: il dist-tag esce dalla versione.
    if [[ "${VERSION}" =~ -([a-zA-Z]+) ]]; then
        TAG="${BASH_REMATCH[1]}"
    else
        TAG="latest"
    fi
    echo "==> npm publish --access public --tag ${TAG}"
    npm publish --access public --tag "${TAG}"
fi
echo ""

# 2. Trusted publisher, cosi' le release successive non chiedono token.
if npm trust list "${NPM_NAME}" 2>/dev/null | grep -q "${GITHUB_SLUG}"; then
    echo "✅ Trusted publisher gia' configurato per ${GITHUB_SLUG}."
else
    echo "==> npm trust github ${NPM_NAME} --file ${WORKFLOW}"
    # --allow-publish e' obbligatorio per le configurazioni create dopo il
    # 20 maggio 2026; quelle precedenti avevano il permesso implicito.
    npm trust github "${NPM_NAME}" \
        --file "${WORKFLOW}" \
        --repository "${GITHUB_SLUG}" \
        --allow-publish
fi

echo ""
echo "==============================================="
echo "✅ Bootstrap completato."
echo "   Da qui in poi pubblica la CI: 'make release' rilascia il backend"
echo "   e crea il tag, il push del tag fa partire ${WORKFLOW}."
echo "==============================================="
