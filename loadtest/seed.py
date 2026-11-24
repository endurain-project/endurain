"""Seed the load-test database with users, activities, health records, gears, follows and notifications.

Runs inside the Endurain image so it uses the application's own code paths (users, activities, health, gears,
followers and notifications crud), against the database the stack's ``DB_*`` variables name::

    docker compose -p endurain-load --env-file .env.loadtest -f compose.yaml run --rm seed \
        --users 50 --activities-per-user 200 --days 730

Idempotent per ``--name``: a user (``lt-<name>-<n>``) is created in one transaction with everything that hangs off it,
so it either exists complete or not at all, and a second run skips the users that exist, then tops up the follows. The
credentials of every user of the seed go to ``--out`` for the Locust users to read.
"""

import argparse
import json
import random
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import core.config as core_config
import core.database as core_database
import core.platform_settings as core_platform_settings
import jasil.container as platform_container
import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings
import model_registry as orm_model_registry
import module_registry as runtime_module_registry
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_streams.constants as streams_constants
import modules.activities.activity_streams.contracts as streams_contracts
import modules.activities.activity_streams.crud as streams_crud
import modules.auth.credentials.integration_service as credentials_integration
import modules.followers.crud as followers_crud
import modules.followers.models as followers_models
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.schema as gears_schema
import modules.health.health_sleep.crud as sleep_crud
import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_steps.crud as steps_crud
import modules.health.health_steps.schema as steps_schema
import modules.health.health_water.crud as water_crud
import modules.health.health_water.schema as water_schema
import modules.health.health_weight.crud as weight_crud
import modules.health.health_weight.schema as weight_schema
import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.schema as notifications_schema
import modules.users.users.crud as users_crud
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service
import modules.users.users_integrations.integration_service as integrations_service
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

#: Hours (UTC) an activity may start at; with the day this makes the per-user start time unique.
_START_HOURS = (6, 10, 14, 18)

#: (activity type, relative weight, typical km per hour, typical distance in km).
_SPORTS = (
    (activity_constants.ActivityType.RUN, 40, 11.0, 9.0),
    (activity_constants.ActivityType.RIDE, 35, 25.0, 40.0),
    (activity_constants.ActivityType.WALK, 10, 5.0, 4.0),
    (activity_constants.ActivityType.HIKE, 5, 4.0, 10.0),
    (activity_constants.ActivityType.TRAIL_RUN, 5, 9.0, 12.0),
    (activity_constants.ActivityType.GRAVEL_RIDE, 5, 22.0, 50.0),
)

#: The Strava application id of the first linked user; user ``n`` gets ``STRAVA_CLIENT_BASE + n``. The stub (stub/stub.py)
#: reads the application from the access token, ``lt-<client id>-...``.
STRAVA_CLIENT_BASE = 900_000

#: Seed users all share one password, derived from the seed name; see :func:`_password`.
_BASE_LAT, _BASE_LON = 38.9, -8.85


def _password(name: str) -> str:
    """The password of every user of a seed.

    Args:
        name: The seed name.

    Returns:
        A password that satisfies the default policy.
    """
    return f"LoadTest-{name}-Password-2026!"


def _start_platform() -> None:
    """Build the platform substrate the way the CLI and the worker do, so crud and subscribers resolve."""
    orm_model_registry.import_all_models()
    substrate_settings = core_platform_settings.build_jasil_settings(
        core_config.settings, plain_areas=runtime_module_registry.storage_plain_areas()
    )
    jasil_settings.configure(substrate_settings)
    platform = platform_container.build_platform(substrate_settings, sources=runtime_module_registry.runtime_sources())
    platform_runtime.set_active_platform(platform)
    runtime_module_registry.configure_application()


def _link_strava(db: Session, user_id: uuid.UUID, index: int) -> None:
    """Link a user to the stub Strava (flushed, not committed).

    Each user is their own Strava application, as in a real deployment, so one application's rate limit stops only
    that user. Every other user's access token is about to expire, so their next sync refreshes it first.

    Args:
        db: Database session.
        user_id: The user to link.
        index: The user's number within the seed.
    """
    client_id = str(STRAVA_CLIENT_BASE + index)
    expires_in = timedelta(minutes=20) if index % 2 else timedelta(hours=6)
    integrations_service.set_strava_client(user_id, client_id, f"lt-secret-{client_id}", db, if_match="*")
    integrations_service.link_strava_account(
        user_id,
        {
            "access_token": f"lt-{client_id}-access-0",
            "refresh_token": f"lt-{client_id}-refresh-0",
            "expires_at": int((datetime.now(UTC) + expires_in).timestamp()),
        },
        db,
    )


def _waypoints(rng: random.Random, start: datetime, seconds: int, kind: str) -> list[dict[str, object]]:
    """Build the samples of one stream: one per ``seconds / 120`` seconds.

    Args:
        rng: Source of randomness.
        start: When the activity started.
        seconds: How long it lasted.
        kind: ``hr``, ``ele``, ``vel`` or ``map``.

    Returns:
        120 samples.
    """
    points = 120
    step = seconds / points
    out: list[dict[str, object]] = []
    lat, lon = _BASE_LAT + rng.uniform(-0.2, 0.2), _BASE_LON + rng.uniform(-0.2, 0.2)
    for i in range(points):
        stamp = (start + timedelta(seconds=i * step)).replace(tzinfo=None).isoformat()
        if kind == "hr":
            out.append({"time": stamp, "hr": int(125 + 35 * rng.random())})
        elif kind == "ele":
            out.append({"time": stamp, "ele": round(20 + 15 * (1 + (i % 30) / 30) + rng.random(), 1)})
        elif kind == "vel":
            out.append({"time": stamp, "vel": round(2.5 + rng.random(), 2)})
        else:
            lat += rng.uniform(-0.0003, 0.0004)
            lon += rng.uniform(-0.0003, 0.0004)
            out.append({"time": stamp, "lat": round(lat, 6), "lon": round(lon, 6)})
    return out


def _stage_activities(
    db: Session, rng: random.Random, user_id: uuid.UUID, gear_ids: list[uuid.UUID], args: argparse.Namespace, label: str
) -> int:
    """Stage a user's activities with their laps and streams (flushed, not committed).

    Args:
        db: Database session.
        rng: Source of randomness.
        user_id: The owner.
        gear_ids: The owner's gears, some of which an activity uses.
        args: The parsed command line.
        label: The user's username, which makes the dedup keys unique.

    Returns:
        How many activities were staged.
    """
    slots = [(day, hour) for day in range(args.days) for hour in _START_HOURS]
    if args.activities_per_user > len(slots):
        raise SystemExit(f"--activities-per-user {args.activities_per_user} does not fit in {args.days} days")
    today = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    weights = [sport[1] for sport in _SPORTS]
    for number, (day, hour) in enumerate(rng.sample(slots, args.activities_per_user)):
        sport, _, speed, typical_km = rng.choices(_SPORTS, weights)[0]
        km = max(1.0, rng.gauss(typical_km, typical_km / 4))
        seconds = int(km / speed * 3600)
        start = (today - timedelta(days=day + 1)).replace(hour=hour)
        visibility = rng.choices(
            [
                activity_constants.ActivityVisibility.FOLLOWERS,
                activity_constants.ActivityVisibility.PUBLIC,
                activity_constants.ActivityVisibility.PRIVATE,
            ],
            [70, 10, 20],
        )[0]
        values: dict[str, object] = {
            "user_id": user_id,
            "name": f"{sport.label} {number}",
            "distance": int(km * 1000),
            "activity_type": sport.stored,
            "start_time": start,
            "end_time": start + timedelta(seconds=seconds),
            "timezone": "Europe/Lisbon",
            "total_elapsed_time": float(seconds),
            "total_timer_time": float(seconds - 30),
            "visibility": visibility.stored,
            "elevation_gain": rng.randint(0, 600),
            "elevation_loss": rng.randint(0, 600),
            "average_hr": rng.randint(120, 160),
            "max_hr": rng.randint(165, 190),
            "average_speed": round(speed / 3.6, 2),
            "calories": int(km * 60),
            "gear_id": rng.choice(gear_ids) if gear_ids and rng.random() < 0.6 else None,
            **{name: False for name in ("is_hidden", "hide_start_time", "hide_location", "hide_map", "hide_hr")},
            **{f"hide_{name}": False for name in ("power", "cadence", "elevation", "speed", "pace", "laps", "gear")},
            "hide_workout_sets_steps": False,
        }
        activity = activity_crud.create_activity(
            activity_contracts.ActivityCore.model_validate(values), db, dedup_key=f"seed:{label}:{number}"
        )
        if rng.random() < args.laps_share:
            lap_seconds = seconds / 5
            activity_laps_crud.create_activity_laps(
                [
                    {
                        "start_time": start + timedelta(seconds=i * lap_seconds),
                        "total_elapsed_time": lap_seconds,
                        "total_timer_time": lap_seconds,
                        "total_distance": km * 1000 / 5,
                        "avg_heart_rate": rng.randint(120, 160),
                        "max_heart_rate": rng.randint(165, 190),
                    }
                    for i in range(5)
                ],
                activity.id,
                db,
            )
        if rng.random() < args.streams_share:
            streams_crud.create_activity_streams(
                [
                    streams_contracts.ActivityStreamsCreate(
                        activity_id=activity.id,
                        stream_type=stream_type,
                        stream_waypoints=_waypoints(rng, start, seconds, kind),
                    )
                    for stream_type, kind in (
                        (streams_constants.STREAM_TYPE_HR, "hr"),
                        (streams_constants.STREAM_TYPE_ELEVATION, "ele"),
                        (streams_constants.STREAM_TYPE_SPEED, "vel"),
                        (streams_constants.STREAM_TYPE_MAP, "map"),
                    )
                ],
                activity,
                db,
            )
        if number % 50 == 49:
            db.flush()
    return args.activities_per_user


def _stage_health(db: Session, rng: random.Random, user_id: uuid.UUID, days: int) -> int:
    """Stage one steps, weight, sleep and water record per day (flushed, not committed).

    Args:
        db: Database session.
        rng: Source of randomness.
        user_id: The owner.
        days: How many days back from yesterday.

    Returns:
        How many records were staged.
    """
    today = datetime.now(UTC).date()
    weight = rng.uniform(60, 90)
    for offset in range(1, days + 1):
        day: date = today - timedelta(days=offset)
        weight += rng.uniform(-0.2, 0.2)
        steps_crud.create_health_steps(
            user_id, steps_schema.HealthStepsImport(date=day, steps=rng.randint(2000, 18000)), db
        )
        weight_crud.create_health_weight(
            user_id, weight_schema.HealthWeightImport(date=day, weight_kg=round(weight, 1)), db
        )
        sleep_crud.create_health_sleep(
            user_id,
            sleep_schema.HealthSleepImport(
                date=day,
                total_sleep_seconds=rng.randint(5 * 3600, 9 * 3600),
                resting_heart_rate=rng.randint(45, 65),
                sleep_score_overall=rng.randint(55, 95),
            ),
            db,
        )
        water_crud.create_health_water(
            user_id, water_schema.HealthWaterImport(date=day, amount_ml=rng.randint(1200, 3200)), db
        )
    return days * 4


def _stage_account(
    db: Session, username: str, name: str, access_type: users_schema.UserAccessType, password_hash: str
) -> users_models.Users:
    """Stage an active, verified account with a local password and the defaults every user has (flushed).

    Args:
        db: Database session.
        username: The account's username; its email is ``<username>@example.com``.
        name: The account's display name.
        access_type: Regular or administrator.
        password_hash: The Argon2 hash of the seed's password.

    Returns:
        The new user.
    """
    user = users_crud.create_user(
        {
            "name": name,
            "username": username,
            "email": f"{username}@example.com",
            "preferred_language": "en",
            "access_type": access_type.value,
            "active": True,
            "email_verified": True,
            "pending_admin_approval": False,
        },
        db,
    )
    credentials_integration.set_local_password_hash(user.id, password_hash, db, change_required=False)
    users_service._stage_default_data(user.id, db)
    return user


def _user_exists(username: str) -> bool:
    """Return whether a user with this username exists.

    Args:
        username: The username to look for.

    Returns:
        True when the user exists.
    """
    with core_database.SessionLocal() as db:
        return bool(
            db.scalar(
                select(func.count()).select_from(users_models.Users).where(users_models.Users.username == username)
            )
        )


def _create_user(index: int, args: argparse.Namespace, password_hash: str) -> uuid.UUID | None:
    """Create user ``index`` with everything that hangs off it, in one transaction.

    Args:
        index: The user's number within the seed.
        args: The parsed command line.
        password_hash: The Argon2 hash of the seed's password.

    Returns:
        The new user's id, or None when the user already exists.
    """
    username = f"lt-{args.name}-{index:04d}"
    rng = random.Random(f"{args.name}:{index}")
    if _user_exists(username):
        return None
    with core_database.SessionLocal() as db:
        user = _stage_account(db, username, f"Load User {index}", users_schema.UserAccessType.REGULAR, password_hash)
        if index < args.strava_users:
            _link_strava(db, user.id, index)
        gear_ids = [
            gears_crud.create_gear(
                gears_schema.GearCreateRequest(nickname=f"{username} {kind} {n}", gear_type=kind), user.id, db
            ).id
            for n, kind in enumerate(("bike", "shoes", "bike"))
        ]
        _stage_activities(db, rng, user.id, gear_ids, args, username)
        _stage_health(db, rng, user.id, args.health_days)
        for kind in (
            notifications_constants.NotificationType.GARMIN_TOKEN_EXPIRED,
            notifications_constants.NotificationType.STRAVA_TOKEN_EXPIRED,
        ):
            notifications_crud.create_notification(
                notifications_schema.NotificationCreate(type=kind, user_id=user.id), db
            )
        db.commit()
        return user.id


def _create_admin(index: int, args: argparse.Namespace, password_hash: str) -> None:
    """Create administrator ``index``, who creates and deletes the accounts of the lifecycle scenario.

    The username is ``lta-<name>-<n>``, so it is never among the seed's ``lt-<name>-<n>`` users that the other
    scenarios use. An administrator that exists is kept.

    Args:
        index: The administrator's number within the seed.
        args: The parsed command line.
        password_hash: The Argon2 hash of the seed's password.
    """
    username = f"lta-{args.name}-{index:02d}"
    if _user_exists(username):
        return
    with core_database.SessionLocal() as db:
        _stage_account(db, username, f"Load Admin {index}", users_schema.UserAccessType.ADMIN, password_hash)
        db.commit()


def _ensure_follows(args: argparse.Namespace, user_ids: list[uuid.UUID]) -> int:
    """Make every user follow a few others, accepted, so feeds have content; existing follows are kept.

    Args:
        args: The parsed command line.
        user_ids: The seed's users.

    Returns:
        How many follows were created.
    """
    created = 0
    with core_database.SessionLocal() as db:
        existing = {
            (row.follower_id, row.followee_id) for row in db.execute(select(followers_models.Follower)).scalars()
        }
        for index, user_id in enumerate(user_ids):
            rng = random.Random(f"{args.name}:follows:{index}")
            others = [other for other in user_ids if other != user_id]
            for other in rng.sample(others, min(args.follows_per_user, len(others))):
                if (user_id, other) in existing:
                    continue
                followers_crud.create_follower(user_id, other, db)
                followers_crud.accept_follower(other, user_id, db)
                created += 1
        db.commit()
    return created


def main() -> int:
    """Seed the database and write the credentials file.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="load", help="seed name; usernames are lt-<name>-<n> (idempotency scope)")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--activities-per-user", type=int, default=50)
    parser.add_argument("--days", type=int, default=365, help="how far back activities are spread")
    parser.add_argument(
        "--health-days",
        type=int,
        default=60,
        choices=range(1, 361),
        metavar="1-360",
        help="days of steps/weight/sleep/water per user (the load test writes older dates, so keep under 360)",
    )
    parser.add_argument("--laps-share", type=float, default=0.4, help="share of activities that have laps")
    parser.add_argument("--streams-share", type=float, default=0.3, help="share of activities that have streams")
    parser.add_argument(
        "--strava-users", type=int, default=0, help="how many of the first users are linked to the stub Strava"
    )
    parser.add_argument("--follows-per-user", type=int, default=5)
    parser.add_argument(
        "--admins", type=int, default=2, help="administrators the lifecycle scenario creates and deletes accounts with"
    )
    parser.add_argument("--sample", type=int, default=60, help="activity ids per user written to the credentials file")
    parser.add_argument("--out", default="/loadtest/data/users.json", help="where the credentials go")
    args = parser.parse_args()

    core_config.check_required_env_vars()
    _start_platform()
    started = time.monotonic()
    password = _password(args.name)
    password_hash = credentials_integration.get_password_hasher().hash_password(password)

    created = 0
    for index in range(args.users):
        if _create_user(index, args, password_hash) is not None:
            created += 1
        if (index + 1) % 10 == 0:
            print(f"seed: {index + 1}/{args.users} users ({time.monotonic() - started:.0f}s)", flush=True)

    for index in range(args.admins):
        _create_admin(index, args, password_hash)

    with core_database.SessionLocal() as db:
        rows = db.execute(
            select(users_models.Users.id, users_models.Users.username)
            .where(users_models.Users.username.like(f"lt-{args.name}-%"))
            .order_by(users_models.Users.username)
        ).all()
        activities = db.scalar(
            select(func.count())
            .select_from(activity_models.Activity)
            .where(activity_models.Activity.user_id.in_([row.id for row in rows]))
        )
    follows = _ensure_follows(args, [row.id for row in rows])
    users = []
    with core_database.SessionLocal() as db:
        strava_ids = set(integrations_service.list_user_ids_with_strava_linked(None, 100_000, db))
        for row in rows:
            # A sample of the user's activities, with whether each has streams and laps, for the Locust users to read.
            sample = db.execute(
                text(
                    "SELECT a.id::text, EXISTS (SELECT 1 FROM activities_streams s WHERE s.activity_id = a.id), "
                    "EXISTS (SELECT 1 FROM activity_laps l WHERE l.activity_id = a.id) "
                    "FROM activities a WHERE a.user_id = :uid ORDER BY random() LIMIT :n"
                ),
                {"uid": row.id, "n": args.sample},
            ).all()
            users.append(
                {
                    "username": row.username,
                    "user_id": str(row.id),
                    "strava": row.id in strava_ids,
                    "activities": [{"id": r[0], "streams": r[1], "laps": r[2]} for r in sample],
                }
            )
        admins = [
            {"username": row.username, "user_id": str(row.id)}
            for row in db.execute(
                select(users_models.Users.id, users_models.Users.username)
                .where(users_models.Users.username.like(f"lta-{args.name}-%"))
                .order_by(users_models.Users.username)
            )
        ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": args.name, "password": password, "users": users, "admins": admins}, indent=2))
    print(
        f"seed {args.name!r}: {created} users created, {len(rows)} in total, {activities} activities, "
        f"{follows} follows created, credentials in {out} ({time.monotonic() - started:.0f}s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
