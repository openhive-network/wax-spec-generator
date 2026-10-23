"""
Deduplication of models of a flattened OpenAPI definition - object schemas equal in structure become one component.

Flattening (`openapi_flattening`) inlines every `$ref`, so a component referenced from several places - and any object
schema written in several places - is generated as a separate model at each of them, named after the property holding
it and numbered when the name repeats (`VotingManabar`, `DownvoteManabar`, `DecayParams12`). Deduplication finds object
schemas equal in structure and replaces them by a `$ref` to one component, so one model is generated for them:

- the structure of a schema is everything except documentation (`description`, `title`, `example`, `examples`) - names,
  types and constraints of properties, required properties, vendor extensions - with nested schemas compared the same
  way, so objects holding equal objects are equal too,
- object schemas with the vendor extension of custom types (`model_options.CustomTypes.extension`) are not models - they
  are replaced by custom types,
- a schema equal to a component is replaced by a reference to that component (to the one referenced most often in the
  original definition, when several components are equal) - components themselves stay as they are,
- schemas equal to no component are moved to a new component when they appear at least twice, named after the
  property holding them most often (the first one found, of equally frequent; the singular form for elements of arrays,
  e.g. `beneficiary` of `beneficiaries`), or after the component holding it and the property when that name is taken,
- descriptions given at the replaced places are kept next to the `$ref` (documentation of the properties).
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final

from datamodel_code_generator.reference import get_singular_name

from api_client_generator.openapi_schema import (
    COMPONENT_REF_PREFIX,
    component_reference,
    component_schemas,
    set_member,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

_DOCUMENTATION_KEYWORDS: Final[frozenset[str]] = frozenset({"description", "title", "example", "examples"})
_ELEMENT_KEYWORDS: Final[frozenset[str]] = frozenset({"items", "prefixItems", "additionalProperties"})


@dataclass
class _Occurrence:
    """An object schema inside a component (or a path), held by `container[key]`."""

    container: dict[str, object] | list[object]
    key: str | int
    schema: dict[str, object]
    holder: str | None
    """Name of the property holding the schema - singular for elements of arrays and maps, None when unknown."""
    component: str | None
    """Name of the component holding the schema, None in paths."""


def deduplicate_models(
    flattened: dict[str, object], original: Mapping[str, object], *, custom_type_extension: str | None = None
) -> dict[str, object]:
    """
    Replace object schemas equal in structure in the flattened definition by references to single components.

    Args:
        flattened: Flattened definition (`openapi_flattening.flatten_openapi`) - changed in place.
        original: The definition before flattening - references in it decide which of equal components is used.
        custom_type_extension: Vendor extension of custom types (`model_options.CustomTypes.extension`) - schemas
            having it are replaced by custom types, not generated as models.

    Returns:
        The flattened definition.
    """
    components = component_schemas(flattened)
    reference_counts = Counter(re.findall(rf'"{re.escape(COMPONENT_REF_PREFIX)}([^"]+)"', json.dumps(original)))

    is_model = partial(_is_model, custom_type_extension=custom_type_extension)
    occurrences = [occurrence for occurrence in _occurrences(flattened, components) if is_model(occurrence.schema)]
    structure_of: dict[int, str] = {}
    by_structure: defaultdict[str, list[_Occurrence]] = defaultdict(list)
    for occurrence in occurrences:
        by_structure[_structure(occurrence.schema, structure_of)].append(occurrence)
    components_by_structure: defaultdict[str, list[str]] = defaultdict(list)
    for name, schema in components.items():
        if is_model(schema):
            components_by_structure[_structure(schema, structure_of)].append(name)

    taken = set(components)
    # inner schemas first - schemas holding them are then copied to new components with the references
    for structure, found in sorted(by_structure.items(), key=lambda item: _depth(item[1][0].schema)):
        equal_components = components_by_structure.get(structure, [])
        if equal_components:
            target = min(equal_components, key=lambda name: (-reference_counts[name], name))
        elif len(found) > 1:
            target = _new_component_name(found, taken)
            taken.add(target)
            components[target] = copy.deepcopy(found[0].schema)
        else:
            continue
        for occurrence in found:
            _replace_by_reference(occurrence, target)
    return flattened


def _is_model(schema: object, *, custom_type_extension: str | None = None) -> bool:
    """An object schema generated as a model - with properties, not replaced by a custom type."""
    if not isinstance(schema, dict) or "$ref" in schema:
        return False
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return False
    kind = schema.get("type", "object")  # e.g. an array with properties is not a model (a tuple of its items)
    if kind != "object" and not (isinstance(kind, list) and "object" in kind):
        return False
    return custom_type_extension is None or custom_type_extension not in schema


def _occurrences(definition: dict[str, object], components: dict[str, object]) -> Iterator[_Occurrence]:
    """Object schemas held by components (not the components themselves) and by paths."""
    for name, component in components.items():
        yield from _nested(component, holder=None, component=name)
    yield from _nested(definition.get("paths"), holder=None, component=None)


def _nested(value: object, *, holder: str | None, component: str | None) -> Iterator[_Occurrence]:
    """
    Object schemas inside the value - named after the properties holding them.

    Elements of arrays and maps are named after the singular form of the property (as datamodel-code-generator names
    them, e.g. `beneficiaries` - `beneficiary`).
    """
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _member(value, index, item, holder=holder, component=component)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"properties", "patternProperties"} and isinstance(item, dict):
                for property_name, property_schema in item.items():
                    yield from _member(item, property_name, property_schema, holder=property_name, component=component)
            elif key in _ELEMENT_KEYWORDS and holder is not None:
                yield from _member(value, key, item, holder=get_singular_name(holder), component=component)
            else:
                yield from _member(value, key, item, holder=holder, component=component)


def _member(
    container: dict[str, object] | list[object],
    key: str | int,
    value: object,
    *,
    holder: str | None,
    component: str | None,
) -> Iterator[_Occurrence]:
    if _is_model(value):
        assert isinstance(value, dict)
        yield _Occurrence(container, key, value, holder, component)
    yield from _nested(value, holder=holder, component=component)


def _structure(schema: object, cache: dict[int, str]) -> str:
    """The structure of the schema - JSON without documentation, keys sorted (also of `required`)."""
    if isinstance(schema, dict):
        if id(schema) in cache:
            return cache[id(schema)]
        members = {
            key: sorted(value) if key == "required" and isinstance(value, list) else _structure_value(value, cache)
            for key, value in schema.items()
            if key not in _DOCUMENTATION_KEYWORDS
        }
        structure = json.dumps(members, sort_keys=True, separators=(",", ":"))
        cache[id(schema)] = structure
        return structure
    return json.dumps(_structure_value(schema, cache), sort_keys=True, separators=(",", ":"))


def _structure_value(value: object, cache: dict[int, str]) -> object:
    if isinstance(value, dict):
        return json.loads(_structure(value, cache))
    if isinstance(value, list):
        return [_structure_value(item, cache) for item in value]
    return value


def _depth(schema: object) -> int:
    if isinstance(schema, dict):
        return 1 + max((_depth(value) for value in schema.values()), default=0)
    if isinstance(schema, list):
        return max((_depth(value) for value in schema), default=0)
    return 0


def _new_component_name(found: list[_Occurrence], taken: set[str]) -> str:
    # the most frequent names first, of equally frequent the first one found (sorting is stable)
    holders = Counter(occurrence.holder for occurrence in found if occurrence.holder is not None)
    candidates = [name for name, _ in sorted(holders.items(), key=lambda item: -item[1])]
    owners = Counter(
        f"{occurrence.component}_{occurrence.holder}"
        for occurrence in found
        if occurrence.holder is not None and occurrence.component is not None
    )
    candidates += [name for name, _ in sorted(owners.items(), key=lambda item: -item[1])]
    for candidate in candidates:
        if candidate not in taken:
            return candidate
    base = candidates[0] if candidates else "model"
    number = 1
    while f"{base}_{number}" in taken:
        number += 1
    return f"{base}_{number}"


def _replace_by_reference(occurrence: _Occurrence, target: str) -> None:
    reference: dict[str, object] = {"$ref": component_reference(target)}
    description = occurrence.schema.get("description")
    if isinstance(description, str):
        reference["description"] = description
    set_member(occurrence.container, occurrence.key, reference)
