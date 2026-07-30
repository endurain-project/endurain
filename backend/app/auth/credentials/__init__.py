"""Auth-owned local password credential package.

Importing this package registers the :class:`LocalCredential` ORM model
with SQLAlchemy's declarative metadata so the ``users_local_credentials``
table is created and mapped at startup.
"""

from . import models  # noqa: F401
