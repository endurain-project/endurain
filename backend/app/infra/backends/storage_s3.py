"""S3-compatible ``StorageProvider`` backend.

Only imported by the composition root when ``STORAGE_URI`` uses the ``s3://``
scheme, so local deployments never load ``boto3``. Install it with the ``s3``
extra (``pip install endurain[s3]``).
"""

from typing import Any
from urllib.parse import parse_qs, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# HeadObject error codes that mean "the object is not there" (as opposed to auth,
# region, throttling, or 5xx failures, which must surface rather than masquerade
# as a missing blob). "404" is what S3 returns for HeadObject; the aliases cover
# S3-compatible providers (MinIO, R2, Ceph).
_MISSING_OBJECT_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class S3Storage:
    """``StorageProvider`` backed by S3-compatible object storage.

    Blobs are stored at ``{prefix}/{area}/{key}`` in a bucket, where *area* is the
    domain-owned namespace; ``url`` returns a presigned GET URL. The DB stores
    only the key, so migrating local -> S3 needs no data migration. Build via
    :meth:`from_uri`.
    """

    def __init__(self, client: Any, bucket: str, prefix: str = "") -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    @classmethod
    def from_uri(cls, uri: str) -> "S3Storage":
        """Build a backend from ``s3://bucket/prefix?region=…&endpoint_url=…``.

        Args:
            uri: An ``s3://`` storage URI. ``region`` and ``endpoint_url`` query
                parameters are optional (``endpoint_url`` enables S3-compatible
                providers such as MinIO or R2).

        Returns:
            A configured ``S3Storage``.

        Raises:
            ValueError: When the URI has no bucket.
        """
        parsed = urlparse(uri)
        bucket = parsed.netloc
        if not bucket:
            raise ValueError(f"S3 STORAGE_URI is missing a bucket: {uri!r}")
        params = parse_qs(parsed.query)
        client = boto3.client(
            "s3",
            region_name=params.get("region", [None])[0],
            endpoint_url=params.get("endpoint_url", [None])[0],
            config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        )
        return cls(client, bucket, parsed.path)

    def _object_key(self, area: str, key: str) -> str:
        return "/".join(part for part in (self._prefix, area, key) if part)

    def save(self, area: str, key: str, data: bytes, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=self._object_key(area, key), Body=data, **extra)
        return key

    def get(self, area: str, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=self._object_key(area, key))
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in _MISSING_OBJECT_CODES:
                return None
            raise
        body: bytes = response["Body"].read()
        return body

    def exists(self, area: str, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._object_key(area, key))
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in _MISSING_OBJECT_CODES:
                return False
            raise
        return True

    def delete(self, area: str, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._object_key(area, key))

    def list_keys(self, area: str, prefix: str = "") -> list[str]:
        object_prefix = self._object_key(area, prefix)
        # Strip back to the area root so the returned values are plain keys.
        strip_from = len(self._object_key(area, "").rstrip("/")) + 1
        keys = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=object_prefix):
            for entry in page.get("Contents", []):
                keys.append(entry["Key"][strip_from:])
        return sorted(keys)

    def url(self, area: str, key: str, expires_in: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": self._object_key(area, key)},
            ExpiresIn=expires_in,
        )
