import abc
import logging
from typing import AsyncIterable, Awaitable, Generic, Type, TypeVar, overload

from .types import CallbackCallable, EventType, PredicateCallable, SubscriptionClosed

__all__ = ["ObservableABC",
           "ChildEmitterABC", "EmitterABC",
           "SubscriptionABC", "SubscribableABC"]

log = logging.getLogger(__name__)

T = TypeVar("T")


class ObservableABC(abc.ABC, Generic[T]):
    """Abstract base class of an observable."""
    __slots__ = ()

    @overload
    def on(self, *, callback: CallbackCallable[T]) -> None: ...

    @overload
    def on(self, event: EventType[T], callback: CallbackCallable[T]) -> None: ...

    @abc.abstractmethod
    def on(self, event: EventType[T] = None, callback: CallbackCallable[T] = None) -> None:
        """Add a listener to the given event(s).

        If you want to listen to all events you can pass the callback to the
        `callback` keyword argument::

            def on_any_event(event):
                print(event)

            observable.on(callback=on_any_event)

        Args:
            event: Event selector. This can be the type of a single event or
                a tuple of multiple events to listen for. The latter case is
                equivalent to calling `on` for each event separately.
            callback: Callable to call when the selected events are emitted.
                It is called with the event instance as its only argument.
                If it returns an `Awaitable` (or is a coroutine) it is awaited
                before the emission "completes" (See `ChildEmitterABC.emit`).
        """
        ...

    @overload
    def once(self, *, callback: CallbackCallable[T]) -> None: ...

    @overload
    def once(self, event: EventType[T], callback: CallbackCallable[T]) -> None: ...

    @abc.abstractmethod
    def once(self, event: EventType[T] = None, callback: CallbackCallable[T] = None) -> None:
        """Add a listener which is only called once.

        This is basically the same as adding the listener using `on`
        and then calling `off` once the listener has been called.

        Args:
            event: Event selector. This can be the type of a single event or
                a tuple of multiple events to listen for.
            callback: Callable to call when the selected events are emitted.
                It is called with the event instance as its only argument.
                If it returns an `Awaitable` (or is a coroutine) it is awaited
                before the emission "completes" (See `ChildEmitterABC.emit`).
        """
        ...

    @overload
    def off(self, *, event: EventType[T]) -> None: ...

    @overload
    def off(self, *, callback: CallbackCallable[T]) -> None: ...

    @overload
    def off(self, event: EventType[T], callback: CallbackCallable[T]) -> None: ...

    @abc.abstractmethod
    def off(self, event: EventType[T] = None, callback: CallbackCallable[T] = None) -> None:
        """Disable an event listener or remove all listeners from an event.

        This can also be used to disable a listener that was added using `once`
        before it is called.

        To remove all listeners from an event, pass the event selector to the
        `event` keyword argument::

            class MyEvent:
                ...

            observable.off(event=MyEvent)

        To remove a listener which is listening to all events, pass the listener
        to the `callback` keyword argument::

            def on_any_event(event):
                print(event)

            observable.off(callback=on_any_event)

        Args:
            event: Event selector. This can be the type of a single event or
                a tuple of multiple events to remove the listeners for.
            callback: Event listener. This is the same callable that was passed
                to `on` or `once`.
        """
        ...


class ChildEmitterABC(abc.ABC, Generic[T]):
    """Abstract base class of a child event emitter.

    A child event emitter can be added as a child to an `EmitterABC`.
    Note that `EmitterABC` is itself a child emitter.
    """
    __slots__ = ()

    @abc.abstractmethod
    def emit(self, event: T) -> Awaitable[None]:
        """Emit an event to all observers.

        The order in which the observers receive the events isn't defined and
        shouldn't be depended upon.

        If a listener raises an error, a `ListenerError` event is emitted.
        If an error occurs while handling the `ListenerError` event, it is
        ignored.

        Attributes:
            event: Event object to emit

        Returns:
            `asyncio.Future` which resolves to `None` after all observers
            have handled the event.
        """
        ...


class EmitterABC(ChildEmitterABC[T], Generic[T]):
    """Abstract base class of an event emitter.

    An emitter can have children which emit all the events it does.
    """
    __slots__ = ()

    @abc.abstractmethod
    def has_child(self, emitter: ChildEmitterABC) -> bool:
        """Check whether the child emitter is a child of the emitter.

        Args:
            emitter: Emitter to check.

        Returns:
            Whether or not the given emitter is either a direct, or an indirect
            (child of a child) child of this emitter.
            Note that every emitter is a child of itself.
        """
        ...

    @abc.abstractmethod
    def add_child(self, emitter: ChildEmitterABC[T]) -> None:
        """Add a child emitter.

        Args:
            emitter: Child emitter to add.

        Raises:
            ValueError: If the child emitter already is a child of this emitter,
                or the emitter is a child of the child emitter.
                The second case is only possible if the child emitter is itself
                an instance of `EmitterABC`.
        """
        ...

    @abc.abstractmethod
    def remove_child(self, emitter: ChildEmitterABC[T]) -> None:
        """Remove a child emitter.

        Args:
            emitter: Child emitter to remove.

        Raises:
            ValueError: If the emitter isn't a direct child.
        """
        ...


class SubscriptionABC(abc.ABC, Generic[T]):
    """Abstract base class of a subscription.

    Subscriptions have the following properties:

    - awaiting a subscriptions is equal to calling `first()`::

        event = await subscription
        print(event)

    - can be used as an async iterable::

        async for event in subscription:
            print(event)

    - can be used as an async context manager which unsubscribes after
        it's closed::

        async with subscription:
            print(await subscription.next())
    """
    __slots__ = ()

    def __await__(self):
        return self.first().__await__()

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

    @overload
    async def first(self) -> T:
        ...

    @overload
    async def first(self, *, predicate: PredicateCallable[T] = None) -> T:
        ...

    async def first(self, *, predicate: PredicateCallable[T] = None) -> T:
        """Return the next event and unsubscribe.

        Args:
            predicate: Optional predicate for the event, same as in `next`.
                If `None`, any events is accepted.

        Raises:
            SubscriptionClosed: If the subscription is already closed.
        """
        try:
            return await self.next(predicate=predicate)
        finally:
            self.unsubscribe()

    @property
    @abc.abstractmethod
    def closed(self) -> bool:
        """Whether the subscription is closed and unusable.

        A closed subscription will raise `SubscriptionClosed` when trying
        to get the next event.
        """
        ...

    @overload
    async def next(self) -> T:
        ...

    @overload
    async def next(self, *, predicate: PredicateCallable[T]) -> T:
        ...

    @abc.abstractmethod
    async def next(self, *, predicate: PredicateCallable[T] = None) -> T:
        """Return the next event.

        Args:
            predicate: Optional callable which is called with the event instance
                and returns a `bool`. Only events for which the predicate
                returns `True` are accepted.
                If the predicate is `None`, all events are accepted.

        Raises:
            SubscriptionClosed: If the subscription is already closed.
        """
        ...

    @abc.abstractmethod
    def unsubscribe(self) -> None:
        """Unsubscribe from the event and close the subscription.

        After calling this method, the subscription is closed and no longer
        usable. Waiting for a new event will only raise `SubscriptionClosed`.
        """
        ...


class SubscribableABC(abc.ABC, Generic[T]):
    """Abstract base class of a subscribable object."""
    __slots__ = ()

    @overload
    def subscribe(self) -> SubscriptionABC[T]: ...

    @overload
    def subscribe(self, event: EventType[T]) -> SubscriptionABC[T]: ...

    @abc.abstractmethod
    def subscribe(self, event: EventType[T] = None) -> SubscriptionABC[T]:
        """Subscribe to the given event(s).

        Args:
            event: Event selector. Event type or multiple event types to
                subscribe to. Can be `None` which will subscribe to all events.

        Returns:
            A subscription which is subscribed to the selected events.
        """
        ...
