#!/usr/bin/env bash
# Sword of Etheria — recomp nativo · launcher (tools + ISO del usuario)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/game/launcher.py" "$@"
