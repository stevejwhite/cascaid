import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from psychiatry_api.cancellation import until_disconnect


def request_for(event):
    async def receive():
        await event.wait()
        return {"type": "http.disconnect"}

    return Request({"type": "http"}, receive)


async def test_disconnect_cancels_work_and_releases_generation_slot():
    disconnected = asyncio.Event()
    started = asyncio.Event()
    stopped = asyncio.Event()
    slot = asyncio.Lock()

    async def work():
        async with slot:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    task = asyncio.create_task(until_disconnect(request_for(disconnected), work()))
    await started.wait()
    disconnected.set()
    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(task, 1)
    assert error.value.status_code == 499
    assert stopped.is_set()
    assert not slot.locked()


async def test_completion_returns_result_without_leaving_disconnect_watcher():
    async def work():
        return "verified"

    before = asyncio.all_tasks()
    assert await until_disconnect(request_for(asyncio.Event()), work()) == "verified"
    assert asyncio.all_tasks() == before


async def test_deadline_cancels_queued_work_without_running_it():
    slot = asyncio.Lock()
    called = False

    async def work():
        nonlocal called
        async with slot:
            called = True

    async with slot:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.02):
                await until_disconnect(request_for(asyncio.Event()), work())
    await asyncio.sleep(0)
    assert not called
