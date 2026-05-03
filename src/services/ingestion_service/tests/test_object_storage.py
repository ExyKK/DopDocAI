import pytest

from app.infra.object_storage import ObjectStorageClient, ObjectStorageError


def test_object_storage_client_retries_transient_upload_errors() -> None:
    client = ObjectStorageClient(
        endpoint_url="http://minio:9000",
        access_key="dopdoc",
        secret_key="dopdocstorage",
        bucket="dopdoc-artifacts",
        max_attempts=3,
        retry_delay_s=0,
    )
    fake_minio = FlakyMinio(failures_before_success=2)
    object.__setattr__(client, "_client", fake_minio)

    client.put_bytes("key.json", b"{}", "application/json")

    assert fake_minio.calls == 3


def test_object_storage_client_wraps_upload_error_after_retries() -> None:
    client = ObjectStorageClient(
        endpoint_url="http://minio:9000",
        access_key="dopdoc",
        secret_key="dopdocstorage",
        bucket="dopdoc-artifacts",
        max_attempts=2,
        retry_delay_s=0,
    )
    fake_minio = FlakyMinio(failures_before_success=3)
    object.__setattr__(client, "_client", fake_minio)

    with pytest.raises(ObjectStorageError, match="Object storage upload failed"):
        client.put_bytes("key.json", b"{}", "application/json")

    assert fake_minio.calls == 2


class FlakyMinio:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.calls = 0

    def put_object(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise RuntimeError("not ready")

        return object()
