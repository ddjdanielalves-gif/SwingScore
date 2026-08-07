from __future__ import annotations

from fastapi import APIRouter

from ..schemas import MacroResponse
from ..services import macro as macro_service

router = APIRouter(prefix="/api", tags=["macro"])


@router.get("/macro", response_model=MacroResponse)
def get_macro():
    return MacroResponse(macro=macro_service.collect())
