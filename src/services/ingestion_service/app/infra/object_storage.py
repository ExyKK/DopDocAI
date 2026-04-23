from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error


class ObjectStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObjectStorageClient:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str = "us-east-1"

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint_url)
        if not parsed.scheme or not parsed.netloc:
            raise ObjectStorageError(f"Object storage endpoint is invalid: {self.endpoint_url!r}")

        secure = parsed.scheme == "https"
        client = Minio(
            parsed.netloc,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=secure,
            region=self.region,
        )

        object.__setattr__(self, "_client", client)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                self.bucket,
                key,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        except S3Error as exc:
            raise ObjectStorageError(f"Object storage upload failed: {exc}") from exc
