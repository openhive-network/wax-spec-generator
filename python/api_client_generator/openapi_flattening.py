"""
Flattening of OpenAPI definitions - models generated from a flattened definition are named after the properties
holding them instead of the components they refer to.

The definition is flattened exactly as json-schema-ref-parser (`dereference`) followed by json-schema-merge-allof
did it, including the order of keys (it decides the order of generated fields) and which of the descriptions given
next to a `$ref` and in the referenced schema is kept:

- every `$ref` is replaced by the referenced value. Keys given next to a `$ref` are merged with the referenced value:
  they win when the referenced value is resolved for the first time, otherwise (a `$ref` without other keys already
  resolved the same value) they are only added to it,
- `allOf` is merged into one schema: properties are merged per property, `required` lists are united and sorted,
  `type` is taken from the last member (e.g. an object overridden by an array) and other keywords from the first one,
  the keys of merged schemas are ordered as json-schema-merge-allof orders them. Equal values given by several members
  are merged once (compared by equality - json-schema-merge-allof compares them with json-schema-compare, which also
  treats e.g. differently ordered `required` lists as equal; such values are merged by their keywords here),
- nullable `anyOf` (`[null, X]`) is kept as `[{"type": "null"}, X]` (generated as `X | None`), any other `anyOf` and
  `oneOf` are kept (generated as unions; json-schema-merge-allof replaced such `anyOf` by its first member).

Only keywords used by OpenAPI definitions of APIs are merged - an `allOf` combining others (e.g. different `oneOf`s)
raises `OpenApiFlatteningError`, as do references outside the definition and circular references.
"""

from __future__ import annotations

import copy
import json
import re
from typing import TYPE_CHECKING, Final, TypeIs

from api_client_generator.exceptions import OpenApiFlatteningError
from api_client_generator.openapi_deduplication import deduplicate_models
from api_client_generator.openapi_schema import set_member

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path


class _Undefined:
    """Missing value (`undefined` of the flattened JSON - not JSON `null`)."""

    def __repr__(self) -> str:
        return "<undefined>"


_UNDEFINED: Final[_Undefined] = _Undefined()

_SCHEMA_GROUP_PROPS: Final[tuple[str, ...]] = ("properties", "patternProperties", "definitions", "dependencies")
_SCHEMA_ARRAYS: Final[tuple[str, ...]] = ("anyOf", "oneOf")
_SCHEMA_PROPS: Final[tuple[str, ...]] = (
    "additionalProperties",
    "additionalItems",
    "contains",
    "propertyNames",
    "not",
    "items",
)
_PROPERTIES_KEYWORDS: Final[tuple[str, ...]] = ("properties", "patternProperties", "additionalProperties")
_ITEMS_KEYWORDS: Final[tuple[str, ...]] = ("items", "additionalItems")
_FIRST_VALUE_KEYWORDS: Final[frozenset[str]] = frozenset({"$id", "$ref", "$schema", "default", "description", "title"})
_MINIMUM_VALUE_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"exclusiveMaximum", "maximum", "maxItems", "maxLength", "maxProperties"}
)
_MAXIMUM_VALUE_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"exclusiveMinimum", "minimum", "minItems", "minLength", "minProperties"}
)
_SCHEMA_RESOLVED_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"additionalProperties", "additionalItems", "contains", "propertyNames"}
)


def flatten_openapi(
    definition: Mapping[str, object], *, deduplicate: bool = False, custom_type_extension: str | None = None
) -> dict[str, object]:
    """
    Return a flattened copy of the OpenAPI definition (see the module documentation).

    Args:
        definition: The OpenAPI definition.
        deduplicate: Replace object schemas equal in structure by references to single components afterwards, so one
            model is generated for them (see `api_client_generator.openapi_deduplication`).
        custom_type_extension: With `deduplicate` - vendor extension of custom types (`CustomTypes.extension`), schemas
            having it are not models.
    """
    document = copy.deepcopy(dict(definition))
    dereferenced = _Dereferencer(document).crawl(document)
    flattened = _flatten_schema(dereferenced)
    if not isinstance(flattened, dict):
        raise OpenApiFlatteningError("The flattened definition is not an object.")
    if deduplicate:
        return deduplicate_models(flattened, definition, custom_type_extension=custom_type_extension)
    return flattened


def flatten_openapi_file(
    openapi_file: Path, output_file: Path, *, deduplicate: bool = False, custom_type_extension: str | None = None
) -> None:
    """Write the flattened definition of `openapi_file` to `output_file` (see `flatten_openapi`)."""
    definition = json.loads(openapi_file.read_text(encoding="utf-8"))
    if not isinstance(definition, dict):
        raise OpenApiFlatteningError(f"{openapi_file}: the definition is not an object.")
    flattened = flatten_openapi(definition, deduplicate=deduplicate, custom_type_extension=custom_type_extension)
    output_file.write_text(json.dumps(flattened, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------------------------------------- JSON helpers


def _is_ref(value: object) -> TypeIs[dict[str, object]]:
    return isinstance(value, dict) and isinstance(value.get("$ref"), str) and bool(value["$ref"])


def _is_truthy(value: object) -> bool:
    """Truthiness of a JSON value as in JavaScript - empty objects and arrays are truthy."""
    if isinstance(value, dict | list):
        return True
    return value is not _UNDEFINED and bool(value)


def _keys(value: object) -> list[str | int]:
    if isinstance(value, dict):
        return list(value)
    if isinstance(value, list):
        return list(range(len(value)))
    return []


def _object_keys(value: object) -> list[str]:
    return list(value) if isinstance(value, dict) else []


def _get(value: object, key: str | int) -> object:
    if isinstance(value, dict) and isinstance(key, str):
        return value.get(key, _UNDEFINED)
    if isinstance(value, list) and isinstance(key, int):
        return value[key] if key < len(value) else _UNDEFINED
    return _UNDEFINED


def _is_equal(first: object, second: object) -> bool:
    """Deep equality of JSON values (key order does not matter, booleans are not numbers)."""
    if isinstance(first, bool) or isinstance(second, bool):
        return first is second
    if isinstance(first, dict) and isinstance(second, dict):
        return first.keys() == second.keys() and all(_is_equal(first[key], second[key]) for key in first)
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(_is_equal(a, b) for a, b in zip(first, second, strict=True))
    if isinstance(first, int | float) and isinstance(second, int | float):
        return first == second
    if type(first) is not type(second):
        return False
    return first == second


def _uniq(values: list[object]) -> list[object]:
    result: list[object] = []
    for value in values:
        if not any(value is seen or (_is_scalar(value) and _is_equal(value, seen)) for seen in result):
            result.append(value)
    return result


def _uniq_with(values: list[object], equal: Callable[[object, object], bool]) -> list[object]:
    result: list[object] = []
    for value in values:
        if not any(equal(seen, value) for seen in result):
            result.append(value)
    return result


def _is_scalar(value: object) -> bool:
    return not isinstance(value, dict | list)


def _flatten_deep(values: object) -> list[object]:
    if not isinstance(values, list):
        return [values]
    return [item for value in values for item in _flatten_deep(value)]


def _sorted_strings(values: list[object]) -> list[object]:
    """`sortBy(uniq(values))` of strings (required properties, enum values)."""
    unique = _uniq(_flatten_deep(values))
    return sorted(unique, key=_sort_key)


def _sort_key(value: object) -> tuple[int, str | float]:
    if isinstance(value, str):
        return (1, value)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return (0, value)
    raise OpenApiFlatteningError(f"Cannot sort {value!r} while merging allOf.")


def _all_unique_keys(values: list[object]) -> list[str | int]:
    keys: list[str | int] = []
    for value in values:
        for key in _keys(value):
            if key not in keys:
                keys.append(key)
    return keys


def _delete_empty_schemas(group: dict[str, object]) -> dict[str, object]:
    """Remove members which are empty schemas (also missing ones) - `deleteUndefinedProps`."""
    return {key: value for key, value in group.items() if _keys(value) or isinstance(value, bool)}


# ------------------------------------------------------------------------------------------------- $ref resolution


class _Dereferencer:
    """In-place dereferencing of `$ref`s, crawling the document in the order of json-schema-ref-parser."""

    def __init__(self, root: dict[str, object]) -> None:
        self._root = root
        self._processed: dict[int, object] = {}  # keeps processed objects alive, so their ids are not reused
        self._parents: dict[int, object] = {}
        self._cache: dict[str, object] = {}

    def crawl(self, value: object) -> object:
        if not isinstance(value, dict | list) or id(value) in self._processed:
            return value
        self._parents[id(value)] = value
        self._processed[id(value)] = value
        result: object = value
        if _is_ref(value):
            result = self._dereference_ref(value)
        else:
            for key in _keys(value):
                member = _get(value, key)
                if _is_ref(member):
                    dereferenced = self._dereference_ref(member)
                elif id(member) in self._parents:
                    raise OpenApiFlatteningError("Circular references cannot be flattened.")
                else:
                    dereferenced = self.crawl(member)
                if dereferenced is not member:
                    set_member(value, key, dereferenced)
        del self._parents[id(value)]
        return result

    def _dereference_ref(self, ref: dict[str, object]) -> object:
        target = ref["$ref"]
        assert isinstance(target, str)
        if target in self._cache:
            cached = self._cache[target]
            if len(ref) > 1 and isinstance(cached, dict):
                # only keys missing in the referenced value are added (the referenced value wins)
                extra = {key: value for key, value in ref.items() if key != "$ref" and key not in cached}
                return {**cached, **extra}
            return cached

        resolved = self._resolve(target)
        if id(resolved) in self._parents:
            raise OpenApiFlatteningError(f"Circular reference `{target}` cannot be flattened.")
        dereferenced = self.crawl(_merge_extended_ref(ref, resolved))
        if len(ref) == 1:
            self._cache[target] = dereferenced
        return dereferenced

    def _resolve(self, target: str, visited: frozenset[str] = frozenset()) -> object:
        if not target.startswith("#"):
            raise OpenApiFlatteningError(f"Reference `{target}` outside the definition cannot be flattened.")
        if target in visited:
            raise OpenApiFlatteningError(f"Circular reference `{target}` cannot be flattened.")
        value: object = self._root
        for token in _pointer_tokens(target):
            if _is_ref(value):
                raise OpenApiFlatteningError(f"Reference `{target}` passing through a `$ref` cannot be flattened.")
            member = _get(value, int(token) if isinstance(value, list) else token)
            if member is _UNDEFINED:
                raise OpenApiFlatteningError(f"Reference `{target}` points to nothing.")
            value = member
        if _is_ref(value):  # an alias - another `$ref`
            alias_target = value["$ref"]
            assert isinstance(alias_target, str)
            return _merge_extended_ref(value, self._resolve(alias_target, visited | {target}))
        return value


def _pointer_tokens(target: str) -> list[str]:
    pointer = target.removeprefix("#")
    if not pointer:
        return []
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer.removeprefix("/").split("/")]


def _merge_extended_ref(ref: dict[str, object], resolved: object) -> object:
    """Resolved value of a `$ref` - merged with the keys given next to it (they win), if there are any."""
    if len(ref) == 1 or not isinstance(resolved, dict):
        return resolved
    merged = {key: value for key, value in ref.items() if key != "$ref"}
    for key, value in resolved.items():
        merged.setdefault(key, value)
    return merged


# ------------------------------------------------------------------------------------------------- flattening


def _flatten_schema(schema: object) -> object:
    if isinstance(schema, list):
        for index, member in enumerate(schema):
            schema[index] = _flatten_schema(member)
        return schema
    if not isinstance(schema, dict):
        return schema

    if _is_truthy(schema.get("allOf")):
        merged = _AllOfMerger().merge(schema)
        if not isinstance(merged, dict):
            return merged
        schema = merged

    any_of = schema.get("anyOf")
    if _is_truthy(any_of):
        if not isinstance(any_of, list):
            raise OpenApiFlatteningError(f"anyOf is not an array: {any_of!r}")
        null_index = next((index for index, member in enumerate(any_of) if _is_null_schema(member)), -1)
        non_null = [member for index, member in enumerate(any_of) if index != null_index]
        if null_index != -1 and len(non_null) == 1:
            schema["anyOf"] = [{"type": "null"}, _flatten_schema(non_null[0])]

    for key in list(schema):
        schema[key] = _flatten_schema(schema[key])
    return schema


def _is_null_schema(schema: object) -> bool:
    if not isinstance(schema, dict):
        return False
    type_ = schema.get("type")
    return type_ == "null" or (isinstance(type_, list) and "null" in type_)


class _AllOfMerger:
    """Merging of `allOf` as json-schema-merge-allof merges it (`deep`, additional properties respected)."""

    def merge(self, root: dict[str, object]) -> object:
        return self._merge_schemas(_flatten_deep(_get_all_of(root)))

    def _merge_schemas(self, schemas: list[object], base: dict[str, object] | None = None) -> object:
        schemas = copy.deepcopy([schema for schema in schemas if schema is not _UNDEFINED])
        merged: dict[str, object] = base if base is not None else {}
        if not schemas:
            return _UNDEFINED
        if any(schema is False for schema in schemas):
            return False
        if all(schema is True for schema in schemas):
            return True

        objects: list[object] = [schema for schema in schemas if isinstance(schema, dict)]
        all_keys = _all_unique_keys(objects)
        if "allOf" in all_keys:
            return self.merge({"allOf": objects})

        properties_keys = [key for key in all_keys if key in _PROPERTIES_KEYWORDS]
        items_keys = [key for key in all_keys if key in _ITEMS_KEYWORDS]
        for key in all_keys:
            if key in properties_keys or key in items_keys:
                continue
            assert isinstance(key, str)
            values = [_get(schema, key) for schema in objects]
            compacted = _uniq_with([value for value in values if value is not _UNDEFINED], _is_equal)
            if len(compacted) == 1 and key in _SCHEMA_ARRAYS:
                members = compacted[0]
                if not isinstance(members, list):
                    raise OpenApiFlatteningError(f"{key} is not an array: {members!r}")
                merged[key] = [
                    self._merge_schemas([member], member if isinstance(member, dict) else None) for member in members
                ]
            elif len(compacted) == 1 and key not in _SCHEMA_GROUP_PROPS and key not in _SCHEMA_PROPS:
                merged[key] = compacted[0]
            else:
                resolved = self._resolve_keyword(key, compacted)
                if resolved is _UNDEFINED:
                    raise OpenApiFlatteningError(f"Values of `{key}` in allOf are incompatible: {compacted!r}")
                merged[key] = resolved

        result = dict(merged)
        if properties_keys:
            result = {**result, **self._resolve_properties(_extract_keywords(objects, properties_keys))}
        if items_keys:
            result = {**result, **self._resolve_items(_extract_keywords(objects, items_keys))}
        return result

    def _resolve_keyword(self, key: str, compacted: list[object]) -> object:
        if key == "type":
            return compacted[-1]  # e.g. an object overridden by an array (extensions of legacy transactions)
        if key in _FIRST_VALUE_KEYWORDS:
            return compacted[0]
        if key == "required":
            return _sorted_strings(compacted)
        if key == "examples":
            return _uniq_with(_flatten_deep(compacted), _is_equal)
        if key in _MINIMUM_VALUE_KEYWORDS:
            return min(_numbers(key, compacted))
        if key in _MAXIMUM_VALUE_KEYWORDS:
            return max(_numbers(key, compacted))
        if key == "uniqueItems":
            return any(value is True for value in compacted)
        if key == "enum":
            common = [
                value
                for value in _as_list(key, compacted[0])
                if all(any(_is_equal(value, other) for other in _as_list(key, values)) for values in compacted[1:])
            ]
            return _sorted_strings(common) if common else _UNDEFINED
        if key == "pattern":
            return "".join(f"(?={pattern})" for pattern in compacted)
        if key == "not":
            return {"anyOf": compacted}
        if key in _SCHEMA_RESOLVED_KEYWORDS:
            return self._merge_schemas(compacted)
        raise OpenApiFlatteningError(f"Merging different values of `{key}` in allOf is not supported: {compacted!r}")

    def _resolve_properties(self, values: list[dict[str, object]]) -> dict[str, object]:
        for sub_schema in values:
            own_keys = _object_keys(sub_schema.get("properties"))
            own_patterns = [re.compile(pattern) for pattern in _object_keys(sub_schema.get("patternProperties"))]
            for other in values:
                if other is sub_schema:
                    continue
                other_properties = other.get("properties")
                if not isinstance(other_properties, dict):
                    continue
                for key in list(other_properties):
                    if key in own_keys or any(pattern.search(key) for pattern in own_patterns):
                        continue
                    other_properties[key] = self._merge_schemas(
                        [other_properties[key], sub_schema.get("additionalProperties", _UNDEFINED)]
                    )

        for sub_schema in values:
            if sub_schema.get("additionalProperties") is False:
                own_pattern_keys = _object_keys(sub_schema.get("patternProperties"))
                for other in values:
                    other_patterns = other.get("patternProperties")
                    if other is not sub_schema and isinstance(other_patterns, dict):
                        for key in [key for key in other_patterns if key not in own_pattern_keys]:
                            del other_patterns[key]

        result: dict[str, object] = {
            "additionalProperties": self._merge_schemas([_get(value, "additionalProperties") for value in values]),
            "patternProperties": self._merge_schema_group([_get(value, "patternProperties") for value in values]),
            "properties": self._merge_schema_group([_get(value, "properties") for value in values]),
        }
        properties = result["properties"]
        if result["additionalProperties"] is False and isinstance(properties, dict):
            result["properties"] = {key: value for key, value in properties.items() if value is not False}
        return _delete_empty_schemas(result)

    def _resolve_items(self, values: list[dict[str, object]]) -> dict[str, object]:
        if any("additionalItems" in value for value in values):
            raise OpenApiFlatteningError("Merging `additionalItems` in allOf is not supported.")
        items = [_get(value, "items") for value in values]
        defined_items = [item for item in items if item is not _UNDEFINED]
        result: dict[str, object] = {}
        if all(isinstance(item, dict | bool) for item in defined_items):
            result["items"] = self._merge_schemas(items)
        else:
            raise OpenApiFlatteningError("Merging arrays of `items` in allOf is not supported.")
        return _delete_empty_schemas(result)

    def _merge_schema_group(self, group: list[object]) -> dict[str, object]:
        merged: dict[str, object] = {}
        for key in _all_unique_keys(group):
            assert isinstance(key, str)
            schemas = [_get(member, key) for member in group]
            compacted = _uniq_with([schema for schema in schemas if schema is not _UNDEFINED], _is_equal)
            merged[key] = self._merge_schemas(compacted)
        return merged


def _get_all_of(schema: object) -> list[object]:
    if not isinstance(schema, dict):
        return [schema]
    members = schema.get("allOf", [])
    copy_ = {key: value for key, value in schema.items() if key != "allOf"}
    return [copy_, *[_get_all_of(member) for member in (members if isinstance(members, list) else [])]]


def _extract_keywords(schemas: list[object], keywords: list[str]) -> list[dict[str, object]]:
    extracted = [
        {str(key): _get(schema, key) for key in keywords if _get(schema, key) is not _UNDEFINED} for schema in schemas
    ]
    unique = _uniq_with(list(extracted), _is_equal)
    return [value for value in unique if isinstance(value, dict)]


def _numbers(key: str, values: list[object]) -> list[int | float]:
    numbers = [value for value in values if isinstance(value, int | float) and not isinstance(value, bool)]
    if len(numbers) != len(values):
        raise OpenApiFlatteningError(f"Values of `{key}` in allOf are not numbers: {values!r}")
    return numbers


def _as_list(key: str, value: object) -> list[object]:
    if not isinstance(value, list):
        raise OpenApiFlatteningError(f"`{key}` is not an array: {value!r}")
    return value
