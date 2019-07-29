import asyncio
import dataclasses

import pytest

import aiobservable

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass()
class Event:
    a: str


async def test_first():
    o = aiobservable.Observable()
    sub = o.subscribe(Event)
    await o.emit(Event("test"))

    assert await sub.first() == Event("test")
    assert sub.closed


async def test_await():
    o = aiobservable.Observable()
    sub = o.subscribe(Event)
    await o.emit(Event("test"))

    assert await sub == Event("test")
    assert sub.closed


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
    # this will stop the listener loop
    sub.unsubscribe()

    assert await fut == [Event("a"), Event("b"), Event("c")]


async def test_multiple():
    @dataclasses.dataclass()
    class Event2:
        a: int

    o = aiobservable.Observable()
    sub = o.subscribe((Event, Event2))

    await o.emit(Event("test"))
    assert await sub.next() == Event("test")

    await o.emit(Event2(5))
    assert await sub.next() == Event2(5)
