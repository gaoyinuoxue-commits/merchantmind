"""Tool invocation service: validate → execute → persist audit log."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tool_call import ToolCallLog
from app.tools.base import (
    ToolSpec,
    ToolValidationError,
    all_tools,
    get_tool,
    validate_arguments,
)


class ToolError(Exception):
    def __init__(self, message: str, code: str = "tool_error"):
        super().__init__(message)
        self.code = code


class ToolService:
    def __init__(self, db: Session, trace_id: Optional[str] = None):
        self.db = db
        self.trace_id = trace_id

    def catalog(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "output_schema": spec.output_schema,
                "permission": spec.permission,
                "risk_level": spec.risk_level,
            }
            for spec in all_tools()
        ]

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            spec = get_tool(name)
        except KeyError:
            raise ToolError(f"unknown tool {name!r}", code="unknown_tool")

        try:
            validate_arguments(spec, arguments)
        except ToolValidationError as exc:
            self._log(spec, arguments, success=False, error=str(exc))
            raise ToolError(str(exc), code="invalid_arguments")

        start = time.perf_counter()
        try:
            data = spec.handler(self.db, arguments)
        except KeyError as exc:
            elapsed = (time.perf_counter() - start) * 1000
            self._log(spec, arguments, success=False, error=str(exc), latency_ms=elapsed)
            raise ToolError(str(exc).strip("'"), code="not_found")
        except Exception as exc:  # defensive: never crash the agent loop silently
            elapsed = (time.perf_counter() - start) * 1000
            self._log(spec, arguments, success=False, error=str(exc)[:500], latency_ms=elapsed)
            raise ToolError(str(exc), code="execution_error")
        elapsed = (time.perf_counter() - start) * 1000
        self._log(spec, arguments, data=data, latency_ms=elapsed)
        return {"tool": name, "arguments": arguments, "data": data}

    def _log(
        self,
        spec: ToolSpec,
        arguments: Dict[str, Any],
        success: bool = True,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> None:
        summary = None
        if data is not None:
            for key in ("cases", "products", "materials", "events"):
                if isinstance(data, dict) and isinstance(data.get(key), list):
                    summary = f"{key}={len(data[key])}"
                    break
            if summary is None:
                summary = "ok"
        log = ToolCallLog(
            tool_name=spec.name,
            merchant_id=arguments.get("merchant_id"),
            trace_id=self.trace_id,
            arguments=arguments,
            result_summary=summary,
            latency_ms=round(latency_ms, 2) if latency_ms is not None else None,
            success=success,
            error=error,
        )
        self.db.add(log)
        self.db.commit()

    def recent_calls(self, limit: int = 50) -> List[ToolCallLog]:
        return list(
            self.db.scalars(
                select(ToolCallLog).order_by(ToolCallLog.created_at.desc()).limit(limit)
            ).all()
        )
