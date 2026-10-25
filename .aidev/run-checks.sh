#!/usr/bin/env bash
# Run the checks named after the suite and write test-results/<suite>/junit.xml.
#
#   .aidev/run-checks.sh <suite> <step>...
#
# Steps: lint (eslint, as CI's lint-ci), build (tsc), py-test (pytest on
# python/tests, offline code generation), py-lint (ruff), py-types (mypy). Each step
# is one junit case; py-test also keeps pytest's own junit. Runs offline in the
# image of .aidev/runtime/Dockerfile.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
root="$PWD"
suite="${1:?usage: $0 <suite> <step>...}"; shift
out="$root/test-results/$suite"
rm -rf "$out"; mkdir -p "$out"
cases="$out/cases.tsv"; : > "$cases"
source .aidev/junit-helpers.sh

needs_node=0
for s in "$@"; do case "$s" in lint|build) needs_node=1 ;; esac; done
if [ "$needs_node" -eq 1 ]; then
    if ! source "$root/.aidev/pnpm-deps.sh"; then
        printf 'case\tinstall\tfail\t0\tpnpm install --offline failed\n' >> "$cases"
        junit_write_cases "$out/junit.xml" "$suite" "$cases"
        exit 1
    fi
fi

status=0
step() {
    local name="$1"; shift
    local log="$out/$name.log" t0=$SECONDS rc=0
    echo "== $name" >&2
    ( cd "$root" && "$@" ) > "$log" 2>&1 < /dev/null || rc=$?
    if [ "$rc" -eq 0 ]; then
        printf 'case\t%s\tpass\t%s\t\n' "$name" "$((SECONDS - t0))" >> "$cases"
    else
        status=1; tail -40 "$log" >&2
        printf 'case\t%s\tfail\t%s\texit %s\t%s\n' "$name" "$((SECONDS - t0))" "$rc" "$log" >> "$cases"
    fi
}

py_tests() {
    local junit="$out/pytest-junit.xml"
    cd python || return 1
    run_with_junit_fallback "$junit" py-test \
        python3 -m pytest -p no:cacheprovider --junitxml="$junit" tests
}

for s in "$@"; do
    case "$s" in
        lint) step lint pnpm exec eslint src --ext .js,.ts --max-warnings=0 --ignore-pattern '*.d.ts' ;;
        build) step build pnpm exec tsc --outDir "$out/dist" ;;
        py-test) step py-test py_tests ;;
        py-lint) step py-lint bash -c 'cd python && ruff check . && ruff format --check .' ;;
        py-types) step py-types bash -c 'cd python && mypy api_client_generator' ;;
        *) printf 'case\t%s\tfail\t0\tunknown step\n' "$s" >> "$cases"; status=1 ;;
    esac
done
junit_write_cases "$out/junit.xml" "$suite" "$cases"
exit "$status"
