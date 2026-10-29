# Automated contributions

This directory configures the automated development platform that contributes to this
repository. This note says which branches it uses here and how its work reaches the
project's main line.

## Branches

- `aidev/integration` — the integration branch. Automated work lands here and nowhere else.
- `main` — the project's main line; reached from `aidev/integration` only by merge request (`aidev handoff`, a linear one-commit-per-change copy on `aidev/handoff`).
- `ai/*` — one branch per task, created and deleted by the platform. Do not commit to them.
- `session/*` — a session's accumulated work, landed on the integration branch as a batch.

## How work reaches the main line

Task and session branches never reach `aidev/integration` through merge requests; the platform
lands them after its own verification. `aidev/integration` reaches the main line by this project's usual process, merge requests included — the
platform never merges into any other branch.

Whether this project's CI pipelines skip `ai/*` and `session/*` branches is decided by the
project's CI rules; maintainers record that decision here.

## Suites run before work lands

Declared in `.aidev/project.yaml` under `verification`:

- `quick` — `command` .aidev/run-checks.sh quick lint build py-test
- `full` — `command` .aidev/run-checks.sh full lint build py-test
- `baseline` — `command` .aidev/run-checks.sh baseline build py-test
- `canary` — `command` .aidev/run-checks.sh canary lint build py-test
- `static` — `command` .aidev/run-checks.sh static lint py-lint py-types
- `coverage` — `command` .aidev/run-checks.sh coverage py-test
- `system` — `command` .aidev/run-checks.sh system build py-test

## Test runtime

`.aidev/runtime/Dockerfile` builds on common-ci-configuration's `node-test-tools:develop`
(so Node is the single version ccc pins; this repo carries none) and adds Python 3 with
`python/poetry.lock`'s main, dev and static-analysis groups. Rebuild and re-pin it with
`.aidev/runtime/build.sh --push` when ccc moves Node or the image, or when the Dockerfile,
`pnpm-lock.yaml`, `python/pyproject.toml` or `python/poetry.lock` changes, and put the
printed `repo@sha256:…` into `environment.image`.

`pnpm-workspace.yaml` is a symlink into the `npm-common-config` submodule (ccc's pnpm
catalogs), so the suites' offline `pnpm install` needs that submodule checked out in the
workspace.

At onboarding (2026-10-25) the `static` slot's `py-lint` (ruff, 9 findings) and
`py-types` (mypy, 5 findings) fail on the existing code; `quick`/`full` pass.
