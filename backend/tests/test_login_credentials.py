import pytest
from pydantic import ValidationError
from houseos.auth import Credentials, LoginCredentials


def test_existing_password_authentication_is_separate_from_enrollment_policy():
    assert LoginCredentials(username="fixture", password="short").password == "short"
    with pytest.raises(ValidationError):
        Credentials(username="fixture", password="short")
    with pytest.raises(ValidationError):
        LoginCredentials(username="fixture", password="")
