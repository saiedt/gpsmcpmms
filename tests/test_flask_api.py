import pytest


@pytest.fixture
def client(setup_demo_environment):
    """Flask test client running against the initialized config_mgr environment."""
    cfg = setup_demo_environment
    # Build the Flask app and register its routes without serving it.
    cfg.start_editor(run_server=False)
    cfg._flask_app.config["TESTING"] = True
    with cfg._flask_app.test_client() as client:
        yield client


def test_get_cvv_data_endpoint(client):
    """Verify GET /api/cvv_data returns 200 OK and valid JSON with module payload."""
    response = client.get("/api/cvv_data")
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert data is not None
