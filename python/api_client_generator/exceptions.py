from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection
    from pathlib import Path


class ApiClientGeneratorError(Exception):
    """Base class for all exceptions raised by the ApiClientGenerator."""


class InvalidApiNameError(ApiClientGeneratorError):
    """Exception raised when the API name is invalid."""

    def __init__(self, api_name: str) -> None:
        self.message = f"Invalid API name: {api_name} provided."
        self.api_name = api_name
        super().__init__(self.message)


class InvalidApiDescriptionAmountError(ApiClientGeneratorError):
    """Exception raised when more than one or none API description is passed to a single generator."""

    def __init__(self) -> None:
        self.message = "More than one or none API dscription passed to the single api client generator."
        super().__init__(self.message)


class RunningScriptWithoutAppropriateFlagError(ApiClientGeneratorError):
    def __init__(self) -> None:
        self.message = (
            "Seems like you are trying to run the script without the -m flag. Please run your generation script like this:\n"
            "python -m your_script_name.py"
        )
        super().__init__(self.message)


class EndpointParamsIsNotModelError(ApiClientGeneratorError):
    """Exception raised when the endpoint parameters are not a model (msgspec struct or dataclass)."""

    def __init__(self, endpoint_name: str = "any") -> None:
        self.message = f"Params for {endpoint_name} endpoint must be a msgspec struct or a dataclass"
        self.endpoint_name = endpoint_name
        super().__init__(self.message)


class EndpointParamsWithDefaultFactoryError(ApiClientGeneratorError):
    """Exception raised when a field of endpoint parameters has a default created by a factory (e.g. `[]`)."""

    def __init__(self, params_name: str, field_name: str) -> None:
        self.message = (
            f"{params_name}.{field_name}: defaults created by a factory (e.g. mutable `[]`) cannot be defaults of"
            " arguments of endpoints."
        )
        self.params_name = params_name
        self.field_name = field_name
        super().__init__(self.message)


class ClassPassedByStrWithoutSourceError(ApiClientGeneratorError):
    """Exception raised when a class is passed by string without its source."""

    def __init__(self) -> None:
        self.message = "You've probably passed a class by string and not provided class source."
        super().__init__(self.message)


class UnsupportedHttpMethodError(ApiClientGeneratorError):
    """Exception raised when an unsupported HTTP method is used."""

    def __init__(self, method: str) -> None:
        self.message = f"Unsupported HTTP method: {method}."
        self.method = method
        super().__init__(self.message)


class UnknownCustomTypeError(ApiClientGeneratorError):
    """Exception raised when the OpenAPI definition references a custom type which was not provided."""

    def __init__(self, name: str, available: tuple[str, ...]) -> None:
        self.message = f"Unknown custom type `{name}`. Available: {', '.join(sorted(available))}."
        self.name = name
        super().__init__(self.message)


class UndefinedModelError(ApiClientGeneratorError):
    """Exception raised when generated code refers to models which are not defined."""

    def __init__(self, module: Path, names: Collection[str]) -> None:
        self.message = f"{module}: referenced, but not defined: {', '.join(sorted(names))}."
        self.module = module
        self.names = tuple(sorted(names))
        super().__init__(self.message)


class OpenApiFlatteningError(ApiClientGeneratorError):
    """Exception raised when an OpenAPI definition cannot be flattened (e.g. circular or external references)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)
