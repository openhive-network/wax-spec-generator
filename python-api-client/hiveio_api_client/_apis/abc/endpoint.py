from __future__ import annotations

from functools import update_wrapper
from typing import TYPE_CHECKING, Concatenate, Generic, ParamSpec, Protocol, TypeVar, cast, overload

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence
    from typing import Self

ApiT = TypeVar("ApiT")
P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)
CallbacksT = TypeVar("CallbacksT")
FilterT = TypeVar("FilterT")
FilterT_co = TypeVar("FilterT_co", covariant=True)


class ClassFilterInterface(Generic[FilterT_co]):
    """
    Base of result models which can be validated selectively - `FilterT_co` is the schema filter of the model.

    The filter is a `TypedDict` seen only by type checkers (given as a string, e.g.
    `ClassFilterInterface["_filters.BlockFilter"]`): a key per field of the model, its value is `True` (validate the
    field) or the filter of the model of the field (validate only the given fields of it). `set_validation_mask` of
    endpoints returning the model takes it.
    """

    __slots__ = ()


class _SupportsValidationMask(Protocol):
    def _set_validation_mask(self, endpoint_name: str, mask: Mapping[str, object] | None) -> None: ...

    def _validation_mask(self, endpoint_name: str) -> Mapping[str, object] | None: ...

    def _compiled_validation_mask(self, endpoint_name: str) -> object | None: ...


class Endpoint(Generic[ApiT, P, R_co, CallbacksT]):
    """
    Endpoint of an API class (created by the endpoint decorators of APIs).

    Accessed through an instance of the API, it is bound to it - `api.endpoint(...)` calls the endpoint,
    `api.endpoint.callbacks` are callbacks of the endpoint in this instance of the API.
    """

    def __init__(
        self, function: Callable[Concatenate[ApiT, P], R_co], callbacks_of: Callable[[ApiT, str], CallbacksT]
    ) -> None:
        """
        Args:
            function: Implementation of the endpoint, called with the instance of the API.
            callbacks_of: Returns callbacks of the endpoint (given by name) in the given instance of the API.
        """
        update_wrapper(self, function)
        self.__function = function
        self.__callbacks_of = callbacks_of
        self.__name = function.__name__

    def __call__(self, api: ApiT, /, *args: P.args, **kwargs: P.kwargs) -> R_co:
        """Call the endpoint of the given instance of the API (as `ApiClass.endpoint(api, ...)`)."""
        return self.__function(api, *args, **kwargs)

    @overload
    def __get__(self, api: None, owner: type[object] | None = None) -> Self: ...

    @overload
    def __get__(self, api: ApiT, owner: type[object] | None = None) -> BoundEndpoint[ApiT, P, R_co, CallbacksT]: ...

    def __get__(
        self, api: ApiT | None, owner: type[object] | None = None
    ) -> Self | BoundEndpoint[ApiT, P, R_co, CallbacksT]:
        if api is None:
            return self
        bound = BoundEndpoint(api, self, self.__function, self.__callbacks_of)
        # kept in the instance - the next accesses get it without the descriptor (as `functools.cached_property`)
        vars(api)[self.__name] = bound
        return bound


class BoundEndpoint(Generic[ApiT, P, R_co, CallbacksT]):
    """Endpoint bound to an instance of its API - callable as the method, with callbacks of the endpoint."""

    def __init__(
        self,
        api: ApiT,
        endpoint: Endpoint[ApiT, P, R_co, CallbacksT],
        function: Callable[Concatenate[ApiT, P], R_co],
        callbacks_of: Callable[[ApiT, str], CallbacksT],
    ) -> None:
        update_wrapper(self, function, updated=())  # name, documentation, ... - not attributes of the function
        self.__self__ = api
        self.__func__ = endpoint
        self.__function = function
        self.__callbacks_of = callbacks_of
        self.__name = function.__name__

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R_co:
        return self.__function(self.__self__, *args, **kwargs)

    @property
    def callbacks(self) -> CallbacksT:
        """Callbacks of requests of this endpoint - called after callbacks of the API collection and of the API."""
        return self.__callbacks_of(self.__self__, self.__name)

    @overload
    def set_validation_mask(
        self: BoundEndpoint[ApiT, P, Awaitable[ClassFilterInterface[FilterT]], CallbacksT], mask: FilterT | None
    ) -> None: ...

    @overload
    def set_validation_mask(
        self: BoundEndpoint[ApiT, P, Awaitable[Sequence[ClassFilterInterface[FilterT]]], CallbacksT],
        mask: FilterT | None,
    ) -> None: ...

    @overload
    def set_validation_mask(
        self: BoundEndpoint[ApiT, P, ClassFilterInterface[FilterT], CallbacksT], mask: FilterT | None
    ) -> None: ...

    @overload
    def set_validation_mask(
        self: BoundEndpoint[ApiT, P, Sequence[ClassFilterInterface[FilterT]], CallbacksT], mask: FilterT | None
    ) -> None: ...

    def set_validation_mask(self, mask: object) -> None:
        """
        Limit validation of results of this endpoint (in this instance of the API) to the given fields.

        The mask does not turn validation on - it is used by validation of responses when it is enabled (validators
        get it by `compiled_validation_mask_of`). Fields not given in the mask are not validated.

        The mask is compiled at once by the API (e.g. to a reduced validation model) - a wrong mask raises here, and
        requests use the compiled mask. Available for endpoints whose result models have a schema filter
        (`ClassFilterInterface`).

        Args:
            mask: The fields to validate - `{"field": True}` validates the whole field, `{"field": {...}}` the given
                fields of its model (of items of a list); `None` removes the mask (all fields are validated). For an
                endpoint returning a list of models - the fields of each of them.

        Raises:
            ValueError: When the API finds the mask wrong (e.g. it names a field the model does not have).
            TypeError: When the API finds the mask wrong (e.g. a value of the mask is not `True` / a dict).
        """
        api = cast("_SupportsValidationMask", self.__self__)
        api._set_validation_mask(self.__name, cast("Mapping[str, object] | None", mask))

    @property
    def validation_mask(self) -> Mapping[str, object] | None:
        """The validation mask of this endpoint (`set_validation_mask`), `None` when it has no mask."""
        return cast("_SupportsValidationMask", self.__self__)._validation_mask(self.__name)

    @property
    def compiled_validation_mask(self) -> object | None:
        """The validation mask of this endpoint compiled by its API - for validators, `None` when it has no mask."""
        return cast("_SupportsValidationMask", self.__self__)._compiled_validation_mask(self.__name)
