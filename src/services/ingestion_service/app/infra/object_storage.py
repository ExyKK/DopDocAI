import time
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlparse

from minio import Minio


class ObjectStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObjectStorageClient:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str = "us-east-1"
    max_attempts: int = 3
    retry_delay_s: float = 1.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint_url)
        if not parsed.scheme or not parsed.netloc:
            raise ObjectStorageError(f"Object storage endpoint is invalid: {self.endpoint_url!r}")
        if self.max_attempts < 1:
            raise ObjectStorageError("Object storage max_attempts must be greater than or equal to 1")

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
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                self._client.put_object(
                    self.bucket,
                    key,
                    BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                )
                return
            except Exception as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break

                time.sleep(self.retry_delay_s * attempt)

        raise ObjectStorageError(f"Object storage upload failed: {last_error}") from last_error
