import random
import json
import base64
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
import secrets
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Request
from authlib.integrations.httpx_client import AsyncOAuth2Client

import core.config as core_config
import core.cryptography as core_cryptography
import core.logger as core_logger
import identity_providers.models as idp_models
import users.user.crud as users_crud
import users.user.schema as users_schema
import users.user.models as users_models
import users.user.utils as users_utils
import users.user_identity_providers.crud as user_idp_crud
import session.password_hasher as session_password_hasher
import server_settings.schema as server_settings_schema


class IdentityProviderService:

    def __init__(self):
        """
        Initializes the service with in-memory caches for discovery data and their expiry times,
        sets the cache time-to-live (TTL) to 1 hour, and prepares an optional asynchronous HTTP client.
        """
        self._discovery_cache: Dict[int, Dict[str, Any]] = {}
        self._cache_expiry: Dict[int, datetime] = {}
        self._cache_ttl = timedelta(hours=1)
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Asynchronously retrieves or creates an instance of httpx.AsyncClient for making HTTP requests.

        If the HTTP client does not already exist, it initializes a new AsyncClient with a timeout of 10 seconds
        and connection limits (maximum 5 keep-alive connections and 10 total connections). Returns the client instance.

        Returns:
            httpx.AsyncClient: The HTTP client instance for asynchronous requests.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=10.0,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                follow_redirects=True,
                headers={
                    "User-Agent": "Endurain/0.16.0 (OIDC Client)",
                    "Accept": "application/json",
                },
            )
        return self._http_client

    async def get_oidc_configuration(
        self, idp: idp_models.IdentityProvider
    ) -> Dict[str, Any] | None:
        """
        Retrieves the OpenID Connect (OIDC) discovery configuration for a given identity provider.
        This method attempts to fetch the OIDC configuration from the provider's well-known discovery endpoint.
        It uses an in-memory cache to avoid redundant network requests and respects a cache TTL (time-to-live).
        If the configuration is cached and not expired, it is returned directly from the cache.
        Otherwise, it fetches the configuration over HTTP, caches it, and returns the result.
        Args:
            idp (idp_models.IdentityProvider): The identity provider instance containing the issuer URL and unique ID.
        Returns:
            Dict[str, Any] | None: The OIDC discovery configuration as a dictionary if successful, or None if fetching fails
            or the issuer URL is not provided.
        Raises:
            Does not raise exceptions directly; logs errors and returns None on failure.
        """
        if not idp.issuer_url:
            return None

        # Check cache
        if idp.id in self._discovery_cache:
            if datetime.now(timezone.utc) < self._cache_expiry.get(
                idp.id, datetime.min.replace(tzinfo=timezone.utc)
            ):
                return self._discovery_cache[idp.id]

        try:
            # Construct the discovery URL
            discovery_url = (
                f"{idp.issuer_url.rstrip('/')}/.well-known/openid-configuration"
            )

            # Fetch the configuration
            client = await self._get_http_client()
            response = await client.get(discovery_url)

            response.raise_for_status()
            config = response.json()

            # Cache the configuration
            self._discovery_cache[idp.id] = config
            self._cache_expiry[idp.id] = datetime.now(timezone.utc) + self._cache_ttl

            return config
        except httpx.HTTPStatusError as err:
            core_logger.print_to_log(
                f"HTTP error fetching OIDC discovery for {idp.name}: {err.response.status_code} - {err.response.text}",
                "warning",
            )
            return None
        except httpx.ConnectError as err:
            core_logger.print_to_log(
                f"Connection error fetching OIDC discovery for {idp.name}. "
                f"URL: {discovery_url}. Error: {err}. "
                f"Check if the service is reachable and not using 'localhost' in Docker.",
                "error",
            )
            return None
        except httpx.RequestError as err:
            core_logger.print_to_log(
                f"Request error fetching OIDC discovery for {idp.name}. "
                f"URL: {discovery_url}. Error: {err}",
                "warning",
            )
            return None
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to fetch OIDC discovery for {idp.name}: {err}", "warning"
            )
            return None

    def _get_redirect_uri(self, idp_slug: str) -> str:
        """
        Generates the redirect URI for a given identity provider slug.

        Args:
            idp_slug (str): The slug identifier for the identity provider.

        Returns:
            str: The complete redirect URI for the specified identity provider.
        """
        base_url = core_config.ENDURAIN_HOST
        return f"{base_url}/api/v1/public/idp/callback/{idp_slug}"

    async def initiate_login(
        self, idp: idp_models.IdentityProvider, request: Request, db: Session
    ) -> str:
        """
        Initiates the OAuth2/OIDC login process for the given identity provider.

        This method prepares the authorization URL for the user to authenticate with the specified
        identity provider (IdP). It handles endpoint discovery, state and nonce generation for security,
        and session storage of relevant OAuth parameters.

        Args:
            idp (idp_models.IdentityProvider): The identity provider instance containing configuration details.
            request (Request): The current HTTP request object, used to store session data.
            db (Session): The database session (not directly used in this method).

        Returns:
            str: The authorization URL to which the user should be redirected to initiate login.

        Raises:
            HTTPException: If the identity provider is not properly configured or if an error occurs during initiation.
        """
        try:
            # Decrypt credentials
            #client_id = core_cryptography.decrypt_token_fernet(idp.client_id)
            client_id = idp.client_id
            # client_secret = core_cryptography.decrypt_token_fernet(idp.client_secret)

            # Get endpoints
            authorization_endpoint = idp.authorization_endpoint

            # Try OIDC discovery if issuer URL is provided
            if not authorization_endpoint and idp.issuer_url:
                config = await self.get_oidc_configuration(idp)
                if config:
                    authorization_endpoint = config.get("authorization_endpoint")

            if not authorization_endpoint:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Identity provider not properly configured",
                )

            # Generate state and nonce for security
            state = secrets.token_urlsafe(32)
            nonce = secrets.token_urlsafe(32)

            # Store in session (using SessionMiddleware)
            request.session[f"oauth_state_{idp.id}"] = state
            request.session[f"oauth_nonce_{idp.id}"] = nonce
            request.session["oauth_idp_id"] = idp.id

            # Build authorization URL
            redirect_uri = self._get_redirect_uri(idp.slug)
            scopes = idp.scopes or "openid profile email"

            client = AsyncOAuth2Client(
                client_id=client_id, redirect_uri=redirect_uri, scope=scopes
            )

            authorization_url, _ = client.create_authorization_url(
                authorization_endpoint, state=state, nonce=nonce
            )

            return authorization_url

        except HTTPException:
            raise
        except Exception as err:
            core_logger.print_to_log(
                f"Error initiating OAuth login for IdP {idp.name}: {err}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate SSO login",
            ) from err

    async def handle_callback(
        self,
        idp: idp_models.IdentityProvider,
        code: str,
        state: str,
        request: Request,
        password_hasher: session_password_hasher.PasswordHasher,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Handles the OAuth2/OIDC callback from an external Identity Provider (IdP).

        This method verifies the state parameter to prevent CSRF attacks, exchanges the authorization code
        for tokens, retrieves user information from the IdP, and finds or creates a corresponding user in the system.

        Args:
            idp (idp_models.IdentityProvider): The identity provider configuration object.
            code (str): The authorization code returned by the IdP.
            state (str): The state parameter returned by the IdP for CSRF protection.
            request (Request): The incoming HTTP request object.
            password_hasher (session_password_hasher.PasswordHasher): The password hasher instance.
            db (Session): The database session for user lookup/creation.

        Returns:
            Dict[str, Any]: A dictionary containing the authenticated user, token data, and userinfo.

        Raises:
            HTTPException: If the state is invalid, the IdP is misconfigured, user identifier is missing,
                           or any other error occurs during the callback handling process.
        """
        try:
            # Verify state
            stored_state = request.session.get(f"oauth_state_{idp.id}")
            if not stored_state or state != stored_state:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid state parameter",
                )

            # Decrypt credentials
            client_id = core_cryptography.decrypt_token_fernet(idp.client_id)
            client_secret = core_cryptography.decrypt_token_fernet(idp.client_secret)

            # Get token endpoint
            token_endpoint = idp.token_endpoint
            userinfo_endpoint = idp.userinfo_endpoint

            # Try OIDC discovery if needed
            if (not token_endpoint or not userinfo_endpoint) and idp.issuer_url:
                config = await self.get_oidc_configuration(idp)
                if config:
                    token_endpoint = token_endpoint or config.get("token_endpoint")
                    userinfo_endpoint = userinfo_endpoint or config.get(
                        "userinfo_endpoint"
                    )

            if not token_endpoint:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Identity provider not properly configured",
                )

            # Exchange code for tokens
            redirect_uri = self._get_redirect_uri(idp.slug)

            client = AsyncOAuth2Client(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )

            token_response = await client.fetch_token(
                token_endpoint, grant_type="authorization_code", code=code
            )

            # Get user information
            userinfo = await self._get_userinfo(
                token_response, userinfo_endpoint, client
            )

            # Extract subject (unique user identifier)
            subject = userinfo.get("sub") or userinfo.get("id")
            if not subject:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="IdP did not provide user identifier",
                )

            # Find or create user
            user = await self._find_or_create_user(
                idp, subject, userinfo, password_hasher, db
            )

            # Clean up session data after successful authentication
            request.session.pop(f"oauth_state_{idp.id}", None)
            request.session.pop(f"oauth_nonce_{idp.id}", None)
            request.session.pop("oauth_idp_id", None)

            core_logger.print_to_log(
                f"User {user.username} authenticated via IdP {idp.name}", "info"
            )

            return {"user": user, "token_data": token_response, "userinfo": userinfo}

        except HTTPException:
            raise
        except Exception as err:
            core_logger.print_to_log(
                f"Error handling OAuth callback for IdP {idp.name}: {err}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process SSO callback",
            ) from err

    async def _get_userinfo(
        self,
        token_response: Dict[str, Any],
        userinfo_endpoint: str | None,
        client: AsyncOAuth2Client,
    ) -> Dict[str, Any]:
        """
        Retrieve user information from an identity provider using the provided token response.

        This method first attempts to fetch user information from the given `userinfo_endpoint` using the provided OAuth2 client.
        If the endpoint is unavailable or the request fails, it falls back to extracting claims from the `id_token` in the token response,
        decoding it without signature verification.

        Args:
            token_response (Dict[str, Any]): The OAuth2 token response containing access and/or ID tokens.
            userinfo_endpoint (str | None): The endpoint URL to fetch user information, if available.
            client (AsyncOAuth2Client): The asynchronous OAuth2 client used to make HTTP requests.

        Returns:
            Dict[str, Any]: The user information claims retrieved from the identity provider.

        Raises:
            HTTPException: If user information cannot be retrieved from either the userinfo endpoint or the ID token.
        """
        # Try to get from userinfo endpoint
        if userinfo_endpoint:
            try:
                # Use the access token to fetch userinfo
                access_token = token_response.get("access_token")
                if access_token:
                    response = await client.get(
                        userinfo_endpoint,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    return response.json()
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to fetch userinfo from endpoint: {err}", "warning"
                )

        # Fall back to ID token claims
        id_token = token_response.get("id_token")
        if id_token:
            try:
                # Decode JWT without verification by manually extracting the payload
                # In production, this should be verified with JWKS
                parts = id_token.split(".")
                if len(parts) != 3:
                    raise ValueError("Invalid JWT format")

                # Decode the payload (second part) - base64url decode
                payload = parts[1]
                # Add padding if necessary
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += "=" * padding

                decoded_bytes = base64.urlsafe_b64decode(payload)
                claims = json.loads(decoded_bytes)

                return claims
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to decode ID token: {err}", "warning", exc=err
                )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user information from IdP",
        )

    def _map_user_claims(
        self, idp: idp_models.IdentityProvider, claims: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Maps user claims from an identity provider to a standardized user dictionary.

        This method takes an identity provider configuration and a dictionary of claims,
        then maps the claims to standard user fields (such as 'username', 'email', and 'name')
        using both default and custom mappings defined in the identity provider.

        Args:
            idp (idp_models.IdentityProvider): The identity provider instance containing optional custom user mapping.
            claims (Dict[str, Any]): The dictionary of claims received from the identity provider.

        Returns:
            Dict[str, Any]: A dictionary mapping standard user fields to their corresponding claim values.
        """
        # Default mapping
        default_mapping = {
            "username": ["preferred_username", "username", "email", "sub"],
            "email": ["email", "mail"],
            "name": ["name", "display_name", "full_name", "displayName"],
        }

        # Merge with custom mapping
        mapping = {**default_mapping, **(idp.user_mapping or {})}

        result = {}
        for field, claim_names in mapping.items():
            if isinstance(claim_names, str):
                claim_names = [claim_names]
            for claim in claim_names:
                if claim in claims and claims[claim]:
                    result[field] = claims[claim]
                    break

        return result

    async def _find_or_create_user(
        self,
        idp: idp_models.IdentityProvider,
        subject: str,
        userinfo: Dict[str, Any],
        password_hasher: session_password_hasher.PasswordHasher,
        db: Session,
    ) -> users_models.User:
        """
        Finds an existing user linked to the given identity provider and subject, or creates a new user if allowed.

        This method attempts to:
        1. Find a user by their identity provider (IdP) link using the subject identifier.
        2. If not found, find a user by email and link their account to the IdP.
        3. If still not found and auto-creation is enabled, create a new user from the IdP information.

        Args:
            idp (idp_models.IdentityProvider): The identity provider instance.
            subject (str): The unique subject identifier from the IdP.
            userinfo (Dict[str, Any]): User information/claims from the IdP.
            password_hasher (session_password_hasher.PasswordHasher): The password hasher instance.
            db (Session): Database session.

        Returns:
            users_models.User: The found or newly created user instance.

        Raises:
            HTTPException: If user creation is disabled for the identity provider and no existing user is found.
        """
        # Try to find existing user by IdP link
        link = user_idp_crud.get_user_idp_link_by_subject(idp.id, subject, db)

        if link:
            user = link.user
            # Update last login timestamp
            user_idp_crud.update_user_idp_last_login(link.user_id, idp.id, db)

            # Update user info if sync is enabled
            if idp.sync_user_info:
                user = await self._update_user_from_idp(user, idp, userinfo, db)
            return user

        # Try to find by email (for linking existing accounts)
        mapped_data = self._map_user_claims(idp, userinfo)
        email = mapped_data.get("email")

        if email:
            user = users_crud.get_user_by_email(email, db)
            if user:
                # Link existing account to IdP
                user_idp_crud.create_user_idp_link(user.id, idp.id, subject, db)

                core_logger.print_to_log(
                    f"Linked existing user {user.username} to IdP {idp.name}", "info"
                )

                return user

        # Create new user if auto-creation is enabled
        if not idp.auto_create_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account creation is disabled for this identity provider",
            )

        user = await self._create_user_from_idp(
            idp, subject, mapped_data, password_hasher, db
        )

        return user

    async def _create_user_from_idp(
        self,
        idp: idp_models.IdentityProvider,
        subject: str,
        mapped_data: Dict[str, Any],
        password_hasher: session_password_hasher.PasswordHasher,
        db: Session,
    ) -> users_models.User:
        """
        Creates a new user in the database based on identity provider (IdP) information.

        This method generates a unique username, creates a user with mapped data from the IdP
        using the existing CRUD layer, and links the user to the IdP subject. The password is
        randomly generated and properly hashed but not intended for SSO users. The user's email
        is marked as verified since we trust the IdP's verification.

        Args:
            idp (idp_models.IdentityProvider): The identity provider instance.
            subject (str): The unique subject identifier from the IdP.
            mapped_data (Dict[str, Any]): User data mapped from the IdP (e.g., username, email, name).
            password_hasher (session_password_hasher.PasswordHasher): The password hasher instance.
            db (Session): The database session.

        Returns:
            users_models.User: The newly created user instance.

        Raises:
            HTTPException: If user creation fails (e.g., duplicate username/email).
        """
        # Generate a random password (won't be used for SSO users)
        random_password = password_hasher.generate_password(length=16)

        # Ensure username is unique
        base_username = mapped_data.get("username", f"user_{subject[:8]}")
        username = base_username
        while users_crud.get_user_by_username(username, db):
            username = f"{base_username}_{str(random.randint(100000, 999999))}"
            

        # Create user signup schema
        user_signup = users_schema.UserSignup(
            username=username,
            email=mapped_data.get("email", f"{username}@sso.local"),
            name=mapped_data.get("name", username),
            password=random_password,
            preferred_language=users_schema.Language.ENGLISH_USA,
            gender=users_schema.Gender.UNSPECIFIED,
            units=server_settings_schema.Units.METRIC,
            first_day_of_week=users_schema.WeekDay.MONDAY,
            currency=server_settings_schema.Currency.EURO,
        )

        # Create a mock server settings that bypasses email verification and admin approval
        # since we trust the IdP for these users
        mock_server_settings = type(
            "obj",
            (object,),
            {
                "signup_require_email_verification": False,
                "signup_require_admin_approval": False,
            },
        )()

        created_user = users_crud.create_signup_user(
            user_signup, mock_server_settings, password_hasher, db
        )

        # Create default data for the user
        users_utils.create_user_default_data(created_user.id, db)

        # Create the IdP link
        user_idp_crud.create_user_idp_link(created_user.id, idp.id, subject, db)

        core_logger.print_to_log(
            f"Created new user {created_user.username} from IdP {idp.name}", "info"
        )

        return created_user

    async def _update_user_from_idp(
        self,
        user: users_models.User,
        idp: idp_models.IdentityProvider,
        userinfo: Dict[str, Any],
        db: Session,
    ) -> users_models.User:
        """
        Updates the user's information based on claims received from an identity provider (IdP).

        Args:
            user (users_models.User): The user instance to update.
            idp (idp_models.IdentityProvider): The identity provider instance.
            userinfo (Dict[str, Any]): The user information claims received from the IdP.
            db (Session): The database session for committing changes.

        Returns:
            users_models.User: The updated user instance.

        Side Effects:
            Commits changes to the database and refreshes the user instance.
        """
        mapped_data = self._map_user_claims(idp, userinfo)

        # Update allowed fields
        if "email" in mapped_data and mapped_data["email"] != user.email:
            user.email = mapped_data["email"]
        if "name" in mapped_data and mapped_data["name"] != user.name:
            user.name = mapped_data["name"]

        db.commit()
        db.refresh(user)

        return user


# Global service instance
idp_service = IdentityProviderService()
