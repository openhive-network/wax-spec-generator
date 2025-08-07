from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any, TypedDict, Callable, Mapping, Sequence
    from collections import defaultdict

    from datamodel_code_generator import (
        DatetimeClassType,
        Formatter,
        GraphQLScope,
        LiteralType,
        OpenAPIScope,
        PythonVersion,
        StrictTypes,
        UnionMode,
    )


class DataModelCodeGeneratorOptions(TypedDict, total=False):
    """Type hints for datamodel_code_generator.generate function options."""

    input_filename: str | None
    target_python_version: PythonVersion
    base_class: str
    additional_imports: list[str] | None
    custom_template_dir: Path | None
    extra_template_data: defaultdict[str, dict[str, Any]] | None
    validation: bool
    field_constraints: bool
    snake_case_field: bool
    strip_default_none: bool
    aliases: Mapping[str, str] | None
    disable_timestamp: bool
    enable_version_header: bool
    allow_population_by_field_name: bool
    allow_extra_fields: bool
    extra_fields: str | None
    apply_default_values_for_required_fields: bool
    force_optional_for_required_fields: bool
    class_name: str | None
    use_schema_description: bool
    use_default_kwarg: bool
    reuse_model: bool
    encoding: str
    enum_field_as_literal: LiteralType | None
    use_one_literal_as_default: bool
    set_default_enum_member: bool
    use_subclass_enum: bool
    strict_nullable: bool
    use_generic_container_types: bool
    enable_faux_immutability: bool
    disable_appending_item_suffix: bool
    strict_types: Sequence[StrictTypes] | None
    empty_enum_field_name: str | None
    custom_class_name_generator: Callable[[str], str] | None
    field_extra_keys: set[str] | None
    field_include_all_keys: bool
    field_extra_keys_without_x_prefix: set[str] | None
    openapi_scopes: list[OpenAPIScope] | None
    include_path_parameters: bool
    graphql_scopes: list[GraphQLScope] | None
    wrap_string_literal: bool | None
    use_title_as_name: bool
    use_operation_id_as_name: bool
    use_unique_items_as_set: bool
    http_headers: Sequence[tuple[str, str]] | None
    http_ignore_tls: bool
    use_annotated: bool
    use_non_positive_negative_number_constrained_types: bool
    original_field_name_delimiter: str | None
    use_double_quotes: bool
    use_union_operator: bool
    collapse_root_models: bool
    special_field_name_prefix: str | None
    remove_special_field_name_prefix: bool
    capitalise_enum_members: bool
    keep_model_order: bool
    custom_file_header: str | None
    custom_file_header_path: Path | None
    custom_formatters: list[str] | None
    custom_formatters_kwargs: dict[str, Any] | None
    use_pendulum: bool
    http_query_parameters: Sequence[tuple[str, str]] | None
    treat_dot_as_module: bool
    union_mode: UnionMode | None
    output_datetime_class: DatetimeClassType | None
    keyword_only: bool
    frozen_dataclasses: bool
    no_alias: bool
    formatters: list[Formatter]
    parent_scoped_naming: bool
