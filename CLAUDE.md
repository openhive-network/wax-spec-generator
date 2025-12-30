# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Wax-spec-generator generates typed API clients from OpenAPI/Swagger specifications. It has two implementations:

- **TypeScript/Node.js** (root level): Generates `.js` and `.d.ts` files for REST and JSON-RPC APIs
- **Python** (`python/` directory): Generates Python API client classes for REST and JSON-RPC APIs

## Commands

### TypeScript (root directory)

```bash
pnpm install                    # Install dependencies
pnpm run build                  # Compile TypeScript to dist/
pnpm run lint                   # Lint with auto-fix
pnpm run lint-ci                # Lint without auto-fix (CI mode)

# Run the generator
npx generate-wax-spec -i <swagger.json> -N <namespace> -T <rest|jsonrpc>
```

### Python (python/ directory)

```bash
cd python
poetry install                  # Install dependencies
poetry run pytest tests/        # Run all tests
poetry run pytest tests/unit/   # Run unit tests only
poetry run ruff check --fix .   # Lint with auto-fix
poetry run ruff format .        # Format code
poetry run mypy .               # Type check
```

## Architecture

### TypeScript Generator

Entry point: `src/index.ts` → `src/generator.ts`

Uses `swagger-typescript-api` to parse OpenAPI specs, with custom hooks in `src/hooks/on-create-route.ts` to transform routes. Generates both JavaScript implementation and TypeScript declarations.

Key flow:
1. Parse CLI options (`parse-options.ts`)
2. Optionally scaffold npm package (`npm.ts`)
3. Generate API spec using `swagger-typescript-api` with custom route hooks
4. Compile to `.js` + `.d.ts` using TypeScript compiler API

### Python Generator

Main package: `python/api_client_generator/`

Two API styles:
- **JSON-RPC** (`json_rpc/`): `generate_api_client()`, `generate_api_collection()`, `generate_api_description()`
- **REST** (`rest/`): `generate_api_client_from_swagger()`

Code generation uses Python's `ast` module to build class definitions programmatically. Output is formatted with `ruff`.

Key modules:
- `_private/client_class_factory/`: Creates client class AST nodes
- `_private/endpoints_factory/`: Creates method AST nodes for endpoints
- `_private/json_rpc_tools/`: JSON-RPC specific utilities
- `_private/rest_api_tools/`: REST API specific utilities
- `generate_types_from_swagger.py`: Uses `datamodel-code-generator` for Pydantic models

## CI/CD

Pipeline stages: `.pre` → `tests` → `build` → `deploy`

- Pre-commit checks use `ruff` for linting/formatting and `mypy` for type checking
- Tests run via `pytest` with fixtures that auto-generate test API clients
- Builds produce npm package (TypeScript) and Python wheel
- Deploys to GitLab package registry and npmjs.org (for tags)

## Testing

Python tests generate API clients during test setup (see `tests/conftest.py` and `tests/generate_clients_and_collections.py`). The `tests/swagger/` directory contains test swagger files and expected outputs for both JSON-RPC and REST APIs.
