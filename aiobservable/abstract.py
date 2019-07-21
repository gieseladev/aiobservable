import abc
import logging
from typing import AsyncIterable, Awaitable, Callable, Generic, Type, TypeVar, Union, overload

__all__ = ["CallbackType",
           "ListenerError",
           "ObservableABC",
           "ChildEmitterABC", "EmitterABC",
           "SubscriptionClosed", "SubscriptionABC", "SubscribableABC"]

log = logging.getLogger(__name__)

T = TypeVar("T")

CallbackType = Callable[[T], Union[None, Awaitable[None]]]


class ListenerError(Exception, Generic[T]):
    event: T
    listener: CallbackType
    e: Exception

    def __init__(self, event: T, listener: CallbackType, e: Exception) -> None:
        super().__init__(str(e))
        self.event = event
        self.listener = listener
        self.e = e

    def __repr__(self) -> str:
        return f"ListenerError({self.event!r}, {self.listener!r}, {self.e!r})"

    def __str__(self) -> str:
        return f"{self.event} caused error in {self.listener}:\n{self.e}"


class SubscriptionClosed(Exception):
    ...


class ObservableABC(abc.ABC, Generic[T]):
    @overload
    def on(self, event: Type[T], callback: CallbackType) -> None:
        ...

    @abc.abstractmethod
    def on(self, event: Type[T], callback: CallbackType) -> None:
        ...

    @overload
    def off(self) -> None:
        ...

    @overload
    def off(self, event: Type[T]) -> None:
        ...

    @overload
    def off(self, event: Type[T], callback: CallbackType) -> None:
        ...

    @abc.abstractmethod
    def off(self, event: Type[T] = None, callback: CallbackType = None) -> None:
        ...

    @abc.abstractmethod
    def once(self, event: Type[T], callback: CallbackType) -> None:
        ...


class ChildEmitterABC(abc.ABC, Generic[T]):
    @abc.abstractmethod
    def emit(self, event: T) -> Awaitable[None]:
        ...


class EmitterABC(ChildEmitterABC):
    @abc.abstractmethod
    def add_child(self, emitter: ChildEmitterABC) -> None:
        ...

    @abc.abstractmethod
    def remove_child(self, emitter: ChildEmitterABC) -> None:
        ...


class SubscriptionABC(abc.ABC, Generic[T]):
    def __aiter__(self) -> AsyncIterable[T]:
        return self

    async def __anext__(self) -> AsyncIterable[T]:
        try:
            return await self.next()
        except SubscriptionClosed:
            raise StopAsyncIteration from None

    async def __aenter__(self) -> "SubscriptionABC":
        return self

    async def __aexit__(self, exc_type: Type[Exception], exc_val: Exception, exc_tb) -> None:
        self.unsubscribe()

    async def first(self) -> T:
        try:
            return await self.next()
        finally:
            self.unsubscribe()

    @property
    @abc.abstractmethod
    def closed(self) -> bool:
        ...

    @abc.abstractmethod
    async def next(self) -> T:
        ...

    @abc.abstractmethod
    def unsubscribe(self) -> None:
        ...


class SubscribableABC(abc.ABC, Generic[T]):
    @overload
    def subscribe(self) -> SubscriptionABC[T]:
        ...

    @overload
    def subscribe(self, event: Type[T]) -> SubscriptionABC[T]:
        ...

    @abc.abstractmethod
    def subscribe(self, event: Type[T] = None) -> SubscriptionABC[T]:
        ...
