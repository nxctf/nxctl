"""Root API routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def root():
    return {
        "message": "NXCTL API is running",
        "status": "ok",
    }
