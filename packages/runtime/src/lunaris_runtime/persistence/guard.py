import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar, cast

from .persistence_error import PersistenceError

P = ParamSpec("P")
T = TypeVar("T")


def guard(operation: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorate a store method so any backend failure surfaces as :class:`PersistenceError`.

    The store implementations talk to drivers (supabase-py / httpx) whose failure types are an
    implementation detail; this translates them into the one error callers are allowed to be
    lenient about. Two exception families pass through untranslated: ``FileNotFoundError`` (the
    stores' domain not-found contract) and ``PersistenceError`` itself (already translated).
    Works on both sync and async methods.
    """

    def decorate(fn: Callable[P, T]) -> Callable[P, T]:
        if inspect.iscoroutinefunction(fn):
            async_fn = cast(Callable[P, Awaitable[object]], fn)

            @wraps(fn)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                try:
                    return await async_fn(*args, **kwargs)
                except (FileNotFoundError, PersistenceError):
                    raise
                except Exception as exc:
                    raise PersistenceError(f"{operation} failed") from exc

            return cast(Callable[P, T], async_wrapper)

        @wraps(fn)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return fn(*args, **kwargs)
            except (FileNotFoundError, PersistenceError):
                raise
            except Exception as exc:
                raise PersistenceError(f"{operation} failed") from exc

        return sync_wrapper

    return decorate
