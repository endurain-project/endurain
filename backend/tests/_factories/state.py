"""A platform state backend that is down, for tests of the stores built on it."""

from collections.abc import Callable

from jasil.providers import StateBackendUnavailableError


class DownState:
    """A state backend that cannot be reached: every operation raises the outage error."""

    def __getattr__(self, name: str) -> Callable[..., None]:
        def unavailable(*args: object, **kwargs: object) -> None:
            raise StateBackendUnavailableError("down")

        return unavailable
