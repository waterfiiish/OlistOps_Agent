from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class PermissionLevel(StrEnum):
    READ = "READ"
    GENERATE = "GENERATE"
    PERSIST = "PERSIST"
    EXTERNAL_WRITE = "EXTERNAL_WRITE"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    permission: PermissionLevel
    handler: Callable[[Any], Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown or disallowed tool: {name}") from exc

    def list(
        self, *, max_permission: PermissionLevel = PermissionLevel.READ
    ) -> list[ToolDefinition]:
        order = list(PermissionLevel)
        ceiling = order.index(max_permission)
        return [
            tool for tool in self._tools.values() if order.index(tool.permission) <= ceiling
        ]

    def invoke(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self.get(name)
        if tool.permission in {PermissionLevel.PERSIST, PermissionLevel.EXTERNAL_WRITE}:
            raise PermissionError(f"{name} requires explicit approval")
        validated = tool.input_model.model_validate(arguments)
        return tool.handler(validated)
