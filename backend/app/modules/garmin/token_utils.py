"""Garmin Connect token storage format and session restore."""

import json

import garminconnect
import requests

import core.cryptography as core_cryptography
import core.logger as core_logger

logger = core_logger.get_logger(__name__)


def login_garminconnect_using_tokens(token: dict) -> garminconnect.Garmin | None:
    """Restore a Garmin Connect client from a stored token.

    Args:
        token: The token as stored by :func:`serialize_garmin_token`.

    Returns:
        An authenticated client, or ``None`` when Garmin Connect rejects the stored session.
    """
    try:
        # Tokens created before the China flag existed carry none; they are global accounts.
        is_cn = token.get("is_cn", False) if isinstance(token, dict) else False

        garmin = garminconnect.Garmin(is_cn=is_cn)

        # Restore session from stored DI tokens
        garmin.client.loads(deserialize_garmin_token(token))
        return garmin
    except (
        garminconnect.GarminConnectAuthenticationError,
        garminconnect.GarminConnectConnectionError,
        requests.exceptions.HTTPError,
    ) as err:
        logger.error(
            "There was an authentication error using Garmin Connect",
            exc_info=err,
        )
        return None


def refreshed_token(token: dict, client) -> dict | None:
    """Build the storable form of a client's token when the client has refreshed it.

    Args:
        token: The token as stored when the client was restored.
        client: The restored Garmin Connect client, which refreshes its token as it is used.

    Returns:
        The token to store, or ``None`` when the client still holds the stored one.
    """
    stored = json.loads(deserialize_garmin_token(token))
    if stored["di_token"] == client.di_token and stored["di_refresh_token"] == client.di_refresh_token:
        return None
    return serialize_garmin_token(client, token.get("is_cn", False))


def serialize_garmin_token(client, is_cn: bool = False) -> dict:
    """Build the storable form of a logged-in client's token, encrypting its secrets.

    Args:
        client: The logged-in Garmin Connect client.
        is_cn: Whether the account is on Garmin's China region.

    Returns:
        The token as stored on the user's integrations.

    Raises:
        Exception: Whatever encryption raised, after logging it.
    """
    try:
        return {
            "di_token": (core_cryptography.encrypt_token_fernet(client.di_token) if client.di_token else None),
            "di_refresh_token": (
                core_cryptography.encrypt_token_fernet(client.di_refresh_token) if client.di_refresh_token else None
            ),
            "di_client_id": client.di_client_id,
            "is_cn": is_cn,
        }
    except Exception as err:
        logger.error(
            "Error in serialize_garmin_token",
            exc_info=err,
        )
        raise err


def deserialize_garmin_token(data: dict) -> str:
    """Build the JSON a client loads from a stored token, decrypting its secrets.

    Args:
        data: The token as stored on the user's integrations.

    Returns:
        The token JSON for ``garminconnect`` to load.

    Raises:
        Exception: Whatever decryption raised, after logging it.
    """
    try:
        return json.dumps(
            {
                "di_token": (
                    core_cryptography.decrypt_token_fernet(data["di_token"]) if data.get("di_token") else None
                ),
                "di_refresh_token": (
                    core_cryptography.decrypt_token_fernet(data["di_refresh_token"])
                    if data.get("di_refresh_token")
                    else None
                ),
                "di_client_id": data.get("di_client_id"),
            }
        )
    except Exception as err:
        logger.error(
            "Error in deserialize_garmin_token",
            exc_info=err,
        )
        raise err
