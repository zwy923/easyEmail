"""Aggregated email related API routers."""
from fastapi import APIRouter

from . import accounts, auth, emails, sync

router = APIRouter()

router.include_router(auth.router)
router.include_router(sync.router)
router.include_router(accounts.router)
router.include_router(emails.router)

__all__ = ["router"]
