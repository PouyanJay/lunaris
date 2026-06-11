"""The store-boundary guard — the decorator behind the ``PersistenceError`` contract.

Load-bearing: the API's best-effort history writes catch exactly ``PersistenceError``, so the
guard's translation (driver failure → contract error) and its two passthroughs (the stores'
``FileNotFoundError`` not-found signal; an already-translated ``PersistenceError``) must hold on
both the sync and async paths.
"""

import pytest
from lunaris_runtime.persistence import PersistenceError
from lunaris_runtime.persistence.guard import guard


@guard("sync op")
def _sync_op(outcome: BaseException | str) -> str:
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


@guard("async op")
async def _async_op(outcome: BaseException | str) -> str:
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


def test_sync_success_passes_the_return_value_through() -> None:
    assert _sync_op("row") == "row"


async def test_async_success_passes_the_return_value_through() -> None:
    assert await _async_op("row") == "row"


def test_sync_driver_failure_is_translated_with_the_cause_chained() -> None:
    # Act / Assert — a driver error becomes the contract error, original chained for diagnosis.
    with pytest.raises(PersistenceError, match="sync op failed") as excinfo:
        _sync_op(ConnectionError("postgrest unreachable"))
    assert isinstance(excinfo.value.__cause__, ConnectionError)


async def test_async_driver_failure_is_translated_with_the_cause_chained() -> None:
    with pytest.raises(PersistenceError, match="async op failed") as excinfo:
        await _async_op(TimeoutError("pooler timed out"))
    assert isinstance(excinfo.value.__cause__, TimeoutError)


def test_not_found_contract_signal_passes_through_untranslated() -> None:
    # The course stores raise FileNotFoundError as their domain not-found — it is a contract
    # value, not a backend failure, and callers (service.get) catch it specifically.
    with pytest.raises(FileNotFoundError):
        _sync_op(FileNotFoundError("course-1"))


async def test_already_translated_error_is_not_double_wrapped() -> None:
    original = PersistenceError("inner layer already translated")
    with pytest.raises(PersistenceError) as excinfo:
        await _async_op(original)
    assert excinfo.value is original
