"""Tool registry contract: explicit JSON-schema inputs/outputs, permission and
risk metadata. All phase-9 tools are read-only; write actions arrive in phase 13.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class ToolValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    permission: str = "read"
    risk_level: str = "read"
    handler: Optional[Callable[..., Dict[str, Any]]] = field(default=None, compare=False)


_REGISTRY: Dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in _REGISTRY:
        raise ValueError(f"duplicate tool: {spec.name}")
    _REGISTRY[spec.name] = spec
    return spec


def get_tool(name: str) -> ToolSpec:
    if name not in _REGISTRY:
        raise KeyError(name)
    return _REGISTRY[name]


def all_tools() -> List[ToolSpec]:
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


_TYPE_CHECKS = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def validate_arguments(spec: ToolSpec, arguments: Dict[str, Any]) -> Dict[str, Any]:
    schema = spec.input_schema
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    if not isinstance(arguments, dict):
        raise ToolValidationError("arguments must be an object")
    keys = set(arguments)
    missing = required - keys
    if missing:
        raise ToolValidationError(f"missing required arguments: {', '.join(sorted(missing))}")
    unknown = keys - set(properties)
    if unknown:
        raise ToolValidationError(f"unknown arguments: {', '.join(sorted(unknown))}")
    for key, value in arguments.items():
        rule = properties[key]
        expected = _TYPE_CHECKS.get(rule.get("type"))
        if expected and not isinstance(value, expected):
            raise ToolValidationError(f"argument {key!r} must be {rule.get('type')}")
        if "enum" in rule and value not in rule["enum"]:
            raise ToolValidationError(f"argument {key!r} must be one of {rule['enum']}")
        if rule.get("type") == "string":
            if "minLength" in rule and len(value) < rule["minLength"]:
                raise ToolValidationError(f"argument {key!r} too short")
        if rule.get("type") in {"integer", "number"}:
            if "minimum" in rule and value < rule["minimum"]:
                raise ToolValidationError(f"argument {key!r} below minimum")
            if "maximum" in rule and value > rule["maximum"]:
                raise ToolValidationError(f"argument {key!r} above maximum")
    return arguments
