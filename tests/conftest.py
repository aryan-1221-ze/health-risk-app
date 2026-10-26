import pytest
import requests

import ai_service
from app import create_app


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    """No test may reach the real AI API. Tests that need requests.post patch it themselves."""
    def refuse(*args, **kwargs):
        raise AssertionError("A test tried to make a real HTTP request")
    monkeypatch.setattr(requests, "post", refuse)


@pytest.fixture
def ai_calls(monkeypatch):
    """Replace the AI call with a stub that records its arguments."""
    calls = []

    def fake_generate_remarks(age, glucose, haemoglobin, cholesterol):
        calls.append((age, glucose, haemoglobin, cholesterol))
        return "Stub remarks for tests."

    monkeypatch.setattr(ai_service, "generate_remarks", fake_generate_remarks)
    return calls


@pytest.fixture
def db_file(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def app(db_file, ai_calls):
    return create_app({"TESTING": True, "DATABASE": db_file, "SECRET_KEY": "test"})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def valid_form():
    return {
        "full_name": "Robyn Pears",
        "date_of_birth": "28/01/1960",
        "email": "robyn@gmail.com",
        "glucose": "232",
        "haemoglobin": "13.5",
        "cholesterol": "180",
    }
