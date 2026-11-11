"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from core.services import Services


def get_services(request: Request) -> Services:
    """The app's services, with UI-saved keys/preferences re-applied."""
    services: Services = request.app.state.services
    services.reload_user_config()
    return services


S = Annotated[Services, Depends(get_services)]
