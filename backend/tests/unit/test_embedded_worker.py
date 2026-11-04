"""The free-plan option: the Celery worker and its beat run inside the API container, only when asked.

It never blocks the API. Pure shell behaviour with fake `celery`, `sleep` and `uvicorn` executables on the PATH:
no broker, no database, no network.
"""

import os
import stat
import subprocess
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SECRET_URL = "redis://:s3cret-password@red-abc123:6379"


def _fakes(tmp_path: Path, celery_status: int = 1) -> Path:
    """A bin/ dir with a `celery` that records its arguments, a `sleep` that records and ends the loop on the 3rd call,
    and a `uvicorn` that records and returns at once."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    scripts = {
        "celery": f'echo "$@" >> "{tmp_path}/celery.log"\nexit {celery_status}\n',
        "sleep": (
            f'echo "$1" >> "{tmp_path}/sleep.log"\n'
            f'if [ "$(wc -l < "{tmp_path}/sleep.log")" -ge 3 ]; then kill $PPID; fi\n'
        ),
        "uvicorn": f'echo "$@" >> "{tmp_path}/uvicorn.log"\n',
    }
    for name, body in scripts.items():
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _env(tmp_path: Path, **over: str) -> dict:
    base = {k: v for k, v in os.environ.items() if not k.startswith(("CELERY_", "EMBEDDED_", "RUN_MIGRATIONS"))}
    base["PATH"] = f"{tmp_path / 'bin'}:{base['PATH']}"
    base.update(over)
    return base


def _run_worker(tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(BACKEND / "embedded_worker.sh")],
        env=_env(tmp_path, **env),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=tmp_path,
    )


def _lines(path: Path) -> list:
    return path.read_text().splitlines() if path.exists() else []


def test_the_script_is_executable_and_uses_a_single_process_with_its_beat():
    script = BACKEND / "embedded_worker.sh"
    assert os.stat(script).st_mode & stat.S_IXUSR
    text = script.read_text()
    assert "--beat" in text and "--pool=solo" in text  # one process: the free instance has 512 MB
    assert text.index("CELERY_BROKER_URL") < text.index("celery -A celery_app worker")  # the broker is checked first


def test_without_a_broker_nothing_starts_and_the_log_says_what_to_set(tmp_path):
    _fakes(tmp_path)
    done = _run_worker(tmp_path, EMBEDDED_WORKER="1")
    assert done.returncode == 0  # the API must keep serving
    assert "CELERY_BROKER_URL" in done.stderr and "no worker started" in done.stderr
    assert _lines(tmp_path / "celery.log") == []


def test_a_broker_that_points_at_the_container_itself_is_refused(tmp_path):
    _fakes(tmp_path)
    for url in ("redis://localhost:6379/0", "redis://127.0.0.1:6379/0", "amqp://guest@red-abc:5672//"):
        done = _run_worker(tmp_path, CELERY_BROKER_URL=url)
        assert done.returncode == 0 and "no worker started" in done.stderr, url
    assert _lines(tmp_path / "celery.log") == []


def test_queues_are_checked_before_anything_is_started(tmp_path):
    _fakes(tmp_path)
    done = _run_worker(tmp_path, CELERY_BROKER_URL=SECRET_URL, EMBEDDED_WORKER_QUEUES="sends; rm -rf /")
    assert done.returncode == 0 and "EMBEDDED_WORKER_QUEUES" in done.stderr
    assert _lines(tmp_path / "celery.log") == []


def test_the_worker_runs_the_blueprint_queues_with_its_beat_restarts_with_a_growing_delay_and_hides_the_url(tmp_path):
    _fakes(tmp_path)
    done = _run_worker(tmp_path, CELERY_BROKER_URL=SECRET_URL)
    calls = _lines(tmp_path / "celery.log")
    assert len(calls) == 3  # crashed three times: restarted each time
    for call in calls:
        assert call.startswith("-A celery_app worker --beat --pool=solo")
        assert "--queues sends,automation,webhooks" in call and "--loglevel info" in call
    assert _lines(tmp_path / "sleep.log") == ["5", "10", "20"]  # a crash loop backs off, it never spins
    assert "s3cret" not in done.stderr + done.stdout  # the broker password is never printed


def test_queues_and_level_can_be_narrowed(tmp_path):
    _fakes(tmp_path)
    _run_worker(
        tmp_path,
        CELERY_BROKER_URL=SECRET_URL,
        EMBEDDED_WORKER_QUEUES="automation,webhooks",
        EMBEDDED_WORKER_LOGLEVEL="warning",
    )
    first = _lines(tmp_path / "celery.log")[0]
    assert "--queues automation,webhooks" in first and "--loglevel warning" in first


def _start(tmp_path: Path, **env: str) -> list:
    """Run start.sh (migrations skipped) and wait for the fake uvicorn, which `exec` replaces the shell with."""
    _fakes(tmp_path)
    subprocess.run(
        ["sh", str(BACKEND / "start.sh")],
        env=_env(tmp_path, RUN_MIGRATIONS="0", **env),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=tmp_path,
    )
    deadline = time.time() + 5
    while time.time() < deadline and not (tmp_path / "sleep.log").exists() and env.get("EMBEDDED_WORKER") == "1":
        time.sleep(0.05)
    time.sleep(0.2)
    return _lines(tmp_path / "uvicorn.log")


def test_by_default_the_api_starts_alone(tmp_path):
    uvicorn = _start(tmp_path, CELERY_BROKER_URL=SECRET_URL)
    assert len(uvicorn) == 1 and "server:app" in uvicorn[0]
    assert _lines(tmp_path / "celery.log") == []  # a broker alone does not start a worker: it is opt-in


def test_only_the_explicit_switch_starts_the_worker_beside_the_api(tmp_path):
    uvicorn = _start(tmp_path, CELERY_BROKER_URL=SECRET_URL, EMBEDDED_WORKER="1")
    assert len(uvicorn) == 1 and "server:app" in uvicorn[0]  # the API starts either way
    assert _lines(tmp_path / "celery.log")  # and the worker started beside it
    for off in ("0", "", "true"):
        other = tmp_path / f"off-{off or 'empty'}"
        other.mkdir()
        _start(other, CELERY_BROKER_URL=SECRET_URL, EMBEDDED_WORKER=off)
        assert _lines(other / "celery.log") == [], off


def test_start_still_ends_on_exec_uvicorn_after_the_optional_worker():
    script = (BACKEND / "start.sh").read_text()
    assert script.index("alembic upgrade head") < script.index("embedded_worker.sh") < script.index("exec uvicorn")
    assert '[ "${EMBEDDED_WORKER:-0}" = "1" ]' in script  # off unless exactly 1
