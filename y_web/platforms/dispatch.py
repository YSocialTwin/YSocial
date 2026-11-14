"""Views that more than one platform repository provides at the same address (plan, phase F9.1).

Each repository is an independent silo: the Standard and the HPC repository of one platform both serve, say,
``/<exp_id>/publish`` with their own code. The core must not register two rules for one address (the first would win
silently), nor let two views claim one endpoint name. While the providers attach their routes (see
:func:`collecting`) the blueprints they decorate are replaced by :class:`ProviderBlueprint`, which records the rules;
when every provider has attached, :meth:`RouteCollector.commit` registers them in the real blueprints:

* an address (rule and methods) served by **one** provider is registered as the provider wrote it, endpoint name
  included: nothing changes for the platforms that have a single repository;
* an address served by **several** providers is registered once, with a dispatcher that runs the view of the provider
  that runs the current experiment (see :func:`resolve_experiment`) and answers 404 when that provider does not serve
  the address;
* two different addresses that claim the same endpoint name keep the first one's name; the other is registered as
  ``<provider id>__<endpoint>``, so repositories cannot collide by construction.

Outside :func:`collecting` (tests, a platform attached on its own) a blueprint is used as it is.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from flask import abort

logger = logging.getLogger(__name__)

#: the collector of the attach phase currently running (``None`` outside it) and the provider that is attaching
_COLLECTOR: ContextVar[Optional["RouteCollector"]] = ContextVar(
    "platform_route_collector", default=None
)
_CURRENT: ContextVar[Optional[str]] = ContextVar("platform_route_owner", default=None)

#: ways to find the experiment a request is about, tried in order; each takes the view arguments of the request
#: (``{"exp_id": 3}``) and returns the experiment or ``None``
EXPERIMENT_RESOLVERS: List[Callable[[Dict[str, Any]], Any]] = []

#: names the experiment id has in the addresses of the platforms
EXPERIMENT_ARGUMENTS = ("exp_id", "idexp", "experiment_id")


def _experiment_from_view_arguments(arguments: Dict[str, Any]) -> Any:
    from y_web.src.models import Exps

    for name in EXPERIMENT_ARGUMENTS:
        if arguments.get(name) is not None:
            try:
                return Exps.query.filter_by(idexp=int(arguments[name])).first()
            except (TypeError, ValueError):
                return None
    return None


EXPERIMENT_RESOLVERS.append(_experiment_from_view_arguments)


def resolve_experiment(arguments: Dict[str, Any]) -> Any:
    """The experiment a request is about, or ``None`` when no resolver can tell."""
    for resolver in EXPERIMENT_RESOLVERS:
        experiment = resolver(arguments)
        if experiment is not None:
            return experiment
    return None


def _rule_key(rule: str, options: Dict[str, Any]) -> Tuple[str, Tuple[str, ...]]:
    methods = options.get("methods") or ("GET",)
    return rule, tuple(sorted({m.upper() for m in methods} | _implicit(methods)))


def _implicit(methods) -> set:
    return {"HEAD", "OPTIONS"} if "GET" in {m.upper() for m in methods} else set()


class ProviderBlueprint:
    """Stands in for a blueprint of the core while a provider attaches its routes: ``route`` and ``add_url_rule`` are
    recorded, everything else (``before_request``, ``context_processor``...) goes to the real blueprint.
    """

    def __init__(self, blueprint: Any, owner: str, collector: "RouteCollector"):
        self._blueprint = blueprint
        self._owner = owner
        self._collector = collector

    def __getattr__(self, name: str) -> Any:
        return getattr(self._blueprint, name)

    def _shortcut(self, method: str, rule: str, options: Dict[str, Any]) -> Callable:
        return self.route(rule, methods=[method], **options)

    def get(self, rule: str, **options: Any) -> Callable:
        return self._shortcut("GET", rule, options)

    def post(self, rule: str, **options: Any) -> Callable:
        return self._shortcut("POST", rule, options)

    def put(self, rule: str, **options: Any) -> Callable:
        return self._shortcut("PUT", rule, options)

    def delete(self, rule: str, **options: Any) -> Callable:
        return self._shortcut("DELETE", rule, options)

    def patch(self, rule: str, **options: Any) -> Callable:
        return self._shortcut("PATCH", rule, options)

    def route(self, rule: str, **options: Any) -> Callable:
        def decorator(view):
            self.add_url_rule(rule, options.pop("endpoint", None), view, **options)
            return view

        return decorator

    def add_url_rule(
        self,
        rule: str,
        endpoint: Optional[str] = None,
        view_func: Optional[Callable] = None,
        **options: Any,
    ) -> None:
        if view_func is None:
            raise TypeError("a platform route needs a view")
        self._collector.add(
            self._blueprint,
            self._owner,
            rule,
            endpoint or view_func.__name__,
            view_func,
            options,
        )


class RouteCollector:
    """Rules recorded while the providers attach, registered together by :meth:`commit`."""

    def __init__(self) -> None:
        # (blueprint, rule key) -> [(owner, endpoint, view, options)], in the order the providers attached
        self._rules: Dict[Tuple[int, Tuple], List[Tuple[str, str, Callable, dict]]] = {}
        self._blueprints: Dict[int, Any] = {}

    def add(self, blueprint, owner, rule, endpoint, view, options) -> None:
        self._blueprints[id(blueprint)] = blueprint
        key = (id(blueprint), _rule_key(rule, options))
        self._rules.setdefault(key, []).append((owner, endpoint, view, options))

    def commit(self) -> List[str]:
        """Register what was recorded. Never raises: returns the problems found."""
        problems: List[str] = []
        taken: Dict[Tuple[int, str], Tuple] = {}
        for key, entries in self._rules.items():
            blueprint = self._blueprints[key[0]]
            rule = key[1][0]
            try:
                first_owner, endpoint, view, options = entries[0]
                if len(entries) > 1:
                    view = _dispatcher(
                        endpoint, {owner: v for owner, _, v, _ in entries}
                    )
                owner_of_endpoint = taken.get((key[0], endpoint))
                if owner_of_endpoint is not None and owner_of_endpoint != key[1]:
                    endpoint = f"{first_owner}__{endpoint}"
                taken[(key[0], endpoint)] = key[1]
                blueprint.add_url_rule(
                    rule, endpoint, view, **{k: v for k, v in options.items()}
                )
            except (
                Exception
            ) as exc:  # noqa: BLE001 - a bad platform must not stop the application
                problems.append(f"{rule}: {exc}")
                logger.warning("[platform routes] %s: %s", rule, exc)
        self._rules.clear()
        return problems


def _dispatcher(endpoint: str, views: Dict[str, Callable]) -> Callable:
    """A view that runs the view of the provider of the current experiment."""

    def dispatch(*args: Any, **kwargs: Any) -> Any:
        from flask import request

        from y_web.platforms import registry

        experiment = resolve_experiment(dict(request.view_args or kwargs))
        provider = registry.for_experiment(experiment) if experiment else None
        view = views.get(provider.provider_id) if provider else None
        if view is None:
            abort(404)
        return view(*args, **kwargs)

    dispatch.__name__ = endpoint
    dispatch.__qualname__ = f"dispatch[{endpoint}]"
    return dispatch


@contextmanager
def collecting() -> Iterator[RouteCollector]:
    """Collect the routes the providers attach and register them on exit (see the module docstring)."""
    collector = RouteCollector()
    token = _COLLECTOR.set(collector)
    try:
        yield collector
    finally:
        _COLLECTOR.reset(token)
    collector.commit()


@contextmanager
def attaching(owner: str) -> Iterator[None]:
    """The provider ``owner`` is attaching its routes."""
    token = _CURRENT.set(owner)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def wrap(blueprint: Any) -> Any:
    """``blueprint`` as a provider must see it: a recording stand-in while routes are being collected."""
    collector, owner = _COLLECTOR.get(), _CURRENT.get()
    if collector is None or owner is None:
        return blueprint
    return ProviderBlueprint(blueprint, owner, collector)
