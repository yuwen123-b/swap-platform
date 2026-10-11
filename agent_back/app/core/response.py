from typing import Any
from fastapi.responses import JSONResponse


def success(data: Any = None, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


def error_response(code: int, message: str, status_code: int | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code or code, content={"code": code, "message": message, "data": None})
