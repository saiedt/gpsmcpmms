import pytest
from gpsmcpmms.config import app


@pytest.fixture
def client(setup_demo_environment):
    """Flask test client running against the initialized config_mgr environment."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_get_cvv_data_endpoint(client):
    """Verify GET /api/cvv_data returns 200 OK and valid JSON with module payload."""
    response = client.get("/api/cvv_data")
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert data is not None
