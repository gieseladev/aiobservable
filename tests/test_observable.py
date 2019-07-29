import asyncio
import dataclasses

import pytest

import aiobservable

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass()
class Event:
    a: str


async def test_observable():
    o = aiobservable.Observable()

    events = []

    def cb_sync(evt):
        events.append(evt)

    async def cb_async(evt):
        events.append(evt)

    o.on(Event, cb_sync)
    o.on(Event, cb_async)

    await o.emit(Event("hello"))
    await o.emit(Event("world"))
    await o.emit(Event("three"))

    assert len(events) == 2 * 3
    assert events[::2] == [
        Event("hello"),
        Event("world"),
        Event("three"),
    ]
    events.clear()

    o.off(Event, cb_async)

    await asyncio.gather(
        o.emit(Event("hello")),
        o.emit(Event("world")),
    )

    assert events == [Event("hello"), Event("world")]


async def test_observable_off():
    o = aiobservable.Observable()

    class Event2:
        ...

    last_event = None
    set_count = 0

    def test(evt):
        nonlocal last_event, set_count
        last_event = evt
        set_count += 1

    o.on(Event, test)
    o.on(Event2, test)

    await o.emit(Event("test"))
    assert last_event == Event("test")
    assert set_count == 1

    e = Event2()
    await o.emit(e)
    assert last_event == e
    assert set_count == 2

    o.off(Event)

    await o.emit(Event("test"))
    assert last_event == e
    assert set_count == 2

    e = Event2()
    await o.emit(e)
    assert last_event == e
    assert set_count == 3

    o.off(Event2, test)

    await o.emit(Event2())
    assert last_event == e
    assert set_count == 3


async def test_observable_once():
    o = aiobservable.Observable()

    once_event = None

    def cb_once(evt):
        nonlocal once_event
        assert once_event is None, "callback called twice"
        once_event = evt

    o.once(Event, cb_once)

    await asyncio.gather(
        o.emit(Event("hello")),
        o.emit(Event("world")),
        o.emit(Event("irrelevant")),
        o.emit(Event("world")),
    )

    assert once_event == Event("hello")
