"""
Chain save resilience — transient Mongo failures must not 500 the admin's save.

Under production load the Mongo pool's waitQueueTimeoutMS exhausts and a save
500s; the admin sees "Internal server error" SOMETIMES (their screenshot) and
not others. The router now retries transient store failures; these tests pin
the retry and its limits.
"""
import pytest

from app.routers.redirect_chain_router import is_transient_db_error, _with_retry


class PoolTimeout(Exception):
    pass


class ServerSelection(Exception):
    pass


class ValidationFail(Exception):
    pass


@pytest.mark.asyncio
async def test_transient_error_is_detected():
    assert is_transient_db_error(PoolTimeout("connection pool is full"))
    assert is_transient_db_error(ServerSelection("timed out after 2000ms"))
    assert is_transient_db_error(ConnectionError("connection closed"))
    # Real validation/business errors are NOT transient.
    assert not is_transient_db_error(ValidationFail("duplicate chain name"))
    assert not is_transient_db_error(ValueError("bad value"))


@pytest.mark.asyncio
async def test_with_retry_retries_transient_then_succeeds():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ServerSelection("timed out")
        return "chain-doc"

    result = await _with_retry(flaky, attempts=3)
    assert result == "chain-doc"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_with_retry_gives_up_after_attempts():
    calls = {"n": 0}

    async def always_flaky():
        calls["n"] += 1
        raise ServerSelection("timed out")

    from fastapi import HTTPException
    try:
        await _with_retry(always_flaky, attempts=3)
        raised = None
    except ServerSelection as e:
        raised = e
    assert raised is not None, "the transient error must surface after retries"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_with_retry_fails_fast_on_non_transient():
    calls = {"n": 0}

    async def broken():
        calls["n"] += 1
        raise ValidationFail("duplicate chain name")

    with pytest.raises(ValidationFail):
        await _with_retry(broken, attempts=3)
    assert calls["n"] == 1, "non-transient errors must NOT be retried"