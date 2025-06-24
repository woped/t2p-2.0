import pytest
from app.backend.app import app

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

def test_test_connection(client):
    response = client.get('/test_connection')
    assert response.status_code == 200
    assert response.json == "Successful"

def test_echo(client):
    response = client.get('/_/_/echo')
    assert response.status_code == 200
    assert response.json['success'] is True