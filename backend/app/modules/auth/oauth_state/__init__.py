"""
OAuth State Module

Server-side persistence for OAuth/SSO flow state. Replaces cookie-based
state with database storage for enhanced security and mobile support,
holding PKCE challenges, OIDC nonce, and flow metadata with replay
protection and a 10-minute hard expiry.

Exports:
    - CRUD: create_oauth_state,
      get_oauth_state_by_id,
      get_oauth_state_by_id_and_not_used,
      get_oauth_state_by_session_id,
      mark_oauth_state_used,
      delete_oauth_state,
      delete_expired_oauth_states
    - Schemas: OAuthStateCreate, OAuthStateRead
    - Models: OAuthState (ORM model)
    - Utils: create_state_id_and_nonce,
      delete_expired_oauth_states_from_db
"""

from .crud import (
    create_oauth_state,
    delete_expired_oauth_states,
    delete_oauth_state,
    get_oauth_state_by_id,
    get_oauth_state_by_id_and_not_used,
    get_oauth_state_by_session_id,
    mark_oauth_state_used,
)
from .models import OAuthState as OAuthStateModel
from .schema import OAuthStateCreate, OAuthStateRead
from .utils import (
    create_state_id_and_nonce,
    delete_expired_oauth_states_from_db,
)

__all__ = [
    # Pydantic schemas
    "OAuthStateCreate",
    # Database model
    "OAuthStateModel",
    "OAuthStateRead",
    # CRUD operations
    "create_oauth_state",
    # Utilities
    "create_state_id_and_nonce",
    "delete_expired_oauth_states",
    "delete_expired_oauth_states_from_db",
    "delete_oauth_state",
    "get_oauth_state_by_id",
    "get_oauth_state_by_id_and_not_used",
    "get_oauth_state_by_session_id",
    "mark_oauth_state_used",
]
