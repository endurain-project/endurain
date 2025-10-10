import os
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
import secrets
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Request
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import jwt, JoseError

import core.config as core_config
import core.cryptography as core_cryptography
import core.logger as core_logger
import identity_providers.crud as idp_crud
import identity_providers.models as idp_models
import users.user.crud as users_crud
import users.user.models as users_models
import users.user.schema as users_schema
import users.user_identity_providers.crud as user_idp_crud


class IdentityProviderService:

    def __init__(self):
        self._discovery_cache: Dict[int, Dict[str, Any]] = {}
        self._cache_expiry: Dict[int, datetime] = {}
        self._cache_ttl = timedelta(hours=1)

    async def get_oidc_configuration(
        self, idp: idp_models.IdentityProvider
    ) -> Dict[str, Any] | None:
        """
        Asynchronously retrieves the OpenID Connect (OIDC) discovery configuration for a given identity provider.
        This method first checks if the OIDC configuration is cached and still valid. If so, it returns the cached configuration.
        Otherwise, it fetches the configuration from the identity provider's `.well-known/openid-configuration` endpoint,
        caches the result, and returns it.
        Args:
            idp (idp_models.IdentityProvider): The identity provider instance containing issuer information.
        Returns:
            Dict[str, Any] | None: The OIDC discovery configuration as a dictionary if successful, or None if the issuer URL is missing
            or if fetching the configuration fails.
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
            discovery_url = (
                f"{idp.issuer_url.rstrip('/')}/.well-known/openid-configuration"
            )
            async with httpx.AsyncClient() as client:
                response = await client.get(discovery_url, timeout=10.0)
                response.raise_for_status()
                config = response.json()

                # Cache the configuration
                self._discovery_cache[idp.id] = config
                self._cache_expiry[idp.id] = (
                    datetime.now(timezone.utc) + self._cache_ttl
                )

                core_logger.print_to_log(
                    f"Successfully fetched OIDC configuration for {idp.name}", "info"
                )

                return config
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
        return f"{base_url}/api/v1/idp/callback/{idp_slug}"

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
            client_id = core_cryptography.decrypt_token_fernet(idp.client_id)
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

            # Store in session (in production, use Redis or similar)
            if not hasattr(request.state, "session"):
                request.state.session = {}
            request.state.session[f"oauth_state_{idp.id}"] = state
            request.state.session[f"oauth_nonce_{idp.id}"] = nonce
            request.state.session["oauth_idp_id"] = idp.id

            # Build authorization URL
            redirect_uri = self._get_redirect_uri(idp.slug)
            scopes = idp.scopes or "openid profile email"

            client = AsyncOAuth2Client(
                client_id=client_id, redirect_uri=redirect_uri, scope=scopes
            )

            authorization_url, _ = client.create_authorization_url(
                authorization_endpoint, state=state, nonce=nonce
            )

            core_logger.print_to_log(
                f"Initiated OAuth login for IdP {idp.name} (ID: {idp.id})", "info"
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
            db (Session): The database session for user lookup/creation.

        Returns:
            Dict[str, Any]: A dictionary containing the authenticated user, token data, and userinfo.

        Raises:
            HTTPException: If the state is invalid, the IdP is misconfigured, user identifier is missing,
                           or any other error occurs during the callback handling process.
        """
        try:
            # Verify state
            stored_state = getattr(request.state, "session", {}).get(
                f"oauth_state_{idp.id}"
            )
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
            user = await self._find_or_create_user(idp, subject, userinfo, db)

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
                response = await client.get(userinfo_endpoint, token=token_response)
                return response.json()
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to fetch userinfo from endpoint: {err}", "warning"
                )

        # Fall back to ID token claims
        id_token = token_response.get("id_token")
        if id_token:
            try:
                # Decode without verification (verification should be done with JWKS)
                claims = jwt.decode(
                    id_token, key=None, options={"verify_signature": False}
                )
                return claims
            except JoseError as err:
                core_logger.print_to_log(f"Failed to decode ID token: {err}", "warning")

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

        user = await self._create_user_from_idp(idp, subject, mapped_data, db)

        return user

    async def _create_user_from_idp(
        self,
        idp: idp_models.IdentityProvider,
        subject: str,
        mapped_data: Dict[str, Any],
        db: Session,
    ) -> users_models.User:
        """
        Creates a new user in the database based on identity provider (IdP) information.

        This method generates a unique username, creates a user with mapped data from the IdP,
        and links the user to the IdP subject. The password is randomly generated and not intended
        for SSO users. The user's email is marked as verified, and default values are set for
        language, gender, units, and access type.

        Args:
            idp (idp_models.IdentityProvider): The identity provider instance.
            subject (str): The unique subject identifier from the IdP.
            mapped_data (Dict[str, Any]): User data mapped from the IdP (e.g., username, email, name).
            db (Session): The database session.

        Returns:
            users_models.User: The newly created user instance.
        """
        # Generate a random password (won't be used for SSO users)
        random_password = secrets.token_urlsafe(32)

        # Ensure username is unique
        base_username = mapped_data.get("username", f"user_{subject[:8]}")
        username = base_username
        counter = 1
        while users_crud.get_user_by_username(username, db):
            username = f"{base_username}{counter}"
            counter += 1

        # Create user
        user = users_models.User(
            username=username,
            email=mapped_data.get("email", f"{username}@sso.local"),
            name=mapped_data.get("name", username),
            password=random_password,  # Will be hashed by the model
            preferred_language=os.getenv("DEFAULT_LANGUAGE", "en"),
            gender=1,  # Unspecified
            units=1,  # Metric
            access_type=1,  # Regular user
            active=True,
            email_verified=True,  # Trust IdP email verification
            pending_admin_approval=False,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        # Create the IdP link
        user_idp_crud.create_user_idp_link(user.id, idp.id, subject, db)

        core_logger.print_to_log(
            f"Created new user {user.username} from IdP {idp.name}", "info"
        )

        return user

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
