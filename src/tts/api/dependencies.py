"""App-scoped service construction shared by API routes and lifespan."""

from __future__ import annotations

import threading
from typing import cast

from fastapi import FastAPI, Request

from tts.config import Settings
from tts.history.dal import Dal
from tts.jobs.manager import JobManager

_INIT_LOCK = threading.Lock()


def initialize_services(app: FastAPI) -> tuple[Dal, JobManager]:
    """Create missing app-scoped services while preserving injected instances."""
    with _INIT_LOCK:
        settings: Settings = app.state.settings
        dal = getattr(app.state, "dal", None)
        if dal is None:
            dal = Dal(settings.data_dir, history_limit=settings.history_limit)
            app.state.dal = dal

        jobs = getattr(app.state, "jobs", None)
        if jobs is None:
            jobs = JobManager(dal, settings)
            app.state.jobs = jobs
    return cast(Dal, dal), cast(JobManager, jobs)


def get_dal(request: Request) -> Dal:
    """Return the app's shared DAL, creating services if a route runs standalone."""
    dal = getattr(request.app.state, "dal", None)
    if dal is None:
        dal, _ = initialize_services(request.app)
    return cast(Dal, dal)


def get_jobs(request: Request) -> JobManager:
    """Return the app's shared job manager."""
    jobs = getattr(request.app.state, "jobs", None)
    if jobs is None:
        _, jobs = initialize_services(request.app)
    return cast(JobManager, jobs)


def close_services(app: FastAPI) -> None:
    """Stop app-scoped services in dependency order."""
    jobs = getattr(app.state, "jobs", None)
    dal = getattr(app.state, "dal", None)
    close_jobs = getattr(jobs, "close", None)
    close_dal = getattr(dal, "close", None)
    try:
        if callable(close_jobs):
            close_jobs()
    finally:
        if callable(close_dal):
            close_dal()
