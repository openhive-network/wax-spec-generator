"""Tests for generic type import handling in create_client_and_imports module.

These tests verify the collection of imports from generic type annotations.
They would fail without the fix for array type annotation handling because the
old implementation used string parsing (extract_module_path, extract_inner_type)
which couldn't properly handle complex generic types like list[SomeType | None].
"""

from __future__ import annotations

from typing import Union

import pytest
from msgspec import Struct

from api_client_generator._private.json_rpc_tools.create_client_and_imports import (
    _collect_generic_type_imports,
    _iter_annotation_leaf_types,
)


# Test types in a hypothetical module structure
class ModuleTypeA(Struct):
    value: str


class ModuleTypeB(Struct):
    data: int


# ============================================================================
# Tests for _iter_annotation_leaf_types
# ============================================================================


class TestIterAnnotationLeafTypes:
    """Tests for _iter_annotation_leaf_types function."""

    def test_simple_type_yields_itself(self) -> None:
        """Test that a simple type yields itself."""
        result = list(_iter_annotation_leaf_types(str))
        assert result == [str]

    def test_custom_type_yields_itself(self) -> None:
        """Test that a custom type yields itself."""
        result = list(_iter_annotation_leaf_types(ModuleTypeA))
        assert result == [ModuleTypeA]

    def test_list_of_simple_type(self) -> None:
        """Test that list[str] yields str."""
        result = list(_iter_annotation_leaf_types(list[str]))
        assert result == [str]

    def test_list_of_custom_type(self) -> None:
        """Test that list[CustomType] yields CustomType."""
        result = list(_iter_annotation_leaf_types(list[ModuleTypeA]))
        assert result == [ModuleTypeA]

    def test_list_with_union_yields_all_types(self) -> None:
        """Test that list[TypeA | TypeB] yields both types - would fail without fix.

        The old implementation used extract_inner_type with regex which couldn't
        handle union types inside brackets.
        """
        result = list(_iter_annotation_leaf_types(list[ModuleTypeA | ModuleTypeB]))
        assert ModuleTypeA in result
        assert ModuleTypeB in result

    def test_list_with_optional_type(self) -> None:
        """Test that list[Type | None] yields Type and NoneType - would fail without fix."""
        result = list(_iter_annotation_leaf_types(list[ModuleTypeA | None]))
        assert ModuleTypeA in result
        assert type(None) in result

    def test_union_type_directly(self) -> None:
        """Test union type yields all its parts - would fail without fix."""
        result = list(_iter_annotation_leaf_types(ModuleTypeA | ModuleTypeB | None))
        assert ModuleTypeA in result
        assert ModuleTypeB in result
        assert type(None) in result

    def test_typing_union(self) -> None:
        """Test typing.Union yields all its parts - would fail without fix."""
        result = list(_iter_annotation_leaf_types(Union[ModuleTypeA, ModuleTypeB]))
        assert ModuleTypeA in result
        assert ModuleTypeB in result

    def test_nested_list(self) -> None:
        """Test nested list yields innermost type - would fail without fix."""
        result = list(_iter_annotation_leaf_types(list[list[ModuleTypeA]]))
        assert result == [ModuleTypeA]

    def test_dict_yields_key_and_value_types(self) -> None:
        """Test dict yields both key and value types - would fail without fix."""
        result = list(_iter_annotation_leaf_types(dict[str, ModuleTypeA]))
        assert str in result
        assert ModuleTypeA in result

    def test_complex_nested_generic(self) -> None:
        """Test complex nested generic yields all leaf types - would fail without fix."""
        # list[dict[str, ModuleTypeA | None]]
        result = list(_iter_annotation_leaf_types(list[dict[str, ModuleTypeA | None]]))
        assert str in result
        assert ModuleTypeA in result
        assert type(None) in result


# ============================================================================
# Tests for _collect_generic_type_imports
# ============================================================================


class TestCollectGenericTypeImports:
    """Tests for _collect_generic_type_imports function."""

    def test_builtin_type_no_imports(self) -> None:
        """Test that builtin types don't generate imports."""
        already_imported: list[str] = []
        result = _collect_generic_type_imports(list[str], already_imported)
        assert result == []

    def test_custom_type_generates_import(self) -> None:
        """Test that custom types generate imports."""
        already_imported: list[str] = []
        result = _collect_generic_type_imports(list[ModuleTypeA], already_imported)
        assert len(result) == 1
        assert "ModuleTypeA" in already_imported

    def test_union_with_custom_type_generates_import(self) -> None:
        """Test that union with custom type generates import - would fail without fix.

        The old implementation used extract_module_path and extract_inner_type
        with regex which couldn't parse union syntax.
        """
        already_imported: list[str] = []
        result = _collect_generic_type_imports(list[ModuleTypeA | None], already_imported)
        assert len(result) == 1
        assert "ModuleTypeA" in already_imported

    def test_union_with_multiple_custom_types(self) -> None:
        """Test that union with multiple custom types generates imports - would fail without fix."""
        already_imported: list[str] = []
        result = _collect_generic_type_imports(list[ModuleTypeA | ModuleTypeB], already_imported)
        assert len(result) == 2
        assert "ModuleTypeA" in already_imported
        assert "ModuleTypeB" in already_imported

    def test_already_imported_not_duplicated(self) -> None:
        """Test that already imported types are not duplicated."""
        already_imported: list[str] = ["ModuleTypeA"]
        result = _collect_generic_type_imports(list[ModuleTypeA], already_imported)
        assert result == []

    def test_complex_generic_collects_all_imports(self) -> None:
        """Test complex generic collects all necessary imports - would fail without fix."""
        already_imported: list[str] = []
        result = _collect_generic_type_imports(list[dict[str, ModuleTypeA | ModuleTypeB | None]], already_imported)
        assert len(result) == 2
        assert "ModuleTypeA" in already_imported
        assert "ModuleTypeB" in already_imported


# ============================================================================
# Regression tests that would have failed with old implementation
# ============================================================================


class TestRegressionOldImplementation:
    """Tests that specifically would have failed with the old string-based implementation.

    The old implementation in create_client_and_imports.py did:
        stringified = str(extracted_params)
        module, class_name = (
            extract_module_path(stringified),
            extract_inner_type(cut_from_bracket_to_dot(stringified)),
        )

    This couldn't handle:
    1. Union types (SomeType | None) - the pipe character broke the regex
    2. Multiple types in union - only one would be extracted
    3. Nested generics - only outermost type would be processed
    """

    @pytest.mark.parametrize(
        "annotation",
        [
            list[ModuleTypeA | None],
            list[Union[ModuleTypeA, None]],
            list[ModuleTypeA | ModuleTypeB],
            list[ModuleTypeA | ModuleTypeB | None],
        ],
    )
    def test_union_types_in_list(self, annotation: type) -> None:
        """Test that union types inside lists are properly iterated."""
        result = list(_iter_annotation_leaf_types(annotation))
        assert ModuleTypeA in result, f"ModuleTypeA not found in leaf types of {annotation}"

    def test_multiple_types_all_collected(self) -> None:
        """Test that all types in a union are collected for import."""
        already_imported: list[str] = []
        annotation = list[ModuleTypeA | ModuleTypeB | None]
        result = _collect_generic_type_imports(annotation, already_imported)

        # Should have imports for both ModuleTypeA and ModuleTypeB
        # (NoneType doesn't need import)
        import_names = [imp.names[0].name for imp in result]
        assert "ModuleTypeA" in import_names, "ModuleTypeA import missing"
        assert "ModuleTypeB" in import_names, "ModuleTypeB import missing"
