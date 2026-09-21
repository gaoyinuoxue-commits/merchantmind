from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.tools import ToolCallLogOut, ToolInvokeIn, ToolInvokeOut, ToolSpecOut
from app.tools.service import ToolError, ToolService

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=List[ToolSpecOut])
def list_tools(db: Session = Depends(get_db)) -> List[dict]:
    return ToolService(db).catalog()


@router.post("/{tool_name}/invoke", response_model=ToolInvokeOut)
def invoke_tool(
    tool_name: str, payload: ToolInvokeIn, db: Session = Depends(get_db)
) -> dict:
    service = ToolService(db)
    try:
        return service.invoke(tool_name, payload.arguments)
    except ToolError as exc:
        status_code = 404 if exc.code == "not_found" else 400
        if exc.code == "unknown_tool":
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=str(exc))


@router.get("/calls/recent", response_model=List[ToolCallLogOut])
def recent_calls(limit: int = 50, db: Session = Depends(get_db)):
    limit = min(max(1, limit), 200)
    return ToolService(db).recent_calls(limit)
