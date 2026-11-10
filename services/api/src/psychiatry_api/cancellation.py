"""Propagate client disconnects through queued work and model HTTP streams."""

import asyncio
from collections.abc import Awaitable

from fastapi import HTTPException, Request


async def until_disconnect[T](request: Request, work: Awaitable[T]) -> T:
    stop = asyncio.Event()

    async def disconnected() -> None:
        while not stop.is_set():
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.1)

    task = asyncio.ensure_future(work)
    watcher = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait((task, watcher), return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            return await task
        raise HTTPException(499, "Request cancelled")
    finally:
        # Starlette's disconnect probe uses an AnyIO cancellation scope. The stop
        # event also terminates the watcher if that scope consumes task cancellation.
        stop.set()
        for pending in (task, watcher):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, watcher, return_exceptions=True)
