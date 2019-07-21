import asyncio
import dataclasses

import pytest

import aiobservable


@dataclasses.dataclass()
class Event:
    a: str


@pytest.mark.asyncio
async def test_first():
    o = aiobservable.Observable()
    sub = o.subscribe(Event)
    await o.emit(Event("test"))

    assert await sub.first() == Event("test")
    assert sub.closed


@pytest.mark.asyncio
async def test_aiter():
    o = aiobservable.Observable([Event])
    sub = o.subscribe()

    async def listener():
        results = []

        async for event in sub:
            results.append(event)

        return results

    fut = asyncio.ensure_future(listener())

    _ = o.emit(Event("a"))

    # gotta sleppp
    await asyncio.sleep(0)
    _ = o.emit(Event("b"))

    await asyncio.sleep(0)
    _ = o.emit(Event("c"))

    await asyncio.sleep(0)
    sub.unsubscribe()

    assert await fut == [Event("a"), Event("b"), Event("c")]
