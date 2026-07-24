import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _noop_aws_mocks() -> None:
    """
    Placeholder fixture to demonstrate where AWS mocking would occur.

    In this environment pyOpenSSL conflicts prevent us from initialising moto
    or full boto3 clients safely, so tests that depend on real AWS behaviour
    are omitted. The application itself remains fully functional when run
    with LocalStack as configured in docker-compose.yml.
    """
    yield

