# Owner: Dev A
"""Signal registry for executing rule-based integrity signals."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from engine.signals.attrition import zero_attrition_signal
from engine.signals.backdated import backdated_signal
from engine.signals.eligibility import eligibility_signal
from engine.signals.shared_contacts import shared_contacts_signal
from engine.types import Signal

SignalFn = Callable[..., list[Signal]]
RecordInput = list[dict[str, Any]] | dict[str, Any]


class SignalRegistry:
    """Registry responsible for registering and executing integrity signals."""

    def __init__(self, register_defaults: bool = True) -> None:
        self._signals: dict[str, SignalFn] = {}
        if register_defaults:
            self._register_default_signals()

    def _register_default_signals(self) -> None:
        """Register the core platform integrity signals."""
        self.register("eligibility", eligibility_signal)
        self.register("shared_contacts", shared_contacts_signal)
        self.register("backdated", backdated_signal)
        self.register("attrition", zero_attrition_signal)

    def register(
        self,
        signal_or_name: SignalFn | str,
        fn: SignalFn | None = None,
    ) -> SignalFn | Callable[[SignalFn], SignalFn]:
        """Register an integrity signal function.

        Can be used directly:
            registry.register(my_signal)
            registry.register("custom_name", my_signal)
        Or as a decorator:
            @registry.register
            def my_signal(records): ...
            @registry.register("custom_name")
            def my_signal(records): ...
        """
        # Case 1: registry.register("name", fn)
        if isinstance(signal_or_name, str) and fn is not None:
            if not callable(fn):
                raise TypeError(f"Signal '{signal_or_name}' must be callable.")
            self._signals[signal_or_name] = fn
            return fn

        # Case 2: @registry.register("name") decorator
        if isinstance(signal_or_name, str) and fn is None:
            name = signal_or_name

            def decorator(func: SignalFn) -> SignalFn:
                if not callable(func):
                    raise TypeError("Registered signal must be callable.")
                self._signals[name] = func
                return func

            return decorator

        # Case 3: registry.register(fn) or @registry.register
        if callable(signal_or_name):
            func = signal_or_name
            name = getattr(func, "__name__", str(func))
            self._signals[name] = func
            return func

        raise ValueError("Invalid arguments to SignalRegistry.register")

    def unregister(self, name: str) -> SignalFn | None:
        """Unregister a signal by name."""
        return self._signals.pop(name, None)

    def get(self, name: str) -> SignalFn | None:
        """Get a registered signal by name."""
        return self._signals.get(name)

    def list_signals(self) -> list[str]:
        """Return a sorted list of registered signal names."""
        return sorted(self._signals.keys())

    def clear(self) -> None:
        """Clear all registered signals."""
        self._signals.clear()

    def reset(self) -> None:
        """Reset the registry to default signals."""
        self.clear()
        self._register_default_signals()

    def execute(
        self,
        records: RecordInput,
        **kwargs: Any,
    ) -> list[Signal]:
        """Execute all registered signals against institution records.

        Input can be:
        - A list of student admission records: list[dict]
        - A dictionary containing: admissions, seat_pools, historical_stats, rules_config
        """
        if not records and not kwargs:
            return []

        # Parse admissions and auxiliary data from records / kwargs
        admissions: list[dict[str, Any]] = []
        historical_stats: list[dict[str, Any]] = []
        seat_pools: list[dict[str, Any]] = []
        rules_config: dict[str, Any] = kwargs.get("rules_config", {})

        if isinstance(records, list):
            admissions = records
            # Check if any items are historical stats
            if any(
                isinstance(r, dict)
                and ("utilisation" in r or "approved_seats" in r or "academic_year" in r)
                for r in records
            ):
                historical_stats = records
        elif isinstance(records, dict):
            admissions = (
                records.get("admissions") or records.get("records") or records.get("students") or []
            )
            historical_stats = records.get("historical_stats") or records.get("history") or []
            seat_pools = records.get("seat_pools") or records.get("pools") or []
            rules_config = {
                **records.get("rules_config", {}),
                **records.get("config", {}),
                **rules_config,
            }

        # Override or supplement from kwargs
        if "historical_stats" in kwargs:
            historical_stats = kwargs["historical_stats"]
        if "seat_pools" in kwargs:
            seat_pools = kwargs["seat_pools"]

        results: list[Signal] = []

        for _name, fn in self._signals.items():
            try:
                sig = inspect.signature(fn)
                params = sig.parameters
                call_args: list[Any] = []
                call_kwargs: dict[str, Any] = {}

                # Route appropriate arguments based on function signature
                if "historical_stats" in params:
                    call_kwargs["historical_stats"] = historical_stats
                elif "admissions" in params:
                    call_kwargs["admissions"] = admissions
                elif "records" in params:
                    call_kwargs["records"] = admissions if isinstance(records, dict) else records
                elif len(params) > 0:
                    # Default first positional argument
                    first_param = next(iter(params.values()))
                    if first_param.name in ("stats", "history"):
                        call_args.append(historical_stats)
                    else:
                        call_args.append(admissions)

                if "seat_pools" in params:
                    call_kwargs["seat_pools"] = seat_pools
                if "rules_config" in params:
                    call_kwargs["rules_config"] = rules_config

                # Pass through any extra kwargs matching the function parameters
                for k, v in kwargs.items():
                    if k in params and k not in call_kwargs:
                        call_kwargs[k] = v

                # Call the signal pure function
                output = fn(*call_args, **call_kwargs)
                if isinstance(output, list):
                    for item in output:
                        if isinstance(item, Signal):
                            results.append(item)
                elif isinstance(output, Signal):
                    results.append(output)
            except Exception:
                # Tolerate malformed data or gracefully continue
                continue

        return results


# Module-level default registry instance
default_registry = SignalRegistry()


def get_default_registry() -> SignalRegistry:
    """Return the global default SignalRegistry instance."""
    return default_registry


def register_signal(
    signal_or_name: SignalFn | str,
    fn: SignalFn | None = None,
) -> SignalFn | Callable[[SignalFn], SignalFn]:
    """Register a signal in the default SignalRegistry."""
    return default_registry.register(signal_or_name, fn)


def execute_signals(
    records: RecordInput,
    **kwargs: Any,
) -> list[Signal]:
    """Execute all default registered signals against the provided records."""
    return default_registry.execute(records, **kwargs)
