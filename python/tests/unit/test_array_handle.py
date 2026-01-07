"""Tests for array_handle module.

These tests verify the handling of generic type annotations for list types.
They would fail without the fix for array type annotation handling because the
old implementation used regex-based string manipulation which couldn't properly
handle complex generic types like list[SomeType | None] or nested generics.
"""

from __future__ import annotations

from typing import Union

import pytest
from msgspec import Struct

from api_client_generator._private.common.array_handle import (
    _format_annotation,
    get_array_ready_for_annotation,
    is_param_array,
)


class CustomType(Struct):
    value: str


class AnotherType(Struct):
    data: int


# ============================================================================
# Tests for is_param_array
# ============================================================================


class TestIsParamArray:
    """Tests for is_param_array function."""

    def test_simple_list_type(self) -> None:
        """Test detection of simple list type."""
        assert is_param_array(list[str]) is True

    def test_list_with_custom_type(self) -> None:
        """Test detection of list with custom type."""
        assert is_param_array(list[CustomType]) is True

    def test_list_with_union_type(self) -> None:
        """Test detection of list with union type - would fail without fix."""
        assert is_param_array(list[CustomType | None]) is True

    def test_list_with_typing_union(self) -> None:
        """Test detection of list with typing.Union - would fail without fix."""
        assert is_param_array(list[Union[CustomType, None]]) is True

    def test_list_with_multiple_union_types(self) -> None:
        """Test detection of list with multiple union types - would fail without fix."""
        assert is_param_array(list[CustomType | AnotherType | None]) is True

    def test_nested_list(self) -> None:
        """Test detection of nested list - would fail without fix."""
        assert is_param_array(list[list[str]]) is True

    def test_bare_list_class(self) -> None:
        """Test detection of bare list class."""
        assert is_param_array(list) is True

    def test_string_list_annotation(self) -> None:
        """Test detection of string annotation."""
        assert is_param_array("list[str]") is True

    def test_string_bare_list(self) -> None:
        """Test detection of bare list string."""
        assert is_param_array("list") is True

    def test_non_list_type(self) -> None:
        """Test that non-list types return False."""
        assert is_param_array(str) is False
        assert is_param_array(int) is False
        assert is_param_array(CustomType) is False

    def test_dict_type_is_not_array(self) -> None:
        """Test that dict type returns False."""
        assert is_param_array(dict[str, int]) is False

    def test_tuple_type_is_not_array(self) -> None:
        """Test that tuple type returns False."""
        assert is_param_array(tuple[str, int]) is False


# ============================================================================
# Tests for get_array_ready_for_annotation
# ============================================================================


class TestGetArrayReadyForAnnotation:
    """Tests for get_array_ready_for_annotation function."""

    def test_simple_list_str(self) -> None:
        """Test formatting of simple list[str]."""
        result = get_array_ready_for_annotation(list[str])
        assert result == "list[str]"

    def test_simple_list_int(self) -> None:
        """Test formatting of simple list[int]."""
        result = get_array_ready_for_annotation(list[int])
        assert result == "list[int]"

    def test_list_with_custom_type(self) -> None:
        """Test formatting of list with custom type."""
        result = get_array_ready_for_annotation(list[CustomType])
        assert result == "list[CustomType]"

    def test_list_with_union_none(self) -> None:
        """Test formatting of list[SomeType | None] - would fail without fix.

        The old regex-based implementation couldn't properly handle union types
        inside brackets.
        """
        result = get_array_ready_for_annotation(list[CustomType | None])
        assert result == "list[CustomType | None]"

    def test_list_with_typing_union_none(self) -> None:
        """Test formatting of list[Union[SomeType, None]] - would fail without fix."""
        result = get_array_ready_for_annotation(list[Union[CustomType, None]])
        assert result == "list[CustomType | None]"

    def test_list_with_multiple_union_types(self) -> None:
        """Test formatting of list with multiple union types - would fail without fix."""
        result = get_array_ready_for_annotation(list[CustomType | AnotherType | None])
        assert result == "list[CustomType | AnotherType | None]"

    def test_bare_list_class(self) -> None:
        """Test formatting of bare list class."""
        result = get_array_ready_for_annotation(list)
        assert result == "list[str]"

    def test_string_annotation_already_formatted(self) -> None:
        """Test that string annotations pass through."""
        result = get_array_ready_for_annotation("list[MyType]")
        assert result == "list[MyType]"

    def test_string_annotation_needs_wrapping(self) -> None:
        """Test that string types get wrapped in list."""
        result = get_array_ready_for_annotation("MyType")
        assert result == "list[MyType]"


# ============================================================================
# Tests for _format_annotation (internal helper)
# ============================================================================


class TestFormatAnnotation:
    """Tests for _format_annotation internal helper function."""

    def test_simple_type(self) -> None:
        """Test formatting of simple type."""
        result = _format_annotation(str)
        assert result == "str"

    def test_custom_type(self) -> None:
        """Test formatting of custom type."""
        result = _format_annotation(CustomType)
        assert result == "CustomType"

    def test_none_type(self) -> None:
        """Test formatting of None type."""
        result = _format_annotation(type(None))
        assert result == "None"

    def test_union_type(self) -> None:
        """Test formatting of union type - would fail without fix."""
        result = _format_annotation(CustomType | None)
        assert result == "CustomType | None"

    def test_union_multiple_types(self) -> None:
        """Test formatting of union with multiple types - would fail without fix."""
        result = _format_annotation(CustomType | AnotherType | None)
        assert result == "CustomType | AnotherType | None"

    def test_list_type(self) -> None:
        """Test formatting of list type."""
        result = _format_annotation(list[str])
        assert result == "list[str]"

    def test_nested_list(self) -> None:
        """Test formatting of nested list - would fail without fix."""
        result = _format_annotation(list[list[str]])
        assert result == "list[list[str]]"

    def test_list_with_union(self) -> None:
        """Test formatting of list with union - would fail without fix."""
        result = _format_annotation(list[str | None])
        assert result == "list[str | None]"

    def test_dict_type(self) -> None:
        """Test formatting of dict type - would fail without fix."""
        result = _format_annotation(dict[str, int])
        assert result == "dict[str, int]"

    def test_dict_with_complex_value(self) -> None:
        """Test formatting of dict with complex value - would fail without fix."""
        result = _format_annotation(dict[str, CustomType | None])
        assert result == "dict[str, CustomType | None]"

    def test_tuple_type(self) -> None:
        """Test formatting of tuple type - would fail without fix."""
        result = _format_annotation(tuple[str, int])
        assert result == "tuple[str, int]"

    def test_tuple_with_ellipsis(self) -> None:
        """Test formatting of variable length tuple - would fail without fix."""
        result = _format_annotation(tuple[str, ...])
        assert result == "tuple[str, ...]"

    def test_set_type(self) -> None:
        """Test formatting of set type - would fail without fix."""
        result = _format_annotation(set[str])
        assert result == "set[str]"


# ============================================================================
# Edge cases that would have failed with old implementation
# ============================================================================


class TestEdgeCasesFixedByPatch:
    """Test cases that specifically would have failed with the old regex-based implementation."""

    @pytest.mark.parametrize(
        "param_type,expected",
        [
            (list[CustomType | None], "list[CustomType | None]"),
            (list[Union[CustomType, None]], "list[CustomType | None]"),
            (list[str | int | None], "list[str | int | None]"),
            (list[list[CustomType]], "list[list[CustomType]]"),
            (list[dict[str, CustomType]], "list[dict[str, CustomType]]"),
        ],
    )
    def test_complex_generic_types(self, param_type: type, expected: str) -> None:
        """Test that complex generic types are handled correctly.

        The old implementation used regex: re.sub(r"\\[([^\\]]+)\\]", replacer, list_as_str)
        which would fail on nested brackets or complex union syntax.
        """
        result = get_array_ready_for_annotation(param_type)
        assert result == expected

    def test_deeply_nested_generics(self) -> None:
        """Test deeply nested generic types - would fail without fix."""
        param_type = list[dict[str, list[CustomType | None]]]
        result = get_array_ready_for_annotation(param_type)
        assert result == "list[dict[str, list[CustomType | None]]]"
