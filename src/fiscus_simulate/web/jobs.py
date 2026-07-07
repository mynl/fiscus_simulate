"""In-process run-job registry for the web layer.

A browser-launched simulation runs **synchronously** when it is small and in a **daemon
thread** when it is large (more than :data:`SYNC_THRESHOLD` scenarios), so the UI never
wedges on the ~22 s 100k run. This is single-process, localhost state — a plain dict
behind a lock, no queue, no cross-process durability (a killed server forgets in-flight
jobs; a completed run is already persisted on disk by :mod:`fiscus_simulate.storage`).

Duplicate-submit protection lives here too: :meth:`JobRegistry.submit` refuses to start
a second in-flight run for a config that already has one, returning the existing job.
"""
from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..models import RunConfig
from ..service import run_simulation

# At or below this many scenarios a run executes inline in the request (≈ a couple of
# seconds); above it the run goes to a background thread with a polled status page.
SYNC_THRESHOLD = 20_000

_ACTIVE = ("queued", "running")


@dataclass
class Job:
    """A single launched run and its lifecycle state."""

    job_id: str
    config_name: str
    n_scenarios: int
    state: str = "queued"  # queued | running | complete | failed
    run_id: str | None = None
    error: str | None = None

    @property
    def active(self) -> bool:
        """True while the job has not reached a terminal state."""
        return self.state in _ACTIVE


class JobRegistry:
    """Thread-safe registry of run jobs (one per process)."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        """Return the job with this id, or None."""
        with self._lock:
            return self._jobs.get(job_id)

    def active_for(self, config_name: str) -> Job | None:
        """Return an in-flight job for ``config_name``, or None."""
        with self._lock:
            for job in self._jobs.values():
                if job.config_name == config_name and job.active:
                    return job
        return None

    def submit(self, config_name: str, cfg: RunConfig, runs_dir: Path) -> Job:
        """Launch a run for ``cfg``; small runs execute inline, large ones in a thread.

        Idempotent: if a run for ``config_name`` is already in flight, that job is
        returned unchanged rather than starting a second one.
        """
        existing = self.active_for(config_name)
        if existing is not None:
            return existing

        job = Job(
            job_id=uuid.uuid4().hex[:12],
            config_name=config_name,
            n_scenarios=int(cfg.simulation.n_scenarios),
        )
        with self._lock:
            self._jobs[job.job_id] = job

        if job.n_scenarios <= SYNC_THRESHOLD:
            self._run(job, cfg, runs_dir)  # inline; job is terminal on return
        else:
            threading.Thread(
                target=self._run, args=(job, cfg, runs_dir), daemon=True
            ).start()
        return job

    def _run(self, job: Job, cfg: RunConfig, runs_dir: Path) -> None:
        job.state = "running"
        try:
            result = run_simulation(cfg, persist=True, runs_dir=runs_dir)
            job.run_id = result.meta.get("run_id")
            job.state = "complete"
        except Exception as exc:  # noqa: BLE001 - any failure is surfaced to the status page
            job.error = f"{type(exc).__name__}: {exc}"
            job.state = "failed"
            traceback.print_exc()
