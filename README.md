# AIObservable

[![PyPI](https://img.shields.io/pypi/v/aiobservable)][pypi-link]


A simple and efficient implementation of the observable pattern.


## Introduction

What sets it apart is that it doesn't represents events as a combination
of a name and arguments, but instead operates on classes.

Instead of using names like "on_connect" the library encourages the use
of a "ConnectEvent" class which has the arguments as its attributes.
Instead of listening to a meaningless name observers instead use the
event type (the class). When emitting an event we then use instances of
the event class.

Apart from other benefits this especially helps with typings and
eliminates the issue of having to know the function signature for each
event, as the only argument is the event instance.

Using the built-in
[dataclasses](https://docs.python.org/3/library/dataclasses.html) makes
it easy to avoid writing boiler-plate code for each event.


## Example

```python
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
```


## Installing

You can install the library from [PyPI][pypi-link]:

```shell
pip install aiobservable
```


[pypi-link]: https://pypi.org/project/aiobservable/ "AIObservable on PyPI"