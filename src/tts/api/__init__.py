"""API router registry.

Append-only: each new routes module adds one entry. Consumers include every
router under the ``/api`` prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from tts.api.routes import health

ROUTERS: list[APIRouter] = [health.router]
