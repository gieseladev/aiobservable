from typing import Awaitable, Callable, Generic, Tuple, Type, TypeVar, Union

__all__ = ["MaybeAwaitable",
           "CallbackCallable", "PredicateCallable",
           "EventTypeTuple", "EventType",
           "ListenerError", "SubscriptionClosed"]

T = TypeVar("T")

MaybeAwaitable = Union[T, Awaitable[T]]

CallbackCallable = Callable[[T], MaybeAwaitable[None]]
PredicateCallable = Callable[[T], MaybeAwaitable[bool]]

EventTypeTuple = Tuple[Type[T], ...]
EventType = Union[Type[T], EventTypeTuple[T]]


class ListenerError(Exception, Generic[T]):
    """Exception event emitted when a listener raised an exception.

    Attributes:
        event: Event instance that was emitted.
        listener: Listener that raised the exception.
        e: Exception that was raised.
    """
    __slots__ = ("event", "listener", "e")

    event: T
    listener: CallbackCallable
    e: Exception

    def __init__(self, event: T, listener: CallbackCallable, e: Exception) -> None:
        super().__init__(str(e))
        self.event = event
        self.listener = listener
        self.e = e

    def __repr__(self) -> str:
        return f"ListenerError({self.event!r}, {self.listener!r}, {self.e!r})"

    def __str__(self) -> str:
        return f"{self.event} caused error in {self.listener}:\n{self.e}"


class SubscriptionClosed(Exception):
    """Exception raised if a closed subscription is used."""
    __slots__ = ()
