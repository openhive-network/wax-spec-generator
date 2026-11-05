from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final

import pytest

TEMPLATE: Final[Path] = Path(__file__).parents[2] / "templates" / "python_api_package.gitlab-ci.yml"
WHEEL: Final[str] = "hiveio_smoke_test_api-1.0.0.post20261105000000-py3-none-any.whl"
OTHER_WHEEL: Final[str] = "hiveio_smoke_test_api-1.0.0.post20261104000000-py3-none-any.whl"
PROJECT_ID: Final[str] = "42"


def publish_script() -> str:
    """The Python script of `.python_api_package_publish`, as the job runs it."""
    lines = TEMPLATE.read_text().splitlines()
    job = lines.index(".python_api_package_publish:")
    start = lines.index("      python3 - <<'EOF'", job) + 1
    end = lines.index("      EOF", start)
    return textwrap.dedent("\n".join(lines[start:end]))


@dataclass
class Registry:
    """Simple index of a project's registry - a page per distribution of `index_directory`, 404 when absent."""

    url: str
    index_directory: Path

    def publish(self, *file_names: str) -> None:
        page = "".join(f'<a href="../../files/abc/{name}#sha256=0">{name}</a>\n' for name in file_names)
        (self.index_directory / "hiveio-smoke-test-api").write_text(page)


@pytest.fixture
def registry(tmp_path: Path) -> Iterator[Registry]:
    index_directory = tmp_path / "index"
    index_directory.mkdir()
    prefix = f"/projects/{PROJECT_ID}/packages/pypi/simple/"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            page = index_directory / self.path.removeprefix(prefix)
            if not self.path.startswith(prefix) or not page.is_file():
                self.send_error(404)
                return
            body = page.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # requests are not logged by tests
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Registry(url=f"http://127.0.0.1:{server.server_address[1]}", index_directory=index_directory)
    server.shutdown()
    thread.join()


def run_publish(
    tmp_path: Path, registry: Registry, *, twine_exit_code: int, twine_publishes: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Runs the publish script with `twine` stubbed - it publishes `twine_publishes` and exits with `twine_exit_code`."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / WHEEL).touch()
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    twine = bin_directory / "twine"
    twine.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import sys
            from pathlib import Path
            names = {twine_publishes!r}
            if names:
                page = "".join(f'<a href="../../files/abc/{{name}}">{{name}}</a>' for name in names)
                (Path({str(registry.index_directory)!r}) / "hiveio-smoke-test-api").write_text(page)
            (Path({str(tmp_path)!r}) / "twine-args").write_text(" ".join(sys.argv[1:]))
            sys.exit({twine_exit_code})
            """
        )
    )
    twine.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{bin_directory}{os.pathsep}{os.environ['PATH']}",
        "CI_API_V4_URL": registry.url,
        "CI_PROJECT_ID": PROJECT_ID,
        "TWINE_USERNAME": "gitlab-ci-token",
        "TWINE_PASSWORD": "token",
        "PYTHON_API_DIST_DIR": str(dist),
    }
    return subprocess.run(
        [sys.executable, "-c", publish_script()],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_wheel_absent_from_the_index_is_uploaded(tmp_path: Path, registry: Registry) -> None:
    # ACT
    result = run_publish(tmp_path, registry, twine_exit_code=0)

    # ASSERT
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "twine-args").read_text().endswith(str(tmp_path / "dist" / WHEEL))


def test_wheel_already_in_the_index_is_not_uploaded(tmp_path: Path, registry: Registry) -> None:
    # ARRANGE
    registry.publish(OTHER_WHEEL, WHEEL)

    # ACT
    result = run_publish(tmp_path, registry, twine_exit_code=1)

    # ASSERT
    assert result.returncode == 0, result.stderr
    assert f"{WHEEL} is already published" in result.stdout
    assert not (tmp_path / "twine-args").exists()


def test_failed_upload_of_a_wheel_published_concurrently_succeeds(tmp_path: Path, registry: Registry) -> None:
    # ACT - another pipeline publishes the same file between the check and the upload, the registry rejects the upload
    result = run_publish(tmp_path, registry, twine_exit_code=1, twine_publishes=(WHEEL,))

    # ASSERT
    assert result.returncode == 0, result.stderr
    assert "published concurrently" in result.stdout


@pytest.mark.parametrize(
    "twine_publishes",
    [(), (OTHER_WHEEL,), (WHEEL.removesuffix(".whl"),)],
    ids=["file-still-absent", "other-version-published", "file-name-prefix-published"],
)
def test_failed_upload_of_a_wheel_not_in_the_index_fails(
    tmp_path: Path, registry: Registry, twine_publishes: tuple[str, ...]
) -> None:
    # ACT
    result = run_publish(tmp_path, registry, twine_exit_code=3, twine_publishes=twine_publishes)

    # ASSERT
    assert result.returncode == 3
    assert "published concurrently" not in result.stdout
