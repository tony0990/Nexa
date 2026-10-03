"""Worker process runner: single-instance lock, logging, signals, graceful shutdown."""
from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from nexa.scheduling.queue import ConnectionFactory, connect

from .heartbeat import Heartbeat
from .service import WorkerDependencies, WorkerService
from .single_instance import SingleInstanceLock

EXIT_OK, EXIT_ALREADY_RUNNING, EXIT_ERROR = 0, 3, 4


@dataclass
class WorkerConfig:
    db_path: str
    poll_interval: float = 10.0
    batch_size: int = 50
    log_dir: Optional[str] = None
    instance_name: str = "NexaWorker"
    lock_dir: Optional[str] = None

    def factory(self) -> ConnectionFactory:
        return lambda: connect(self.db_path)


def configure_logging(log_dir: Optional[str]) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "worker.log"), maxBytes=2_000_000, backupCount=5, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def install_signal_handlers(service: WorkerService) -> None:
    def _handler(signum, _frame):
        logging.getLogger("nexa.worker").info("signal %s received - shutting down", signum)
        service.stop()
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):          # SIGBREAK = Ctrl+Break / console close on Windows
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                pass


def run_worker(config: WorkerConfig, build_dependencies: Callable[[WorkerConfig], WorkerDependencies],
               *, once: bool = False) -> int:
    """Entry used by apps/nexa_worker.py. Runs without any GUI."""
    configure_logging(config.log_dir)
    log = logging.getLogger("nexa.worker")
    lock = SingleInstanceLock(config.instance_name, config.lock_dir)
    if not lock.acquire():
        log.error("another NexaWorker instance is already running")
        return EXIT_ALREADY_RUNNING
    try:
        deps = build_dependencies(config)
        hb = Heartbeat(config.factory(), deps.clock)
        service = WorkerService(deps, poll_interval=config.poll_interval,
                                batch_size=config.batch_size, heartbeat=hb)
        install_signal_handlers(service)
        if once:
            summary = service.run_once(deps.clock())
            hb.beat(summary.as_dict())
            log.info("run_once: %s", summary.as_dict())
            return EXIT_OK
        log.info("NexaWorker started (db=%s, interval=%ss)", config.db_path, config.poll_interval)
        service.run_forever()
        return EXIT_OK
    except Exception:
        log.exception("worker crashed")
        return EXIT_ERROR
    finally:
        lock.release()
