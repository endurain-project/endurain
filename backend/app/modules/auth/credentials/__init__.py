"""Auth-owned local password credential package.

Importing this package registers the :class:`LocalCredential` ORM model
with SQLAlchemy's mapper registry so the ``Users.local_credential``
relationship can be resolved at mapper-configuration time.
"""

from . import models  # noqa: F401
