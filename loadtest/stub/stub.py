"""Stub providers for the load-test stack: map tiles, Nominatim and Strava behind one throwaway HTTPS certificate.

Runs inside the Endurain image (it needs only the standard library and ``cryptography``) and answers, over https on
port 443, for ``tile.openstreetmap.org``, ``nominatim.openstreetmap.org`` and ``www.strava.com``; ``compose.yaml`` points
those names at this container. At start it makes a CA and a server certificate for those names under ``/pki`` and
writes ``ca-bundle.pem`` (the system CAs plus the stub's CA) that the application trusts through ``SSL_CERT_FILE`` and
``REQUESTS_CA_BUNDLE``.

Strava answers what a sync and an unlink use (token refresh, athlete, activities list, activity, streams, laps, gear,
deauthorization) with deterministic data: each Strava application (client id) has one activity per 6 hours, with a
stable id, so repeated syncs meet the same activities and a duplicate would show. A fixed-window rate limit per
client id answers ``429`` with Strava's rate-limit headers; it is off by default and set through the admin API.

The admin API (plain http, port 8081, published on 127.0.0.1:18081)::

    GET  /health
    GET  /stats                       counts of what was served, and the Strava limit in force
    POST /strava/limit  {"limit": 40, "window": 900, "reject_for": 30}
        limit, window   at most ``limit`` Strava API calls per client id per ``window`` seconds (0 = unlimited)
        reject_for      answer 429 to every Strava call for this many seconds, whatever the counters say
    POST /reset                       clear the counters and the limit
"""

import datetime as dt
import json
import ssl
import struct
import threading
import time
import zlib
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

PKI = Path("/pki")
HOSTS = ("tile.openstreetmap.org", "nominatim.openstreetmap.org", "www.strava.com")
SYSTEM_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")

#: Seconds between two activities of one Strava application, and how long each lasts.
SLOT_SECONDS = 6 * 3600
ACTIVITY_SECONDS = 3600
#: Offset that keeps a Strava activity off the seeded activities' start times (6, 10, 14 and 18 o'clock).
SLOT_OFFSET_SECONDS = 1800
STREAM_POINTS = 60
#: Strava's daily limit is reported but never reached by the stub.
DAILY_LIMIT = 1000

_lock = threading.RLock()
_stats: Counter[str] = Counter()
_limit = {"limit": 0, "window": 900, "reject_until": 0.0}
_windows: dict[str, list[float]] = {}  # client id -> [window start, calls in it]


# ------------------------------------------------------------------------------------------------------------------
# Certificates
# ------------------------------------------------------------------------------------------------------------------


def _count(key: str) -> None:
    with _lock:
        _stats[key] += 1


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def make_pki() -> None:
    """Write the CA, the server certificate and key, and the trust bundle the application uses under ``/pki``."""
    PKI.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = _name("Endurain load-test stub CA")
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    server = (
        x509.CertificateBuilder()
        .subject_name(_name(HOSTS[0]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host) for host in HOSTS]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca.public_bytes(serialization.Encoding.PEM)
    (PKI / "server.pem").write_bytes(server.public_bytes(serialization.Encoding.PEM) + ca_pem)
    (PKI / "server.key").write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    (PKI / "ca.pem").write_bytes(ca_pem)
    system = SYSTEM_CA_BUNDLE.read_bytes() if SYSTEM_CA_BUNDLE.exists() else b""
    bundle = PKI / "ca-bundle.pem"
    bundle.write_bytes(system + b"\n" + ca_pem)
    for path in PKI.iterdir():
        path.chmod(0o644)  # the application runs as another user and only reads the bundle


# ------------------------------------------------------------------------------------------------------------------
# Payloads
# ------------------------------------------------------------------------------------------------------------------


def _png(size: int = 256) -> bytes:
    """A solid light-grey PNG, the answer for every map tile."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + b"\xe6\xe6\xe6" * size
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * size, 6))
        + chunk(b"IEND", b"")
    )


TILE = _png()

NOMINATIM = {
    "place_id": 1,
    "licence": "load-test stub",
    "osm_type": "way",
    "osm_id": 1,
    "category": "highway",
    "type": "residential",
    "name": "Avenida da Liberdade",
    "display_name": "Avenida da Liberdade, Santo Antonio, Lisbon, Lisboa, 1250-096, Portugal",
    "address": {
        "road": "Avenida da Liberdade",
        "suburb": "Santo Antonio",
        "city": "Lisbon",
        "state": "Lisboa",
        "postcode": "1250-096",
        "country": "Portugal",
        "country_code": "pt",
    },
}


def _client_id(token: str) -> str | None:
    """The Strava application an access token of the load test belongs to (``lt-<client id>-...``)."""
    parts = token.split("-")
    return parts[1] if len(parts) >= 3 and parts[0] == "lt" and parts[1].isdigit() else None


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slot_start(slot: int) -> int:
    return slot * SLOT_SECONDS + SLOT_OFFSET_SECONDS


def _activity_id(client_id: str, slot: int) -> int:
    return int(client_id) * 10_000_000_000 + slot


def _parse_activity_id(activity_id: int) -> tuple[str, int]:
    client, slot = divmod(activity_id, 10_000_000_000)
    return str(client), slot


def _epoch(value: str | None, default: float) -> float:
    """A window bound as Strava clients send it: epoch seconds or an ISO date."""
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return dt.datetime.fromisoformat(value).timestamp()


def summary_activity(client_id: str, slot: int) -> dict:
    start = _slot_start(slot)
    return {
        "id": _activity_id(client_id, slot),
        "name": f"Stub run {slot}",
        "distance": 10000.0,
        "moving_time": ACTIVITY_SECONDS - 100,
        "elapsed_time": ACTIVITY_SECONDS,
        "total_elevation_gain": 50.0,
        "sport_type": "Run",
        "start_date": _iso(start),
        "start_date_local": _iso(start),
        "timezone": "(GMT+00:00) UTC",
        "average_speed": 2.78,
        "max_speed": 5.0,
        "gear_id": None,
    }


def detailed_activity(client_id: str, slot: int) -> dict:
    return {
        **summary_activity(client_id, slot),
        "average_heartrate": 145.0,
        "max_heartrate": 175.0,
        "calories": 500.0,
        "description": "Stub loop",
        "start_latlng": [38.72, -9.14],
    }


def streams(client_id: str, slot: int) -> dict:
    """The streams of an activity: a small loop with heart rate, altitude and speed."""
    count = STREAM_POINTS
    values = {
        "time": list(range(count)),
        "latlng": [[round(38.72 + 0.0005 * i, 6), round(-9.14 + 0.0004 * i, 6)] for i in range(count)],
        "altitude": [round(20 + (i % 10), 1) for i in range(count)],
        "heartrate": [130 + (i % 30) for i in range(count)],
        "velocity_smooth": [round(2.5 + (i % 5) / 10, 2) for i in range(count)],
    }
    return {
        name: {"data": data, "series_type": "time", "original_size": count, "resolution": "high"}
        for name, data in values.items()
    }


def laps(client_id: str, slot: int) -> list[dict]:
    start = _iso(_slot_start(slot))
    half = STREAM_POINTS // 2
    return [
        {
            "id": _activity_id(client_id, slot) * 10 + index,
            "lap_index": index,
            "name": f"Lap {index}",
            "start_index": (index - 1) * half,
            "end_index": index * half - 1,
            "start_date": start,
            "start_date_local": start,
            "elapsed_time": half,
            "moving_time": half,
            "distance": 5000.0,
            "average_speed": 3.0,
            "max_speed": 4.0,
            "average_heartrate": 140.0,
            "max_heartrate": 150.0,
        }
        for index in (1, 2)
    ]


# ------------------------------------------------------------------------------------------------------------------
# Strava rate limit
# ------------------------------------------------------------------------------------------------------------------


def _strava_limit_check(client_id: str) -> dict[str, str] | None:
    """Count a Strava call; return the headers of a 429 when it is over the limit, else None."""
    now = time.time()
    with _lock:
        rejecting = now < _limit["reject_until"]
        used = 0
        over = rejecting
        if _limit["limit"] > 0:
            window = _windows.get(client_id)
            if window is None or now - window[0] >= _limit["window"]:
                window = _windows[client_id] = [now, 0]
            window[1] += 1
            used = window[1]
            over = over or used > _limit["limit"]
        if over:
            _count("strava_429")
        limit = _limit["limit"] or 100
    if not over:
        return None
    # The short-term pair is exhausted, the daily one is not: the application backs off for 15 minutes, not until UTC midnight.
    return {
        "X-RateLimit-Limit": f"{limit},{DAILY_LIMIT}",
        "X-RateLimit-Usage": f"{max(used, limit + 1)},{DAILY_LIMIT // 10}",
        "X-ReadRateLimit-Limit": f"{limit},{DAILY_LIMIT}",
        "X-ReadRateLimit-Usage": f"{max(used, limit + 1)},{DAILY_LIMIT // 10}",
    }


# ------------------------------------------------------------------------------------------------------------------
# HTTP
# ------------------------------------------------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "stub"
    #: Whether this handler serves the admin API rather than the providers.
    admin = False

    def log_message(self, format: str, *args) -> None:
        pass

    def _send(self, status: int, body: bytes = b"", content_type: str = "application/json", headers=None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload, headers=None) -> None:
        self._send(status, json.dumps(payload).encode(), headers=headers)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def do_PUT(self) -> None:
        self._route("PUT")

    def _route(self, method: str) -> None:
        url = urlsplit(self.path)
        if self.admin:
            return self._admin(method, url.path)
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host == "www.strava.com":
            return self._strava(method, url)
        if host == "nominatim.openstreetmap.org":
            _count("nominatim")
            return self._json(200, NOMINATIM)
        _count("tile")
        self._send(200, TILE, "image/png", {"Cache-Control": "max-age=3600"})

    # -- admin --------------------------------------------------------------------------------------------------

    def _admin(self, method: str, path: str) -> None:
        if path == "/health":
            return self._json(200, {"status": "ok"})
        if path == "/stats":
            with _lock:
                return self._json(200, {"served": dict(_stats), "strava_limit": dict(_limit), "now": time.time()})
        if method == "POST" and path == "/strava/limit":
            body = json.loads(self._body() or b"{}")
            with _lock:
                for key in ("limit", "window"):
                    if key in body:
                        _limit[key] = int(body[key])
                if "reject_for" in body:
                    _limit["reject_until"] = time.time() + float(body["reject_for"])
                _windows.clear()
            return self._json(200, dict(_limit))
        if method == "POST" and path == "/reset":
            with _lock:
                _stats.clear()
                _windows.clear()
                _limit.update(limit=0, window=900, reject_until=0.0)
            return self._json(200, {})
        self._json(404, {"message": "not found"})

    # -- strava -------------------------------------------------------------------------------------------------

    def _strava(self, method: str, url) -> None:
        path = url.path.removeprefix("/api/v3")
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        if path == "/oauth/token" and method == "POST":
            form = {key: values[0] for key, values in parse_qs(self._body().decode()).items()}
            client_id = form.get("client_id", "")
            if (blocked := _strava_limit_check(client_id)) is not None:
                return self._json(429, {"message": "Rate Limit Exceeded", "errors": []}, blocked)
            _count("strava_token")
            now = int(time.time())
            return self._json(
                200,
                {
                    "token_type": "Bearer",
                    "access_token": f"lt-{client_id}-access-{now}",
                    "refresh_token": f"lt-{client_id}-refresh-{now}",
                    "expires_at": now + 6 * 3600,
                    "expires_in": 6 * 3600,
                },
            )
        if path == "/oauth/deauthorize" and method == "POST":  # the unlink of an account revokes the grant
            _count("strava_deauthorize")
            return self._json(200, {"access_token": "revoked"})
        auth = self.headers.get("Authorization", "")
        client_id = _client_id(auth.removeprefix("Bearer ").strip()) if auth.startswith("Bearer ") else None
        if client_id is None:
            return self._json(
                401,
                {
                    "message": "Authorization Error",
                    "errors": [{"resource": "Athlete", "field": "access_token", "code": "invalid"}],
                },
            )
        if (blocked := _strava_limit_check(client_id)) is not None:
            return self._json(
                429,
                {
                    "message": "Rate Limit Exceeded",
                    "errors": [{"resource": "Application", "field": "rate limit", "code": "exceeded"}],
                },
                blocked,
            )
        usage = {"X-RateLimit-Limit": f"{_limit['limit'] or 100},{DAILY_LIMIT}", "X-RateLimit-Usage": "1,1"}

        if path == "/athlete":
            _count("strava_athlete")
            return self._json(
                200,
                {
                    "id": int(client_id),
                    "firstname": "Stub",
                    "lastname": "Athlete",
                    "bikes": [{"id": f"b{client_id}", "name": "listed", "primary": True, "distance": 0}],
                    "shoes": [{"id": f"s{client_id}", "name": "listed", "primary": True, "distance": 0}],
                },
                usage,
            )
        if path == "/athlete/activities":
            _count("strava_activities")
            now = time.time()
            after, before = _epoch(query.get("after"), 0), _epoch(query.get("before"), now)
            if int(query.get("page", "1")) > 1:
                return self._json(200, [], usage)
            slots = range(int(max(after, 0) // SLOT_SECONDS) - 1, int(before // SLOT_SECONDS) + 1)
            found = [
                summary_activity(client_id, slot) for slot in slots if after <= _slot_start(slot) <= min(before, now)
            ]
            return self._json(200, found, usage)
        if path.startswith("/gear/"):
            _count("strava_gear")
            gear_id = path.removeprefix("/gear/")
            return self._json(
                200,
                {
                    "id": gear_id,
                    "name": "Stub gear",
                    "brand_name": "Stub",
                    "model_name": "One",
                    "primary": False,
                    "distance": 1000.0,
                    "resource_state": 3,
                },
                usage,
            )
        if path.startswith("/activities/"):
            parts = path.removeprefix("/activities/").split("/")
            try:
                owner, slot = _parse_activity_id(int(parts[0]))
            except ValueError:
                return self._json(404, {"message": "Record Not Found"}, usage)
            if owner != client_id:
                return self._json(404, {"message": "Record Not Found"}, usage)
            if len(parts) == 1:
                _count("strava_activity")
                return self._json(200, detailed_activity(client_id, slot), usage)
            if parts[1] == "streams":
                _count("strava_streams")
                return self._json(200, streams(client_id, slot), usage)
            if parts[1] == "laps":
                _count("strava_laps")
                return self._json(200, laps(client_id, slot), usage)
        _count("strava_unrouted")
        self._json(404, {"message": "Record Not Found"}, usage)


class AdminHandler(Handler):
    admin = True


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128


def main() -> None:
    make_pki()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(PKI / "server.pem", PKI / "server.key")
    https = Server(("0.0.0.0", 443), Handler)
    https.socket = context.wrap_socket(https.socket, server_side=True)
    threading.Thread(target=https.serve_forever, daemon=True).start()
    print("stub: https on 443 for", ", ".join(HOSTS), flush=True)
    Server(("0.0.0.0", 8081), AdminHandler).serve_forever()


if __name__ == "__main__":
    main()
