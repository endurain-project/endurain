"""61: let only one identity provider use an issuer

A user's link to an identity provider is only as trustworthy as the issuer that names the provider, so two providers
must not share one. The check in the service can race, so a unique index on the issuer without its trailing slashes
decides. Providers with no issuer URL are not compared. An install that already has two providers with the same issuer
cannot pick one silently: the upgrade stops and names them, and the administrator changes or deletes all but one
before upgrading again.

Revision ID: e61b7c3d9a40
Revises: c09e5b7d2f14
Create Date: 2026-11-07 15:00:00.000000

"""

from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e61b7c3d9a40"
down_revision: str | None = "c09e5b7d2f14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "identity_providers"
_ISSUER_INDEX = "uq_identity_providers_issuer_url_normalized"


def upgrade() -> None:
    """Refuse to continue while two providers share an issuer, then create the unique index.

    Raises:
        RuntimeError: When two or more providers have the same issuer once trailing slashes are ignored.
    """
    rows = op.get_bind().execute(
        sa.text(
            "SELECT rtrim(issuer_url, '/') AS issuer, slug FROM identity_providers "
            "WHERE issuer_url IS NOT NULL ORDER BY slug"
        )
    )
    slugs_by_issuer: dict[str, list[str]] = defaultdict(list)
    for issuer, slug in rows:
        slugs_by_issuer[issuer].append(slug)
    shared = {issuer: slugs for issuer, slugs in slugs_by_issuer.items() if len(slugs) > 1}
    if shared:
        lines = "; ".join(f"{issuer} is used by {', '.join(slugs)}" for issuer, slugs in sorted(shared.items()))
        raise RuntimeError(
            "Cannot upgrade: identity providers must have different issuer URLs (a trailing slash is ignored). "
            f"{lines}. Change the issuer URL of, or delete, all but one of the providers that share an issuer, "
            "then upgrade again."
        )
    op.create_index(_ISSUER_INDEX, _TABLE, [sa.text("rtrim(issuer_url, '/')")], unique=True)


def downgrade() -> None:
    """Drop the unique index."""
    op.drop_index(_ISSUER_INDEX, table_name=_TABLE)
