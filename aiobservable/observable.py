import asyncio
import inspect
import logging
from typing import Awaitable, Callable, Container, Dict, Generic, Iterable, List, Optional, Set, Tuple, Type, TypeVar, \
    Union

from .abstract import CallbackType, ChildEmitterABC, EmitterABC, ListenerError, MaybeAwaitable, ObservableABC, \
    PredicateCallableType, SubscribableABC, SubscriptionABC, SubscriptionClosed

__all__ = ["Subscription", "Observable"]

log = logging.getLogger(__name__)

T = TypeVar("T")


async def maybe_await(a: MaybeAwaitable[T]) -> T:
    if inspect.isawaitable(a):
        return await a
    else:
        return a


class Subscription(SubscriptionABC[T], Generic[T]):
    __slots__ = ("__closed", "__unsub",
                 "__event_set", "__current")

    __closed: bool
    __unsub: Callable[[], None]

    __event_set: asyncio.Event
    __current: Optional[T]

    def __init__(self, unsub: Callable[[], None], loop: asyncio.AbstractEventLoop = None) -> None:
        self.__unsub = unsub

        self.__closed = False
        self.__event_set = asyncio.Event(loop=loop)
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

    async def next(self, predicate: PredicateCallableType = None) -> T:
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


class Observable(ObservableABC[T], EmitterABC, SubscribableABC[T], Generic[T]):
    __slots__ = ("loop",
                 "__listeners", "__once_listeners", "__child_emitters",
                 "__events")

    loop: Optional[asyncio.AbstractEventLoop]

    __listeners: Dict[Type[T], List[CallbackType[T]]]
    __once_listeners: Dict[Type[T], List[Tuple[CallbackType[T], Optional[PredicateCallableType[T]]]]]
    __child_emitters: List[ChildEmitterABC]
    __subscriptions: Dict[Union[Type[T], None], List[Subscription]]

    __events: Optional[Set[Type[T]]]

    def __init__(self, events: Iterable[Type[T]] = None, *, loop: asyncio.AbstractEventLoop = None) -> None:
        self.loop = loop

        self.__listeners = {}
        self.__once_listeners = {}
        self.__child_emitters = []
        self.__subscriptions = {}

        if events is not None:
            events = set(events)
            events.update((ListenerError,))

        self.__events = events

    def __check_event(self, event: Type[T]) -> None:
        if self.__events is not None and event not in self.__events:
            raise TypeError(f"{self} does not emit {event}!")

    def on(self, event: Type[T], callback: CallbackType[T]) -> None:
        self.__check_event(event)

        try:
            listeners = self.__listeners[event]
        except KeyError:
            listeners = self.__listeners[event] = []

        _check_listener(event, listeners, callback)
        listeners.append(callback)

    def off(self, event: Type[T] = None, callback: CallbackType[T] = None) -> None:
        if event is None:
            self.__listeners = {}
            return

        self.__check_event(event)

        if callback is None:
            try:
                del self.__listeners[event]
            except KeyError:
                pass
        else:
            try:
                self.__listeners[event].remove(callback)
            except (KeyError, ValueError):
                raise ValueError(f"{callback} is not listening to {event}") from None

    def once(self, event: Type[T], callback: CallbackType[T], *, predicate: PredicateCallableType[T] = None) -> None:
        self.__check_event(event)

        try:
            tups = self.__once_listeners[event]
        except KeyError:
            tups = self.__once_listeners[event] = []

        try:
            listeners = next(zip(*tups))
        except StopIteration:
            pass
        else:
            _check_listener(event, listeners, callback)

        tups.append((callback, predicate))

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

    def __fire_listener(self, listener: CallbackType[T], event: T, *,
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

    def __emit_listeners(self, event: T, *,
                         loop: asyncio.AbstractEventLoop,
                         ignore_exceptions: bool) -> Iterable[asyncio.Future]:
        try:
            listeners = self.__listeners[type(event)]
        except KeyError:
            return ()

        def fire(listener: CallbackType[T]) -> asyncio.Future:
            return self.__fire_listener(listener, event, loop=loop, ignore_exceptions=ignore_exceptions)

        return map(fire, listeners)

    def __emit_once_listeners(self, event: T, *,
                              loop: asyncio.AbstractEventLoop,
                              ignore_exceptions: bool) -> Iterable[asyncio.Future]:
        try:
            listeners = self.__once_listeners[type(event)]
        except KeyError:
            return ()

        async def fire(listener: CallbackType[T], predicate: Optional[PredicateCallableType[T]]) -> None:
            if not (predicate is None or await maybe_await(predicate(event))):
                return

            try:
                listeners.remove((listener, predicate))
            except ValueError:
                # we're no longer in the list
                return

            await self.__fire_listener(listener, event, loop=loop, ignore_exceptions=ignore_exceptions)

        def fire_task(tup: Tuple[CallbackType[T], Optional[PredicateCallableType[T]]]) -> asyncio.Future:
            return loop.create_task(fire(*tup))

        return map(fire_task, listeners)

    def __emit(self, event: T, *, ignore_exceptions: bool) -> asyncio.Future:
        log.debug("%s emitting %s", self, event)

        event_type = type(event)
        self.__check_event(event_type)

        loop = self.loop or asyncio.get_event_loop()

        self.__emit_subscriptions(event)

        futures: List[Awaitable] = []

        futures.extend(self.__emit_once_listeners(event, loop=loop, ignore_exceptions=ignore_exceptions))
        futures.extend(self.__emit_listeners(event, loop=loop, ignore_exceptions=ignore_exceptions))

        for emitter in self.__child_emitters:
            futures.append(emitter.emit(event))

        return asyncio.gather(*futures, loop=loop)

    def emit(self, event: T) -> Awaitable[None]:
        return self.__emit(event, ignore_exceptions=False)

    def add_child(self, emitter: ChildEmitterABC) -> None:
        if emitter in self.__child_emitters:
            raise ValueError(f"{emitter} is already a child of {self}")

        self.__child_emitters.append(emitter)

    def remove_child(self, emitter: ChildEmitterABC) -> None:
        try:
            self.__child_emitters.remove(emitter)
        except ValueError:
            raise ValueError(f"{emitter} is not a child of {self}") from None

    def __unsubscribe(self, event: Optional[Type[T]], subscription: Subscription) -> None:
        try:
            self.__subscriptions[event].remove(subscription)
        except (KeyError, ValueError):
            pass

    def subscribe(self, event: Type[T] = None) -> SubscriptionABC:
        if event is not None:
            self.__check_event(event)

        try:
            subscriptions = self.__subscriptions[event]
        except KeyError:
            subscriptions = self.__subscriptions[event] = []

        def unsub() -> None:
            self.__unsubscribe(event, subscription)

        subscription = Subscription(unsub, loop=self.loop)
        subscriptions.append(subscription)

        return subscription


def _check_listener(event: type, listeners: Container[CallbackType], listener: CallbackType) -> None:
    if listener in listeners:
        raise ValueError(f"{listener} already listening to {event}")
