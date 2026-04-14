"""OneLapFit utility functions for API interactions and token management."""

import base64
import hashlib
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.logger as core_logger
import core.config as core_config

import users.users_integrations.crud as user_integrations_crud
import users.users_integrations.models as user_integrations_models

# OneLapFit API base URLs
ONELAPFIT_API_BASE = "https://api-fitness.rfsvr.com/api/v1/app"
ONELAPFIT_ACCOUNT_API_BASE = "https://api-fitness.rfsvr.com/api/account/v1"

# API Key for request signing
ONELAPFIT_API_KEY = "6b14dcd729a8234487734f50c6335995"


def generate_nonce() -> str:
    """
    Generate a random nonce for request signing.
    6 random bytes → Base64 encoded.

    Returns:
        Base64-encoded nonce string (not URL-encoded)
    """
    random_bytes = secrets.token_bytes(6)
    nonce_base64 = base64.b64encode(random_bytes).decode('ascii')
    return nonce_base64


def create_signature(path: str, params: dict) -> str:
    """
    Create MD5 signature for API request.

    Args:
        path: API path (e.g., "/api/v1/app/login")
        params: Dictionary of query parameters (excluding nonce and timestamp which are added here)

    Returns:
        MD5 signature string
    """
    # Sort params alphabetically by key
    sorted_keys = sorted(params.keys())

    # Build query string
    query_parts = []
    for key in sorted_keys:
        value = params[key]
        query_parts.append(f"{key}={value}")

    query_string = "&".join(query_parts)

    # Build sign string: path?query_string&key=api_key
    sign_string = f"{path}?{query_string}&key={ONELAPFIT_API_KEY}"

    # MD5 hash
    return hashlib.md5(sign_string.encode('utf-8')).hexdigest()


async def get_region_code(email: str) -> str:
    """
    Fetch region code from OneLapFit API.

    Args:
        email: User email address

    Returns:
        Region code string

    Raises:
        HTTPException: If region fetch fails
    """
    try:
        path = "/api/account/v1/user/region"
        nonce = generate_nonce()
        timestamp = int(time.time())

        # Build params for signing (email, nonce, timestamp) - use raw nonce for signing
        params = {
            "email": email,
            "nonce": nonce,
            "timestamp": str(timestamp)
        }

        # Create signature
        signature = create_signature(path, params)

        # URL-encode the nonce for the header (matching Postman's encodeURIComponent)
        nonce_encoded = urllib.parse.quote(nonce, safe='')

        # Send nonce, timestamp, sign as HTTP headers; only data params in query string
        full_url = f"{ONELAPFIT_ACCOUNT_API_BASE}/user/region?email={urllib.parse.quote(email, safe='')}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                full_url,
                headers={
                    "nonce": nonce_encoded,
                    "timestamp": str(timestamp),
                    "sign": signature,
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                core_logger.print_to_log(
                    f"OneLapFit region fetch failed with status {response.status_code}: {response.text}",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to fetch region code from OneLapFit",
                )

            data = response.json()

            if data.get("code") != 200:
                core_logger.print_to_log(
                    f"OneLapFit region API returned error: {data.get('error')}",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Failed to fetch region code: {data.get('error')}",
                )

            region_code = data.get("data", {}).get("region")
            if not region_code:
                core_logger.print_to_log(
                    "OneLapFit region: No region code in response data",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No region code returned from OneLapFit",
                )

            # Convert region to string if it's a number
            return str(region_code)
    except HTTPException:
        raise
    except httpx.RequestError as err:
        core_logger.print_to_log(
            f"OneLapFit region API request error: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to connect to OneLapFit service",
        ) from err


def hash_password(password: str) -> str:
    """Hash password using MD5 (as required by OneLapFit API)."""
    return hashlib.md5(password.encode()).hexdigest().lower()


async def login_onelapfit(email: str, password: str) -> tuple[str, str]:
    """
    Login to OneLapFit and retrieve access token.

    Args:
        email: User email address
        password: User password (will be MD5 hashed)

    Returns:
        Tuple of (access_token, region_code)

    Raises:
        HTTPException: If login fails
    """
    try:
        # First, get the region code
        region_code = await get_region_code(email)

        hashed_password = hash_password(password)

        # Create signature for login request
        path = "/api/v1/app/login"
        nonce = generate_nonce()
        timestamp = int(time.time())

        params = {
            "nonce": nonce,
            "timestamp": str(timestamp)
        }

        signature = create_signature(path, params)

        # URL-encode the nonce for the header (matching Postman's encodeURIComponent)
        nonce_encoded = urllib.parse.quote(nonce, safe='')

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ONELAPFIT_API_BASE}/login",
                headers={
                    "onelap-region": region_code,
                    "nonce": nonce_encoded,
                    "timestamp": str(timestamp),
                    "sign": signature,
                },
                json={
                    "account": email,
                    "password": hashed_password,
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                core_logger.print_to_log(
                    f"OneLapFit login failed with status {response.status_code}: {response.text}",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="OneLapFit login failed. Check your credentials.",
                )

            data = response.json()

            if data.get("code") != 200:
                core_logger.print_to_log(
                    f"OneLapFit login API returned error: {data.get('error')}",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"OneLapFit login failed: {data.get('error')}",
                )

            token = data.get("data", {}).get("token")
            if not token:
                core_logger.print_to_log(
                    "OneLapFit login: No token in response data",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No token returned from OneLapFit",
                )

            core_logger.print_to_log(
                f"OneLapFit login successful for email {email}"
            )
            return token, region_code
    except HTTPException:
        raise
    except httpx.RequestError as err:
        core_logger.print_to_log(
            f"OneLapFit API request error: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to connect to OneLapFit service",
        ) from err


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_models.UsersIntegrations | None:
    """
    Fetch user integrations and validate OneLapFit token exists.

    Args:
        user_id: User ID
        db: Database session

    Returns:
        User integrations object or None if token is invalid/missing

    Raises:
        HTTPException: If user integrations not found
    """
    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
        user_id, db
    )

    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User information not found",
        )

    if user_integrations.onelapfit_token is None:
        return None

    return user_integrations


async def fetch_onelapfit_activities(
    token: str,
    start_time: int,
    end_time: int,
    region: str = None,
    page: int = 0,
) -> dict:
    """
    Fetch riding list from OneLapFit API.

    Args:
        token: OneLapFit access token
        start_time: Unix timestamp for start date
        end_time: Unix timestamp for end date
        region: Region code (required by API for routing)
        page: Page number for pagination (0-indexed)

    Returns:
        Response data from OneLapFit API

    Raises:
        HTTPException: If API call fails
    """
    try:
        # Create signature for activities request
        path = "/api/v1/app/record/riding/list"
        nonce = generate_nonce()
        timestamp = int(time.time())

        # Build params for signing (only start_time, end_time, nonce, timestamp)
        params = {
            "start_time": str(start_time),
            "end_time": str(end_time),
            "nonce": nonce,
            "timestamp": str(timestamp)
        }

        signature = create_signature(path, params)

        # URL-encode the nonce for the header (matching Postman's encodeURIComponent)
        nonce_encoded = urllib.parse.quote(nonce, safe='')

        activities_url = f"{ONELAPFIT_API_BASE}/record/riding/list?start_time={start_time}&end_time={end_time}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                activities_url,
                headers={
                    "Authorization": token,
                    "nonce": nonce_encoded,
                    "timestamp": str(timestamp),
                    "sign": signature,
                    **({"onelap-region": region} if region else {}),
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                core_logger.print_to_log(
                    f"OneLapFit activities fetch failed with status {response.status_code}: {response.text}",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_424_FAILED_DEPENDENCY,
                    detail="Unable to fetch OneLapFit activities",
                )

            data = response.json()

            if data.get("code") != 200:
                core_logger.print_to_log(
                    f"OneLapFit activities API returned error: {data.get('error')}",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_424_FAILED_DEPENDENCY,
                    detail=f"OneLapFit API error: {data.get('error')}",
                )

            return data.get("data", {})
    except HTTPException:
        raise
    except httpx.RequestError as err:
        core_logger.print_to_log(
            f"OneLapFit activities fetch request error: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to connect to OneLapFit service",
        ) from err


async def fetch_onelapfit_overview(
    token: str,
    start_time: int = 0,
    end_time: int = None,
    region: str = None,
) -> dict:
    """
    Fetch riding overview from OneLapFit API.

    Args:
        token: OneLapFit access token
        start_time: Unix timestamp for start date (default: 0)
        end_time: Unix timestamp for end date (default: current time)
        region: Region code (required by API for routing)

    Returns:
        Response data from OneLapFit API
    """
    if end_time is None:
        end_time = int(datetime.now(timezone.utc).timestamp())

    try:
        # Create signature for overview request
        path = "/api/v1/app/record/riding/overview"
        nonce = generate_nonce()
        timestamp = int(time.time())

        # Build params for signing
        params = {
            "start_time": str(start_time),
            "end_time": str(end_time),
            "source": "table",
            "data_type": "all",
            "nonce": nonce,
            "timestamp": str(timestamp)
        }

        signature = create_signature(path, params)

        # URL-encode the nonce for the header (matching Postman's encodeURIComponent)
        nonce_encoded = urllib.parse.quote(nonce, safe='')

        overview_url = f"{ONELAPFIT_API_BASE}/record/riding/overview?start_time={start_time}&end_time={end_time}&source=table&data_type=all"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                overview_url,
                headers={
                    "Authorization": token,
                    "nonce": nonce_encoded,
                    "timestamp": str(timestamp),
                    "sign": signature,
                    **({"onelap-region": region} if region else {}),
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_424_FAILED_DEPENDENCY,
                    detail="Unable to fetch OneLapFit overview",
                )

            data = response.json()
            if data.get("code") != 200:
                raise HTTPException(
                    status_code=status.HTTP_424_FAILED_DEPENDENCY,
                    detail=f"OneLapFit API error: {data.get('error')}",
                )

            return data.get("data", {})
    except HTTPException:
        raise
    except httpx.RequestError as err:
        core_logger.print_to_log(
            f"OneLapFit overview fetch request error: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to connect to OneLapFit service",
        ) from err


async def download_fit_file(url: str) -> bytes:
    """
    Download FIT file from OneLapFit URL.

    Args:
        url: Full URL to FIT file

    Returns:
        File content as bytes

    Raises:
        HTTPException: If download fails
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=60.0)

            if response.status_code != 200:
                core_logger.print_to_log(
                    f"FIT file download failed with status {response.status_code}",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_424_FAILED_DEPENDENCY,
                    detail="Unable to download FIT file",
                )

            return response.content
    except HTTPException:
        raise
    except httpx.RequestError as err:
        core_logger.print_to_log(
            f"FIT file download request error: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to download FIT file",
        ) from err
