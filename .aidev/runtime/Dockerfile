# The image AIDEV runs this project's suites in (`environment.image` in
# .aidev/project.yaml). Suites run with `--network none` and the caller's uid, so
# everything they need is in the image:
#
# * common-ci-configuration's node-test-tools (Ubuntu 26.04, Node v24.21.0, pnpm),
#   the same tool image CI's npm templates use;
# * a pnpm store filled from pnpm-lock.yaml (`pnpm fetch`), so `pnpm install
#   --offline` works in the sandbox;
# * Python 3 with python/poetry.lock's main, dev and static-analysis groups in
#   /opt/py (pytest, ruff, mypy), installed by poetry from a copy of python/;
#   the package itself (`--no-root`) is importable from the mounted workspace
#   through a .pth.
#
# Build and pin it with .aidev/runtime/build.sh; see .aidev/README.md.
FROM registry.gitlab.syncad.com/hive/common-ci-configuration/node-test-tools@sha256:e49773279d26e2b546c5e785e656fcec5caa983def88aef5816e2d95ec72ef1a
USER root
ENV HOME=/tmp \
    PATH=/opt/py/bin:$PATH \
    VIRTUAL_ENV=/opt/py \
    npm_config_store_dir=/opt/pnpm-store \
    npm_config_manage_package_manager_versions=false \
    HUSKY=0 \
    DO_NOT_TRACK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MYPY_CACHE_DIR=/tmp/.mypy_cache \
    RUFF_CACHE_DIR=/tmp/.ruff_cache
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 python3-venv python3-pip git \
    && rm -rf /var/lib/apt/lists/* \
    && python3 --version
COPY js/ /tmp/pnpm-fetch/
RUN cd /tmp/pnpm-fetch \
    && pnpm fetch \
    && cd / && rm -rf /tmp/pnpm-fetch \
    && chmod -R a+rwX /opt/pnpm-store
COPY python/ /work/python/
RUN python3 -m venv /opt/poetry \
    && /opt/poetry/bin/pip install --no-cache-dir poetry \
    && python3 -m venv --without-pip /opt/py \
    && cd /work/python \
    && POETRY_CACHE_DIR=/tmp/poetry-cache /opt/poetry/bin/poetry install --no-root --no-interaction \
         --with dev,static-analysis \
    && /opt/py/bin/ruff --version && /opt/py/bin/mypy --version && /opt/py/bin/python -m pytest --version \
    && echo /work/python > "$(/opt/py/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/wax-spec-generator-workspace.pth" \
    && rm -rf /work /tmp/poetry-cache /opt/poetry \
    && chmod -R a+rwX /opt/py
