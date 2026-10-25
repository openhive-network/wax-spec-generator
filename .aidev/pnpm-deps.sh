# Sourced by run-checks.sh from the repository root: bring node_modules up to
# date with pnpm-lock.yaml from the image's pnpm store, offline.
lock_id="$(sha256sum pnpm-lock.yaml | cut -d' ' -f1) $(node --version)"
marker=node_modules/.aidev-pnpm-lock
if [ "$(cat "$marker" 2>/dev/null)" != "$lock_id" ] || [ ! -x node_modules/.bin/tsc ] || [ ! -x node_modules/.bin/eslint ]; then
    echo "node_modules is not current for pnpm-lock.yaml: pnpm install --offline" >&2
    pnpm install --offline --frozen-lockfile --ignore-scripts < /dev/null || return 1
    if [ ! -x node_modules/.bin/tsc ] || [ ! -x node_modules/.bin/eslint ]; then
        echo "pnpm install left no tsc/eslint" >&2; return 1
    fi
    printf '%s\n' "$lock_id" > "$marker.tmp" && mv "$marker.tmp" "$marker"
fi
