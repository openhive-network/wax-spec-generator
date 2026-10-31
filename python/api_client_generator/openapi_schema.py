"""Components of OpenAPI definitions and references to them - shared by flattening, deduplication and custom types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

COMPONENT_REF_PREFIX: Final[str] = "#/components/schemas/"
"""Prefix of `$ref` values referring to components (`components/schemas`) of the definition."""


def component_schemas(definition: Mapping[str, object]) -> dict[str, object]:
    """Schemas of the components of the definition (`components/schemas`) - empty when there are none."""
    components = definition.get("components")
    schemas = components.get("schemas") if isinstance(components, dict) else None
    return schemas if isinstance(schemas, dict) else {}


def component_reference(name: str) -> str:
    """`$ref` value referring to the component of the given name."""
    return f"{COMPONENT_REF_PREFIX}{name}"


def referenced_component(schema: Mapping[str, object], components: Mapping[str, object]) -> object | None:
    """The component the `$ref` of the schema refers to - None when the schema refers to no component."""
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith(COMPONENT_REF_PREFIX):
        return components.get(reference.removeprefix(COMPONENT_REF_PREFIX))
    return None


def set_member(container: dict[str, object] | list[object], key: str | int, value: object) -> None:
    """Set the member of a JSON object (string key) or array (index)."""
    if isinstance(container, dict) and isinstance(key, str):
        container[key] = value
        return
    if isinstance(container, list) and isinstance(key, int):
        container[key] = value
