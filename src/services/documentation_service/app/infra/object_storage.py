import json
import time
from io import BytesIO
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
        max_attempts: int = 3,
        retry_delay_s: float = 1.0,
    ):
        parsed = urlparse(endpoint_url)
        endpoint = parsed.netloc or parsed.path
        if not endpoint:
            raise ValueError("S3 endpoint is required")

        self._bucket = bucket
        self._max_attempts = max_attempts
        self._retry_delay_s = retry_delay_s
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

    def put_bytes(self, key: str, data: bytes, content_type: str, *, bucket: str | None = None) -> None:
        bucket_name = bucket or self._bucket
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                self._client.put_object(
                    bucket_name,
                    key,
                    BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                )
                return
            except Exception as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    break

                time.sleep(self._retry_delay_s * attempt)

        raise ObjectStorageError(f"Could not write object {bucket_name}/{key}: {last_error}") from last_error

    def get_json(self, key: str, *, bucket: str | None = None, max_bytes: int = 20_000_000):
        bucket_name = bucket or self._bucket
        response = None
        try:
            response = self._client.get_object(bucket_name, key)
            data = response.read(max_bytes + 1)
        except S3Error as exc:
            raise ObjectStorageError(f"Could not read object {bucket_name}/{key}: {exc}") from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()

        if len(data) > max_bytes:
            raise ObjectStorageError(f"Object {bucket_name}/{key} exceeds max readable JSON size")

        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ObjectStorageError(f"Object {bucket_name}/{key} is not valid JSON: {exc}") from exc
