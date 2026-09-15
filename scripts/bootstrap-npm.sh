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
NPM_NAME="@regioneer/volto-rer-linkchecker"
GITHUB_SLUG="RegioneER/rer-linkchecker"
WORKFLOW="npm.yml"
# Esplicito e non negoziabile: un `@scope:registry` nell'~/.npmrc di chi lancia
# lo script dirottererebbe publish e view su un altro registry senza dirlo, e
# il trusted publisher OIDC esiste solo su npmjs.org.
NPM_REGISTRY="https://registry.npmjs.org/"

OWNED_SESSION=0

cleanup() {
    if [ "${OWNED_SESSION}" = "1" ]; then
        echo ""
        echo "==> npm logout (chiudo la sessione aperta da questo script)"
        npm logout --registry "${NPM_REGISTRY}" || echo "⚠️  logout non riuscito: chiudila a mano con 'npm logout'."
    fi
}
trap cleanup EXIT

cd "${REPO_ROOT}/${PACKAGE_PATH}"
VERSION="$(node -p "require('./package.json').version")"

echo "==============================================="
echo "Bootstrap npm: ${NPM_NAME}@${VERSION}"
echo "  repo CI:  ${GITHUB_SLUG}  (workflow ${WORKFLOW})"
echo "  registry: ${NPM_REGISTRY}"
echo "==============================================="
echo ""

# Autenticazione. Serve comunque: `npm trust list` legge le impostazioni del
# pacchetto e non funziona da anonimo.
if npm whoami --registry "${NPM_REGISTRY}" > /dev/null 2>&1; then
    echo "✅ Gia' autenticato come $(npm whoami --registry "${NPM_REGISTRY}")."
    echo "   Sessione preesistente: la lascio aperta a fine script."
else
    echo "==> npm login (flusso web nel browser)"
    npm login --registry "${NPM_REGISTRY}"
    OWNED_SESSION=1
    echo "✅ Autenticato come $(npm whoami --registry "${NPM_REGISTRY}"). La chiudo io a fine script."
fi
echo ""

# 1. Pubblicazione iniziale, solo se il pacchetto non esiste ancora.
if npm view "${NPM_NAME}" version --registry "${NPM_REGISTRY}" > /dev/null 2>&1; then
    echo "✅ ${NPM_NAME} esiste gia' su npm, salto la publish."
else
    # Stesso criterio del workflow: il dist-tag esce dalla versione.
    if [[ "${VERSION}" =~ -([a-zA-Z]+) ]]; then
        TAG="${BASH_REMATCH[1]}"
    else
        TAG="latest"
    fi
    echo "==> npm publish --access public --tag ${TAG} --registry ${NPM_REGISTRY}"
    npm publish --access public --tag "${TAG}" --registry "${NPM_REGISTRY}"
fi
echo ""

# 2. Trusted publisher, cosi' le release successive non chiedono token.
#
# `npm trust` e' recente: npm 10.9 non lo ha ("Unknown command"), npm 12 si'. Per
# non imporre un upgrade della npm globale (spesso gestita da volta o corepack)
# si usa npm@latest via npx solo per questo passo. L'autenticazione e' la stessa,
# perche' legge lo stesso ~/.npmrc.
NPM_TRUST=(npm)
if ! npm trust list --help > /dev/null 2>&1; then
    echo "ℹ️  npm $(npm --version) non ha 'npm trust': per questo passo uso npx npm@latest."
    NPM_TRUST=(npx -y npm@latest)
fi

if "${NPM_TRUST[@]}" trust list "${NPM_NAME}" --registry "${NPM_REGISTRY}" 2>/dev/null | grep -q "${GITHUB_SLUG}"; then
    echo "✅ Trusted publisher gia' configurato per ${GITHUB_SLUG}."
else
    echo "==> ${NPM_TRUST[*]} trust github ${NPM_NAME} --file ${WORKFLOW}"
    # --allow-publish e' obbligatorio per le configurazioni create dopo il
    # 20 maggio 2026; quelle precedenti avevano il permesso implicito.
    if ! "${NPM_TRUST[@]}" trust github "${NPM_NAME}" \
        --file "${WORKFLOW}" \
        --repository "${GITHUB_SLUG}" \
        --registry "${NPM_REGISTRY}" \
        --allow-publish
    then
        # Caso visto sul campo: npm risponde 403 "Granular access tokens that
        # bypass two-factor authentication may not perform this action".
        # Configurare un trusted publisher e' un'operazione di sicurezza e
        # pretende una sessione con 2FA, che un granular access token salvato
        # nell'~/.npmrc non ha. La publish qui sopra invece il token la fa
        # passare, quindi si arriva a questo punto con il pacchetto gia'
        # pubblicato: il rilancio dello script salta la publish e ritenta solo
        # il trust.
        cat <<MSG

❌ Configurazione del trusted publisher fallita.

   Se l'errore e' 403 "Granular access tokens that bypass two-factor
   authentication may not perform this action", sei autenticato con un token
   che bypassa la 2FA (tipicamente la riga
   //registry.npmjs.org/:_authToken=... del tuo ~/.npmrc). Due strade:

     a) npm login --registry ${NPM_REGISTRY}    # flusso web, porta la 2FA
        e rilancia questo script. Attenzione: il login sovrascrive quella
        riga dell'~/.npmrc, quindi se quel token ti serve altrove salvalo.

     b) configuralo dal sito, che e' l'altra via ufficiale:
        https://www.npmjs.com/package/${NPM_NAME} -> Settings ->
        Trusted Publisher, con repository ${GITHUB_SLUG}, workflow
        ${WORKFLOW} e il permesso di publish.

   Il resto del bootstrap (la publish) e' gia' a posto: quando il trust c'e',
   non serve rilanciare nulla.
MSG
        exit 1
    fi
fi

echo ""
echo "==============================================="
echo "✅ Bootstrap completato."
echo "   Da qui in poi pubblica la CI: 'make release' aggiorna versioni e"
echo "   changelog e crea il tag, il push del tag fa partire ${WORKFLOW}."
echo "==============================================="
