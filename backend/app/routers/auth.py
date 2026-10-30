# Owner: Dev B
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.auth import User

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=User)
def me(user: User = Depends(get_current_user)) -> User:
    return user
