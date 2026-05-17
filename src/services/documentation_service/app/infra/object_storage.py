from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error


class ObjectStorageError(RuntimeError):
    pass


class ObjectStorageClient:
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ):
        parsed = urlparse(endpoint_url)
        endpoint = parsed.netloc or parsed.path
        if not endpoint:
            raise ValueError("S3 endpoint is required")

        self._bucket = bucket
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=parsed.scheme == "https",
            region=region,
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def bucket_exists(self) -> bool:
        try:
            return self._client.bucket_exists(self._bucket)
        except S3Error as exc:
            raise ObjectStorageError(f"Could not check bucket {self._bucket}: {exc}") from exc

    def ensure_bucket_exists(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        except S3Error as exc:
            raise ObjectStorageError(f"Could not ensure bucket {self._bucket}: {exc}") from exc
