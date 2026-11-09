"""An in-memory stand-in for the account security generations, for tests that run without PostgreSQL."""

from sqlalchemy.orm import Session


class FakeSecurityGenerations:
    """Holds each user's generation in memory with the semantics of the real integration service.

    A bump takes effect at once rather than at the caller's commit, which is what a test that starts a proof, makes a
    security change and then redeems the proof needs.

    Attributes:
        generations: The generation of each user that has one; a missing user is at 0.
        bumps: The user ids that were bumped, in order.
    """

    def __init__(self) -> None:
        """Start with every user at generation 0."""
        self.generations: dict[int, int] = {}
        self.bumps: list[int] = []

    def current_generation(self, user_id: int, db: Session) -> int:
        """Return the user's generation."""
        return self.generations.get(user_id, 0)

    def stage_bump(self, user_id: int, db: Session) -> None:
        """Advance the user's generation by one."""
        self.generations[user_id] = self.generations.get(user_id, 0) + 1
        self.bumps.append(user_id)

    def matches_locked(self, user_id: int, stamped: int | None, db: Session) -> bool:
        """Return whether a stamp is the user's current generation; a missing stamp never is."""
        return stamped is not None and self.generations.get(user_id, 0) == stamped
