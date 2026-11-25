"""A Garmin Connect account and the rows of a linked user, for tests on the real database.

Garmin Connect is a third party, so it is faked at the boundary the module calls: the ``garminconnect.Garmin`` client
the module builds. :class:`GarminAccount` stands for one Garmin Connect account (its activities, gear, health data, the
answers it gives and the errors it raises) and :meth:`GarminAccount.install` makes every client the module builds talk
to it. Everything of ours (the stored token, the activities, gear and health records a sync writes, the shared state)
stays real.
"""

import io
import json
import uuid
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import garminconnect
import jasil.runtime as jasil_runtime
import pytest
from sqlalchemy.orm import Session

import modules.garmin.rate_limit_store as garmin_rate_limit_store
import modules.garmin.token_utils as garmin_token_utils
import modules.users.users_integrations.integration_service as user_integrations_integration

#: The tokens of an account linked without any.
ACCESS_TOKEN = "access-1"
REFRESH_TOKEN = "refresh-1"

#: The start of an activity made without one.
DEFAULT_ACTIVITY_START = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)


class FakeGarminClient:
    """The low-level client of a Garmin Connect session: the token it holds and its refresh.

    Attributes:
        di_token: The access token.
        di_refresh_token: The refresh token.
        di_client_id: The client id the tokens were issued to.
    """

    def __init__(self, account: GarminAccount) -> None:
        """Build a client with no token.

        Args:
            account: The Garmin Connect account the client talks to.
        """
        self._account = account
        self.di_token: str | None = None
        self.di_refresh_token: str | None = None
        self.di_client_id: str | None = None

    def loads(self, token_json: str) -> None:
        """Restore the session from the JSON of a stored token.

        Args:
            token_json: The token as :func:`modules.garmin.token_utils.deserialize_garmin_token` builds it.

        Raises:
            GarminConnectAuthenticationError: When the account refuses stored sessions.
        """
        if self._account.restore_error is not None:
            raise self._account.restore_error
        token = json.loads(token_json)
        self.di_token = token["di_token"]
        self.di_refresh_token = token["di_refresh_token"]
        self.di_client_id = token["di_client_id"]

    def _token_expires_soon(self) -> bool:
        """Whether the access token is within the refresh window."""
        return self.di_token in self._account.expiring_tokens

    def _refresh_di_token(self) -> None:
        """Replace the tokens with a fresh pair.

        Raises:
            GarminConnectAuthenticationError: When the account refuses the refresh.
        """
        self._account.calls.append(("refresh_token", ()))
        if self._account.refresh_error is not None:
            raise self._account.refresh_error
        self._account.refreshes += 1
        self.di_token = f"access-refreshed-{self._account.refreshes}"
        self.di_refresh_token = f"refresh-refreshed-{self._account.refreshes}"


class FakeGarmin:
    """A ``garminconnect.Garmin`` client, answering from a :class:`GarminAccount`."""

    ActivityDownloadFormat = garminconnect.Garmin.ActivityDownloadFormat

    def __init__(
        self,
        account: GarminAccount,
        email: str | None = None,
        password: str | None = None,
        is_cn: bool = False,
        prompt_mfa: Callable[[], str] | None = None,
    ) -> None:
        """Build a client the way the module does.

        Args:
            account: The Garmin Connect account the client talks to.
            email: The username, for a login.
            password: The password, for a login.
            is_cn: Whether the client is for Garmin's China region.
            prompt_mfa: Asks the user for an MFA code.
        """
        self._account = account
        self.email = email
        self.password = password
        self.is_cn = is_cn
        self.prompt_mfa = prompt_mfa
        self.client = FakeGarminClient(account)
        account.clients.append(self)

    def login(self) -> None:
        """Log in as the account's login script says, which by default succeeds with a fresh token."""
        self._account.calls.append(("login", (self.email,)))
        if self._account.login_script is not None:
            self._account.login_script(self)
            return
        self.client.di_token = "login-access"
        self.client.di_refresh_token = "login-refresh"
        self.client.di_client_id = "login-client"

    def _answer(self, method: str, key: object, answer: Any) -> Any:
        """Record a call, raise the error scripted for it, or return the answer.

        Args:
            method: The client method called.
            key: What the call is about (a day, an activity id), matched by a scripted failure.
            answer: What the account answers when nothing is scripted to fail.

        Returns:
            The answer.
        """
        self._account.calls.append((method, (key,)))
        if self._account.on_call is not None:
            self._account.on_call(method)
        for scripted_method, scripted_key, error in self._account.failures:
            if scripted_method == method and scripted_key in (None, key):
                raise error
        return answer

    def get_activities_by_date(self, start: str, end: str) -> list[dict[str, Any]] | None:
        """List the activities of the account that started within the window."""
        if self._account.activities is None:
            return self._answer("get_activities_by_date", (start, end), None)
        listed = [a for a in self._account.activities if start <= a["startTimeLocal"][:10] <= end]
        return self._answer("get_activities_by_date", (start, end), listed)

    def get_activity(self, activity_id: str) -> dict[str, Any]:
        """Answer the detail of an activity, whose id the client takes as text."""
        return self._answer("get_activity", int(activity_id), self._account.activity_details.get(int(activity_id), {}))

    def get_activity_gear(self, activity_id: int) -> object:
        """Answer the gear used on an activity."""
        return self._answer("get_activity_gear", activity_id, self._account.activity_gear.get(activity_id, []))

    def download_activity(self, activity_id: int, dl_fmt: object = None) -> bytes:
        """Answer the archive of an activity's original file."""
        return self._answer("download_activity", activity_id, self._account.archives.get(activity_id, b""))

    def get_device_last_used(self) -> dict[str, Any]:
        """Answer the device the account last used."""
        return self._answer("get_device_last_used", None, {"userProfileNumber": 42})

    def get_gear(self, user_profile_number: int) -> object:
        """Answer the gear of the account."""
        return self._answer("get_gear", user_profile_number, self._account.gear)

    def get_body_composition(self, start: str, end: str) -> dict[str, Any]:
        """Answer the body composition entries of the window."""
        return self._answer("get_body_composition", (start, end), {"dateWeightList": self._account.body_composition})

    def get_daily_steps(self, start: str, end: str) -> list[dict[str, Any]]:
        """Answer the daily steps entries of the window."""
        return self._answer("get_daily_steps", (start, end), self._account.daily_steps)

    def get_sleep_data(self, day: str) -> dict[str, Any]:
        """Answer the sleep payload of a day, with a null-filled one for a day without sleep."""
        return self._answer("get_sleep_data", day, self._account.sleep.get(day, {"dailySleepDTO": {"id": None}}))


class GarminAccount:
    """One Garmin Connect account: what it holds, how it answers and what it refuses.

    Attributes:
        activities: The activity summaries ``get_activities_by_date`` lists, or ``None`` for an answer of none.
        archives: The archive ``download_activity`` answers, by activity id.
        activity_gear: The gear ``get_activity_gear`` answers, by activity id.
        activity_details: The detail ``get_activity`` answers, by activity id.
        gear: The gear ``get_gear`` answers.
        body_composition: The ``dateWeightList`` of the body composition.
        daily_steps: The daily steps entries.
        sleep: The sleep payload by ISO day.
        expiring_tokens: Access tokens the client reports as about to expire.
        restore_error: When set, restoring a stored session raises it.
        refresh_error: When set, refreshing a token raises it.
        login_script: When set, replaces the default login; it gets the client being logged in.
        on_call: Called with the method name before every data call is answered.
        failures: ``(method, key, error)`` triples; a call to the method (about the key, or any when ``None``) raises.
        calls: Every call the module made, as ``(method, arguments)``.
        clients: Every client the module built.
        refreshes: How many tokens were refreshed.
    """

    def __init__(self) -> None:
        """Build an account with nothing in it."""
        self.activities: list[dict[str, Any]] | None = []
        self.archives: dict[int, bytes] = {}
        self.activity_gear: dict[int, object] = {}
        self.activity_details: dict[int, dict[str, Any]] = {}
        self.gear: object = []
        self.body_composition: list[dict[str, Any]] = []
        self.daily_steps: list[dict[str, Any]] = []
        self.sleep: dict[str, dict[str, Any]] = {}
        self.expiring_tokens: set[str] = set()
        self.restore_error: Exception | None = None
        self.refresh_error: Exception | None = None
        self.login_script: Callable[[FakeGarmin], None] | None = None
        self.on_call: Callable[[str], None] | None = None
        self.failures: list[tuple[str, object, Exception]] = []
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.clients: list[FakeGarmin] = []
        self.refreshes = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> GarminAccount:
        """Make every ``garminconnect.Garmin`` the module builds a client of this account.

        Args:
            monkeypatch: The test's monkeypatch.

        Returns:
            The account.
        """

        def build(*args: Any, **kwargs: Any) -> FakeGarmin:
            return FakeGarmin(self, *args, **kwargs)

        monkeypatch.setattr(garminconnect, "Garmin", build)
        return self

    def fail(self, method: str, error: Exception, *, key: object = None) -> None:
        """Make a call raise an error.

        Args:
            method: The client method.
            error: What it raises.
            key: The activity id or day the failure is about, or ``None`` for every call to the method.
        """
        self.failures.append((method, key, error))

    def add_activity(self, activity_id: int, *, name: str = "Morning Run", start: datetime | None = None) -> None:
        """Hold an activity: its summary in the listing and its archive for download.

        Args:
            activity_id: The Garmin Connect activity id.
            name: The activity's name.
            start: When it started; :data:`DEFAULT_ACTIVITY_START` by default.
        """
        started = start or DEFAULT_ACTIVITY_START
        assert self.activities is not None
        self.activities.append(activity_summary(activity_id, name=name, start=started))
        self.archives[activity_id] = activity_archive(activity_id, start=started, name=name)

    def add_multisport_activity(
        self,
        activity_id: int,
        archive: bytes,
        child_ids: list[int],
        *,
        name: str = "Morning Multisport",
        start: datetime | None = None,
    ) -> None:
        """Hold a multisport activity as Garmin Connect lists it: one parent entry, its legs not listed.

        Args:
            activity_id: The parent's Garmin Connect activity id.
            archive: The archive ``download_activity`` answers for it.
            child_ids: The ids of its legs, in leg order, which ``get_activity`` answers.
            name: The activity's name.
            start: When it started; :data:`DEFAULT_ACTIVITY_START` by default.
        """
        assert self.activities is not None
        summary = activity_summary(activity_id, name=name, start=start or DEFAULT_ACTIVITY_START)
        self.activities.append({**summary, "isParent": True, "parentId": None})
        self.archives[activity_id] = archive
        self.activity_details[activity_id] = {"activityId": activity_id, "metadataDTO": {"childIds": child_ids}}

    def called(self, method: str) -> list[tuple[Any, ...]]:
        """List the arguments of every call to a method."""
        return [arguments for called, arguments in self.calls if called == method]


def activity_summary(activity_id: int, *, name: str = "Morning Run", start: datetime = DEFAULT_ACTIVITY_START) -> dict:
    """Build the summary Garmin Connect lists for an activity.

    Args:
        activity_id: The Garmin Connect activity id.
        name: The activity's name.
        start: When it started.

    Returns:
        The summary.
    """
    return {
        "activityId": activity_id,
        "activityName": name,
        "startTimeLocal": start.strftime("%Y-%m-%d %H:%M:%S"),
    }


def activity_archive(activity_id: int, *, start: datetime = DEFAULT_ACTIVITY_START, name: str = "Morning Run") -> bytes:
    """Build the archive Garmin Connect serves for an activity: a ZIP holding the original GPX file.

    Garmin names the file after the activity id, which is where the module reads the id from.

    Args:
        activity_id: The Garmin Connect activity id.
        start: When the track starts.
        name: The track's name.

    Returns:
        The ZIP's bytes.
    """
    return zip_of({f"{activity_id}_ACTIVITY.gpx": activity_gpx(start=start, name=name)})


def activity_gpx(*, start: datetime = DEFAULT_ACTIVITY_START, name: str = "Morning Run") -> bytes:
    """Build a small, valid GPX track.

    Args:
        start: When the track starts.
        name: The track's name.

    Returns:
        The GPX file's bytes.
    """
    points = "".join(
        f'<trkpt lat="{38.70 + step * 0.0005:.6f}" lon="{-9.14 + step * 0.0005:.6f}"><ele>{20 + step}</ele>'
        f"<time>{(start + timedelta(seconds=30 * step)).strftime('%Y-%m-%dT%H:%M:%SZ')}</time></trkpt>"
        for step in range(20)
    )
    gpx = (
        '<?xml version="1.0"?><gpx version="1.1" creator="garmin-test" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><name>{name}</name><trkseg>{points}</trkseg></trk></gpx>"
    )
    return gpx.encode()


#: A GPX file that passes validation but holds no track, so ingestion refuses it.
EMPTY_GPX = b'<?xml version="1.0"?><gpx version="1.1" creator="garmin-test" xmlns="http://www.topografix.com/GPX/1/1"/>'


def zip_of(members: dict[str, bytes]) -> bytes:
    """Build a ZIP of named members.

    Args:
        members: The member names and their bytes.

    Returns:
        The ZIP's bytes.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for member, data in members.items():
            archive.writestr(member, data)
    return buffer.getvalue()


def gear_payload(gear_uuid: str = "g-1", **overrides: object) -> dict[str, Any]:
    """Build one gear piece as Garmin Connect lists it.

    Args:
        gear_uuid: The Garmin Connect gear UUID.
        **overrides: Fields that replace the defaults of an active pair of shoes.

    Returns:
        The gear payload.
    """
    values: dict[str, object] = {
        "uuid": gear_uuid,
        "gearMakeName": "Nike",
        "gearModelName": "Pegasus",
        "displayName": "Road shoes",
        "customMakeModel": None,
        "gearTypeName": "Shoes",
        "gearStatusName": "active",
    }
    values.update(overrides)
    return values


def body_composition_entry(day: str, weight_g: float | None = 75000.0, **overrides: object) -> dict[str, Any]:
    """Build one body composition entry as Garmin Connect lists it.

    Args:
        day: The calendar date, ISO formatted.
        weight_g: The weight in grams, or ``None`` for a weigh-in without one.
        **overrides: Fields that replace the defaults.

    Returns:
        The entry.
    """
    values: dict[str, object] = {
        "calendarDate": day,
        "weight": weight_g,
        "bmi": 24.5,
        "bodyFat": 18.0,
        "bodyWater": 55.0,
        "boneMass": 3200.0,
        "muscleMass": 35000.0,
        "physiqueRating": None,
        "visceralFat": 5,
        "metabolicAge": 30,
    }
    values.update(overrides)
    return values


def steps_entry(day: str, steps: int | None = 8000) -> dict[str, Any]:
    """Build one daily steps entry as Garmin Connect lists it.

    Args:
        day: The calendar date, ISO formatted.
        steps: The step count, or ``None`` for a day without one.

    Returns:
        The entry.
    """
    return {"calendarDate": day, "totalSteps": steps}


def sleep_payload(day: str, **dto_overrides: object) -> dict[str, Any]:
    """Build a ``get_sleep_data`` payload for a day.

    Args:
        day: The calendar date, ISO formatted.
        **dto_overrides: Fields of ``dailySleepDTO`` that replace the defaults of an eight-hour night.

    Returns:
        The payload.
    """
    dto: dict[str, object] = {
        "id": 1759000000000,
        "calendarDate": day,
        "sleepTimeSeconds": 28800,
        "sleepStartTimestampGMT": 1759100000000,
        "sleepEndTimestampGMT": 1759128800000,
    }
    dto.update(dto_overrides)
    return {"dailySleepDTO": dto}


def link_garmin(
    db: Session,
    user_id: uuid.UUID,
    *,
    di_token: str = ACCESS_TOKEN,
    di_refresh_token: str = REFRESH_TOKEN,
    is_cn: bool = False,
    sync_gear: bool = False,
) -> dict[str, Any]:
    """Link Garmin Connect for a user through the module's own link path (flushed, not committed).

    The token is stored as a link stores it, its secrets encrypted with the configured key.

    Args:
        db: Database session.
        user_id: The user linking Garmin Connect.
        di_token: The access token.
        di_refresh_token: The refresh token.
        is_cn: Whether the account is on Garmin's China region.
        sync_gear: Whether the user's gear sync is on.

    Returns:
        The token as stored.
    """
    client = FakeGarminClient(GarminAccount())
    client.di_token = di_token
    client.di_refresh_token = di_refresh_token
    client.di_client_id = "client-1"
    token = garmin_token_utils.serialize_garmin_token(client, is_cn)
    user_integrations_integration.link_garminconnect_account(user_id, token, db)
    if sync_gear:
        user_integrations_integration.set_garminconnect_sync_gear(user_id, True, db)
    db.flush()
    return token


def rate_limits() -> garmin_rate_limit_store.GarminRateLimitStore:
    """Return the rate-limit store over the test platform's state, as the routes and workers build it."""
    return garmin_rate_limit_store.GarminRateLimitStore(jasil_runtime.get_state())
