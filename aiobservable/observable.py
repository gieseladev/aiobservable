import asyncio
import inspect
import logging
from typing import Awaitable, Callable, Container, Dict, Generic, Iterable, List, MutableMapping, Optional, Set, Type, \
    TypeVar, overload

from .abstract import ChildEmitterABC, EmitterABC, ObservableABC, SubscribableABC, SubscriptionABC
from .types import CallbackCallable, EventType, EventTypeTuple, ListenerError, MaybeAwaitable, PredicateCallable, \
    SubscriptionClosed

__all__ = ["Subscription", "Observable"]

log = logging.getLogger(__name__)

T = TypeVar("T")


async def maybe_await(a: MaybeAwaitable[T]) -> T:
    """Await and return the given object if it's awaitable, otherwise just return.

    Args:
        a: Awaitable to await or object to pass.

    Returns:
        Either the result of awaiting the `Awaitable` or the object.
    """
    if inspect.isawaitable(a):
        return await a
    else:
        return a


class Subscription(SubscriptionABC[T], Generic[T]):
    """Implementation of `SubscriptionABC` used by `Observable`.

    You should not create an instance of this class yourself, instead you
    should use the `Observable.subscribe` method.
    """
    __slots__ = ("__closed", "__unsub",
                 "__event_set", "__current")

    __closed: bool
    __unsub: Callable[[], None]

    __event_set: asyncio.Event
    __current: Optional[T]

    def __init__(self, unsub: Callable[[], None]) -> None:
        self.__unsub = unsub

        self.__closed = False
        self.__event_set = asyncio.Event()
        self.__current = None

    @property
    def closed(self) -> bool:
        return self.__closed

    async def _next(self) -> T:
        await self.__event_set.wait()

        if self.__closed:
            raise SubscriptionClosed

        self.__event_set.clear()
        return self.__current

    @overload
    async def next(self) -> T:
        ...

    @overload
    async def next(self, *, predicate: PredicateCallable[T]) -> T:
        ...

    async def next(self, predicate: PredicateCallable = None) -> T:
        if predicate is None:
            return await self._next()

        while True:
            event = await self._next()
            if await maybe_await(predicate(event)):
                return event

    def _emit(self, event: T) -> None:
        if self.__closed:
            log.warning("received event even though subscription is closed: %s", self)
            return

        self.__current = event
        self.__event_set.set()

    def unsubscribe(self) -> None:
        if self.__closed:
            return

        self.__unsub()
        self.__closed = True
        self.__event_set.set()


class Observable(ObservableABC[T], EmitterABC[T], SubscribableABC[T], Generic[T]):
    """Observable implementation.

    Even though the class is called "Observable" it is more than just an
    implementation of `ObservableABC`, it also implements `EmitterABC` and
    `SubscribableABC`.

    This implementation is invariant in the event type. This means that if
    we have two event types A and B, where B is a subclass of A, observers
    of A won't receive events of type B. Regardless of inheritance, events
    are treated differently.

    Args:
        events: Iterable of event types. When not `None`, this restricts
            the observable to the given event types. When trying to emit
            or observe an event that isn't in the given `Iterable`, a
            `TypeError` is raised.
    """
    __slots__ = ("__listeners", "__once_listeners",
                 "__subscriptions",
                 "__child_emitters",
                 "__events")

    __listeners: Dict[Optional[Type[T]], List[CallbackCallable[T]]]
    __once_listeners: Dict[Optional[Type[T]], List[CallbackCallable[T]]]
    __subscriptions: Dict[Optional[Type[T]], List[Subscription]]

    __child_emitters: List[ChildEmitterABC]

    __events: Optional[Set[Type[T]]]

    def __init__(self, events: Iterable[Type[T]] = None) -> None:
        self.__listeners = {}
        self.__once_listeners = {}
        self.__subscriptions = {}

        self.__child_emitters = []

        if events is not None:
            events = set(events)
            events.update((ListenerError,))

        self.__events = events

    def __check_event(self, event: EventType[T]) -> None:
        if self.__events is None:
            return

        events = get_events(event)
        if not all(event in self.__events for event in events):
            raise TypeError(f"{self} does not emit {event}!")

    def __add_listener(self, event: Optional[EventType[T]],
                       callback: Optional[CallbackCallable[T]], *,
                       once: bool, caller: str) -> None:
        if callback is None:
            raise TypeError(f"{caller}(): \"callback\" needs to be provided")
        elif not callable(callback):
            raise TypeError(f"{caller}() \"callback\" has to be callable")

        if event is None:
            # use None as a special key
            events = (None,)
        else:
            events = get_events(event)
            self.__check_event(events)

        mapping = self.__once_listeners if once else self.__listeners

        def get_listeners(event_local: Type[T]) -> List[CallbackCallable[T]]:
            return get_or_default_factory(mapping, event_local, list)

        # first ensure that all events don't already have the given listener
        for event_ in events:
            _check_listener(event_, get_listeners(event_), callback)

        # then add the listener to the events
        for event_ in events:
            get_listeners(event_).append(callback)

    @overload
    def on(self, *, callback: CallbackCallable[T]) -> None:
        ...

    @overload
    def on(self, event: EventType[T], callback: CallbackCallable[T]) -> None:
        ...

    def on(self, event: EventType[T] = None, callback: CallbackCallable[T] = None) -> None:
        self.__add_listener(event, callback, once=False, caller="on")

    @overload
    def once(self, *, callback: CallbackCallable[T]) -> None:
        ...

    @overload
    def once(self, event: EventType[T], callback: CallbackCallable[T]) -> None:
        ...

    def once(self, event: EventType[T] = None, callback: CallbackCallable[T] = None) -> None:
        self.__add_listener(event, callback, once=True, caller="off")

    def __remove_callback_from_listeners(self, event: Optional[Type[T]], callback: CallbackCallable[T]) -> None:
        try:
            self.__listeners[event].remove(callback)
        except (KeyError, ValueError):
            pass

        try:
            self.__once_listeners[event].remove(callback)
        except (KeyError, ValueError):
            pass

    def __remove_listener_from_all_events(self, callback: CallbackCallable[T]) -> None:
        self.__remove_callback_from_listeners(None, callback)

    def __remove_listeners_from_events(self, events: EventTypeTuple[T]) -> None:
        for event in events:
            try:
                del self.__listeners[event]
            except KeyError:
                pass

            try:
                del self.__once_listeners[event]
            except KeyError:
                pass

    def __remove_callback_from_events(self, events: EventTypeTuple[T], callback: CallbackCallable[T]) -> None:
        for event in events:
            self.__remove_callback_from_listeners(event, callback)

    @overload
    def off(self, *, event: EventType[T]) -> None:
        ...

    @overload
    def off(self, *, callback: CallbackCallable[T]) -> None:
        ...

    @overload
    def off(self, event: EventType[T], callback: CallbackCallable[T]) -> None:
        ...

    def off(self, event: EventType[T] = None, callback: CallbackCallable[T] = None) -> None:
        if event is None and callback is None:
            raise TypeError("off() requires either \"event\", \"callback\", or both")

        if event is None:
            self.__remove_listener_from_all_events(callback)
            return

        events = get_events(event)
        self.__check_event(events)

        if callback is None:
            self.__remove_listeners_from_events(events)
        else:
            self.__remove_callback_from_events(events, callback)

    def __emit_subscriptions(self, event: T) -> None:
        subscriptions: List[Subscription] = []

        try:
            subscriptions.extend(self.__subscriptions[type(event)])
        except KeyError:
            pass

        try:
            subscriptions.extend(self.__subscriptions[None])
        except KeyError:
            pass

        for subscription in subscriptions:
            subscription._emit(event)

    def __fire_listener(self, listener: CallbackCallable[T], event: T, *,
                        loop: asyncio.AbstractEventLoop,
                        ignore_exceptions: bool) -> asyncio.Future:
        async def fire_listener() -> None:
            try:
                await maybe_await(listener(event))
            except Exception as e:
                log.error("%s couldn't handle event %s: %s", listener, event, e)

                if not ignore_exceptions:
                    _ = self.__emit(ListenerError(event, listener, e), ignore_exceptions=True)

        return loop.create_task(fire_listener())

    def __fire_listeners(self, listeners: Iterable[CallbackCallable[T]], event: T, *,
                         loop: asyncio.AbstractEventLoop,
                         ignore_exceptions: bool) -> Iterable[asyncio.Future]:
        def fire(listener: CallbackCallable[T]) -> asyncio.Future:
            return self.__fire_listener(listener, event, loop=loop, ignore_exceptions=ignore_exceptions)

        return map(fire, listeners)

    def __emit_listeners(self, event: T, *,
                         loop: asyncio.AbstractEventLoop,
                         ignore_exceptions: bool) -> Iterable[asyncio.Future]:
        try:
            listeners = self.__listeners[type(event)]
        except KeyError:
            return ()

        return self.__fire_listeners(listeners, event, loop=loop, ignore_exceptions=ignore_exceptions)

    def __emit_once_listeners(self, event: T, *,
                              loop: asyncio.AbstractEventLoop,
                              ignore_exceptions: bool) -> Iterable[asyncio.Future]:
        try:
            listeners = self.__once_listeners[type(event)]
        except KeyError:
            return ()

        return self.__fire_listeners(listeners, event, loop=loop, ignore_exceptions=ignore_exceptions)

    def __emit(self, event: T, *, ignore_exceptions: bool) -> asyncio.Future:
        log.debug("%s emitting %s", self, event)

        event_type = type(event)
        self.__check_event(event_type)

        self.__emit_subscriptions(event)

        futures: List[Awaitable] = []

        loop = asyncio.get_event_loop()
        futures.extend(self.__emit_once_listeners(event, loop=loop, ignore_exceptions=ignore_exceptions))
        futures.extend(self.__emit_listeners(event, loop=loop, ignore_exceptions=ignore_exceptions))

        for emitter in self.__child_emitters:
            futures.append(emitter.emit(event))

        return asyncio.gather(*futures)

    def emit(self, event: T) -> Awaitable[None]:
        return self.__emit(event, ignore_exceptions=False)

    def has_child(self, emitter: ChildEmitterABC) -> bool:
        if emitter in self.__child_emitters:
            return True

        for child_emitter in self.__child_emitters:
            if isinstance(child_emitter, EmitterABC):
                if child_emitter.has_child(emitter):
                    return True

        return False

    def add_child(self, emitter: ChildEmitterABC[T]) -> None:
        if self.has_child(emitter):
            raise ValueError(f"{emitter} is already a child of {self}")

        if isinstance(emitter, EmitterABC) and emitter.has_child(self):
            raise ValueError(f"{emitter} already has {self} as a child, adding "
                             f"it as a child to {self} would cause an infinite loop.")

        self.__child_emitters.append(emitter)

    def remove_child(self, emitter: ChildEmitterABC[T]) -> None:
        try:
            self.__child_emitters.remove(emitter)
        except ValueError:
            raise ValueError(f"{emitter} is not a child of {self}") from None

    def __unsubscribe(self, events: EventTypeTuple, subscription: Subscription) -> None:
        for event in events:
            try:
                self.__subscriptions[event].remove(subscription)
            except (KeyError, ValueError):
                pass

    @overload
    def subscribe(self) -> SubscriptionABC[T]:
        ...

    @overload
    def subscribe(self, event: EventType[T]) -> SubscriptionABC[T]:
        ...

    def subscribe(self, event: EventType[T] = None) -> SubscriptionABC:
        if event is None:
            events = (None,)
        else:
            events = get_events(event)
            self.__check_event(events)

        def unsub() -> None:
            self.__unsubscribe(events, subscription)

        subscription = Subscription(unsub)

        for event in events:
            subscriptions = get_or_default_factory(self.__subscriptions, event, list)
            subscriptions.append(subscription)

        return subscription


def _check_listener(event: Optional[type], listeners: Container[CallbackCallable], listener: CallbackCallable) -> None:
    if listener in listeners:
        if event is None:
            event = "all events"

        raise ValueError(f"{listener} already listening to {event}")


def get_events(event: EventType[T]) -> EventTypeTuple[T]:
    if isinstance(event, tuple):
        return event
    else:
        return event,


K = TypeVar("K")
V_co = TypeVar("V_co", covariant=True)


def get_or_default_factory(mapping: MutableMapping[K, V_co], key: K,
                           factory: Callable[[], V_co]) -> V_co:
    try:
        return mapping[key]
    except KeyError:
        value = mapping[key] = factory()
        return value
