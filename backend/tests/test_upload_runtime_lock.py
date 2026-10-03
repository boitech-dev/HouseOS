"""Upload locks belong under the API service's writable runtime/run boundary."""

from uuid import uuid4
import pytest
from fastapi import HTTPException
from houseos.files import upload_lock
from houseos.config import settings


def test_upload_lock_uses_writable_run_directory_and_excludes_concurrent_request(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    identity = str(uuid4())
    with upload_lock(identity):
        assert (tmp_path / "run" / "upload-locks" / identity).is_file()
        assert not (tmp_path / "upload-locks").exists()
        with pytest.raises(HTTPException) as error:
            with upload_lock(identity):
                pass
        assert error.value.status_code == 409
    with upload_lock(identity):
        pass
