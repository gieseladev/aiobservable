"""aiobservable is a small and lightweight implementation the observable pattern.

What sets it apart is that it doesn't represents events as a combination of
a name and arguments, but instead operates on classes.

Instead of using names like "on_connect" the library encourages the use of a
"ConnectEvent" class which has the arguments as its attributes. Instead of
listening to a meaningless name observers instead pass the event type
(the class) to the `ObservableABC.on` method.
When emitting an event we then use instances of the event type.

This is especially typing friendly and puts an end to the problem of
"what arguments and keyword arguments does my listener function have to expect"
because the only argument the listener receives is the event instance.
Need to know what event you're dealing with? Just call type(event) to get the
class and you're there.


Example:
    Simple example using dataclasses::

    import asyncio
    import dataclasses

    import aiobservable


    @dataclasses.dataclass()
    class ConnectEvent:
        user_id: int
        user_name: str

    async def main():
        observable = aiobservable.Observable()

        def on_connect(event: ConnectEvent) -> None:
            print(f"{event.user_name} connected!")

        observable.on(ConnectEvent, on_connect)

        event = ConnectEvent(1, "Simon")

        # emit returns a future which resolves to None when all observers
        # are done handling the event
        await observable.emit(event)

    asyncio.run(main())
"""

from .abstract import *
from .observable import *
from .types import *

__author__ = "Giesela Inc."
__version__ = "0.2.0"
