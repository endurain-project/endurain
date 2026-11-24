"""Row-locked writes of one user, against real PostgreSQL (``SELECT ... FOR UPDATE``).

``replace_photo_key`` must hand every caller the key it really replaced, or a stored photo is orphaned;
``approve_pending_user`` must approve a waiting user once however many administrators click at the same time.
"""

import threading

from sqlalchemy import text

import modules.users.users.crud as users_crud
from tests._factories.users import make_user


def _race(count: int, task) -> list:
    barrier = threading.Barrier(count)
    results: list = []
    errors: list[Exception] = []

    def run(position: int) -> None:
        try:
            barrier.wait()
            results.append(task(position))
        except Exception as err:
            errors.append(err)

    threads = [threading.Thread(target=run, args=(position,)) for position in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    return results


def test_simultaneous_photo_changes_each_learn_the_key_they_replaced(committed_sessions):
    with committed_sessions() as db:
        user_id = make_user(db, photo_path="photo-0").id
        db.commit()

    def replace(position: int) -> str | None:
        with committed_sessions() as db:
            previous = users_crud.replace_photo_key(user_id, f"photo-{position + 1}", db)
            db.commit()
        return previous

    replaced = _race(4, replace)

    with committed_sessions() as db:
        stored = db.execute(text("SELECT photo_path FROM users WHERE id = :i"), {"i": user_id}).scalar_one()
    # Every stored key is replaced exactly once: the chain 0 -> a -> b -> c -> d has no key seen twice or skipped.
    assert sorted(replaced) == sorted({"photo-0", "photo-1", "photo-2", "photo-3", "photo-4"} - {stored})


def test_a_user_waiting_for_approval_is_approved_once(committed_sessions):
    with committed_sessions() as db:
        user_id = make_user(db, active=False, pending_admin_approval=True, deactivated_at=None).id
        db.commit()

    def approve(_position: int) -> bool:
        with committed_sessions() as db:
            approved = users_crud.approve_pending_user(user_id, db)
            db.commit()
        return approved

    results = _race(4, approve)

    with committed_sessions() as db:
        active, pending = db.execute(
            text("SELECT active, pending_admin_approval FROM users WHERE id = :i"), {"i": user_id}
        ).one()
    assert sorted(results) == [False, False, False, True]
    assert (active, pending) == (True, False)
