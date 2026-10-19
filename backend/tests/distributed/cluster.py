"""A disposable deployment: API replicas and job workers as real OS processes."""

import contextlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import boto3
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_APP_DIR = _BACKEND_DIR / "app"
_SUPPORT_DIR = Path(__file__).resolve().parent / "support"

#: Short enough to see a reclaim in a test, long enough to satisfy JASIL's
#: ``lease_seconds >= 3 * heartbeat_interval_seconds`` rule (15 s heartbeat).
LEASE_SECONDS = 60

_STARTUP_MARKER = "Application startup complete"


@dataclass(frozen=True)
class ClusterConfig:
    """The shared infrastructure a deployment runs against."""

    database_url: str
    redis_url: str
    s3_endpoint_url: str
    s3_bucket: str


@dataclass
class _Process:
    label: str
    popen: subprocess.Popen
    log_path: Path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Cluster:
    """API replicas and workers sharing one database, Redis and bucket.

    The database is created fresh (the API migrates it on startup, as in
    production) and dropped on :meth:`close`; every process is killed then too.
    """

    def __init__(self, config: ClusterConfig, tmp_path: Path, *, name: str) -> None:
        url = make_url(config.database_url)
        if "test" not in (url.database or ""):
            raise RuntimeError("TEST_DATABASE_URL must name a disposable database whose name contains 'test'")
        self._config = config
        self._url = url
        self._db_name = f"{url.database}_{re.sub(r'\W+', '_', name).lower()}"[:60]
        self._dir = tmp_path
        self._processes: list[_Process] = []
        self._apis = 0
        self._workers = 0
        self._admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with self._admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{self._db_name}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{self._db_name}"'))
        self.engine: Engine = create_engine(url.set(database=self._db_name))
        self._reset_shared_services()

    # -- environment ---------------------------------------------------------

    def _reset_shared_services(self) -> None:
        import redis

        redis.Redis.from_url(self._config.redis_url).flushdb()
        self._aws_config = self._dir / "aws_config"
        self._aws_config.write_text("[default]\ns3 =\n    addressing_style = path\n")
        self._s3_env = {
            "AWS_ENDPOINT_URL": self._config.s3_endpoint_url,
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_CONFIG_FILE": str(self._aws_config),
        }
        with _PatchedEnviron(self._s3_env):
            client = boto3.client("s3")
            if self._config.s3_bucket not in {bucket["Name"] for bucket in client.list_buckets()["Buckets"]}:
                client.create_bucket(Bucket=self._config.s3_bucket)
            for page in client.get_paginator("list_objects_v2").paginate(Bucket=self._config.s3_bucket):
                for obj in page.get("Contents", []):
                    client.delete_object(Bucket=self._config.s3_bucket, Key=obj["Key"])

    def env(self, *, distributed: bool, port: int = 8080) -> dict[str, str]:
        """The environment of one process of this deployment."""
        env = dict(os.environ)
        for var in ("TEST_DATABASE_URL", "DATABASE_URL"):
            env.pop(var, None)
        data = self._dir / "data"
        for sub in ("files", "logs"):
            (data / sub).mkdir(parents=True, exist_ok=True)
        frontend = self._dir / "frontend"
        frontend.mkdir(exist_ok=True)
        (frontend / "index.html").write_text("<html></html>")
        env.update(
            DB_HOST=self._url.host or "localhost",
            DB_PORT=str(self._url.port or 5432),
            DB_USER=self._url.username or "",
            DB_PASSWORD=self._url.password or "",
            DB_DATABASE=self._db_name,
            SECRET_KEY="test-secret-key-for-testing-purposes-minimum-32-characters-long",
            FERNET_KEY="CDpRchmDIJvecXEB3KTahUnkf8WkLvPXTnrw64JkknQ=",
            DATA_DIR=str(data),
            FILES_DIR=str(data / "files"),
            LOGS_DIR=str(data / "logs"),
            FRONTEND_DIR=str(frontend),
            BACKEND_DIR=str(_BACKEND_DIR),
            ENVIRONMENT="production",
            ENDURAIN_HOST=f"http://localhost:{port}",
            PYTHONUNBUFFERED="1",
            REDIS_URL=self._config.redis_url,
            JOBS_ENABLED="true",
            JOBS_RUN_IN_PROCESS_WORKER="false",
            JOBS_POLL_INTERVAL_SECONDS="1",
            JOBS_LEASE_SECONDS=str(LEASE_SECONDS),
            DEPLOYMENT_PROFILE="distributed" if distributed else "local",
        )
        if distributed:
            env.update(STORAGE_URI=f"s3://{self._config.s3_bucket}", **self._s3_env)
        return env

    # -- processes -----------------------------------------------------------

    def _spawn(self, label: str, argv: list[str], env: dict[str, str]) -> _Process:
        log_path = self._dir / f"{label}.log"
        popen = subprocess.Popen(  # noqa: S603 - fixed argv built from this repo's own entry points
            argv,
            cwd=_APP_DIR,
            env=env,
            stdout=log_path.open("w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        process = _Process(label, popen, log_path)
        self._processes.append(process)
        return process

    def start_api(self, *, distributed: bool, timeout: float = 150) -> _Process:
        """Start an API replica and wait until it has finished starting up."""
        port = _free_port()
        process = self._spawn(
            f"api{self._apis}",
            [sys.executable, "-m", "uvicorn", "main:app", "--port", str(port)],
            self.env(distributed=distributed, port=port),
        )
        self._apis += 1
        assert self.wait_for(lambda: _STARTUP_MARKER in process.log_path.read_text(), timeout), (
            f"{process.label} did not start:\n{process.log_path.read_text()[-2000:]}"
        )
        return process

    def start_worker(self, *, distributed: bool, slow_seconds: float | None = None) -> _Process:
        """Start a durable-job worker, optionally one whose upload processing is delayed."""
        env = self.env(distributed=distributed)
        script = "worker.py"
        if slow_seconds is not None:
            env["SLOW_SECONDS"] = str(slow_seconds)
            script = str(_SUPPORT_DIR / "slow_worker.py")
        process = self._spawn(f"worker{self._workers}", [sys.executable, script], env)
        self._workers += 1
        return process

    @staticmethod
    def kill(process: _Process) -> None:
        """SIGKILL a process and everything it started, with no chance to clean up."""
        os.killpg(process.popen.pid, signal.SIGKILL)
        process.popen.wait(timeout=10)

    def log(self, process: _Process) -> str:
        return process.log_path.read_text()

    def error_lines(self) -> list[str]:
        """Every error-level or traceback line any process has logged."""
        return [
            f"{process.label}: {line[:200]}"
            for process in self._processes
            for line in process.log_path.read_text().splitlines()
            if '"level": "ERROR"' in line or "Traceback" in line
        ]

    # -- driving and observing ----------------------------------------------

    def accept_uploads(self, count: int, tag: str, *, distributed: bool) -> list[str]:
        """Accept GPX uploads the way an API replica does and return their job ids."""
        result = subprocess.run(  # noqa: S603 - fixed argv built from this repo's own entry points
            [sys.executable, str(_SUPPORT_DIR / "accept_uploads.py"), str(count), tag],
            cwd=_APP_DIR,
            env=self.env(distributed=distributed),
            capture_output=True,
            text=True,
            timeout=120,
        )
        line = next((line for line in result.stdout.splitlines() if line.startswith("JOBS ")), None)
        assert line is not None, f"upload driver failed:\n{result.stderr[-2000:]}"
        return json.loads(line.removeprefix("JOBS "))

    def query(self, sql: str, **params) -> list[tuple]:
        with self.engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(sql), params)]

    def scalar(self, sql: str, **params):
        return self.query(sql, **params)[0][0]

    def job_status(self, job_id: str) -> str:
        return self.scalar("SELECT status FROM activity_ingestion_jobs WHERE id = :id", id=job_id)

    @staticmethod
    def wait_for(condition: Callable[[], object], timeout: float, interval: float = 0.5) -> bool:
        """Poll ``condition`` until it is truthy or ``timeout`` seconds pass."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return True
            time.sleep(interval)
        return bool(condition())

    def wait_for_uploads(self, job_ids: list[str], timeout: float = 120) -> bool:
        """Wait until every upload job is terminal; returns whether they all got there."""
        return self.wait_for(lambda: all(self.job_status(job) in ("completed", "failed") for job in job_ids), timeout)

    def wait_for_durable_jobs(self, expected: int, timeout: float = 90) -> bool:
        """Wait until exactly ``expected`` durable jobs exist and every one has completed.

        The count matters: the upload job completes before the outbox relay has
        turned its ``activity.created`` into the derived jobs, so "nothing is open"
        is also true in that gap.
        """
        return self.wait_for(
            lambda: (
                self.scalar("SELECT count(*) FROM processing_jobs") == expected
                and self.scalar("SELECT count(*) FROM processing_jobs WHERE status <> 'completed'") == 0
            ),
            timeout,
        )

    # -- teardown ------------------------------------------------------------

    def close(self) -> None:
        for process in self._processes:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.popen.pid, signal.SIGTERM)
        for process in self._processes:
            try:
                process.popen.wait(timeout=20)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(process.popen.pid, signal.SIGKILL)
        self.engine.dispose()
        with self._admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{self._db_name}" WITH (FORCE)'))
        self._admin.dispose()


class _PatchedEnviron:
    """Set environment variables for a block, then restore them."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values
        self._saved: dict[str, str | None] = {}

    def __enter__(self) -> None:
        for key, value in self._values.items():
            self._saved[key] = os.environ.get(key)
            os.environ[key] = value

    def __exit__(self, *_exc) -> None:
        for key, old in self._saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
