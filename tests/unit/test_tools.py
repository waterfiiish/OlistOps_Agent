import pytest
from pydantic import BaseModel

from packages.tools.registry import PermissionLevel, ToolDefinition, ToolRegistry


class Input(BaseModel):
    value: int


def test_registry_validates_input() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="read",
            description="test",
            input_model=Input,
            permission=PermissionLevel.READ,
            handler=lambda value: value.value * 2,
        )
    )
    assert registry.invoke("read", {"value": 4}) == 8


def test_registry_blocks_write_without_approval() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="persist",
            description="test",
            input_model=Input,
            permission=PermissionLevel.PERSIST,
            handler=lambda value: value.value,
        )
    )
    with pytest.raises(PermissionError, match="requires explicit approval"):
        registry.invoke("persist", {"value": 1})

