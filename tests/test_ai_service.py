import pytest
import requests

import ai_service
from ai_service import AIServiceError

FAKE_KEY = "test-key-do-not-leak-12345"


class FakeResponse:
    def __init__(self, status_code=200, body=None, bad_json=False):
        self.status_code = status_code
        self._body = body
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._body


def success_body(text="Educational note. Please consult a healthcare professional."):
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("GEMINI_MODEL", "test-model")


@pytest.fixture
def sent(monkeypatch):
    """Patch requests.post to return a configurable response and record the request."""
    record = {"response": FakeResponse(body=success_body())}

    def fake_post(url, headers=None, json=None, timeout=None):
        record.update(url=url, headers=headers, json=json, timeout=timeout)
        result = record["response"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(requests, "post", fake_post)
    return record


def call():
    return ai_service.generate_remarks(66, 232.0, 13.5, 180.0)


def test_success_returns_trimmed_text(sent):
    sent["response"] = FakeResponse(body=success_body("  Remarks text.  \n"))
    assert call() == "Remarks text."


def test_request_uses_configured_model_header_key_and_timeouts(sent):
    call()
    assert "test-model:generateContent" in sent["url"]
    assert sent["headers"]["x-goog-api-key"] == FAKE_KEY
    assert FAKE_KEY not in sent["url"]
    connect_timeout, read_timeout = sent["timeout"]
    assert 0 < connect_timeout <= 10 and 0 < read_timeout <= 60


def test_default_model_is_used_when_not_configured(sent, monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL")
    call()
    assert ai_service.DEFAULT_MODEL in sent["url"]


def test_prompt_contains_values_and_age_but_no_personal_details(sent):
    call()
    prompt = sent["json"]["contents"][0]["parts"][0]["text"]
    assert "66 years" in prompt and "232" in prompt and "13.5" in prompt and "180" in prompt
    assert "mg/dL" in prompt and "g/dL" in prompt
    for personal in ("Robyn", "robyn@gmail.com", "1960", "28/01"):
        assert personal not in prompt


def test_system_instruction_sets_safety_rules(sent):
    call()
    rules = sent["json"]["systemInstruction"]["parts"][0]["text"]
    assert "not a doctor" in rules
    assert "do not give a diagnosis" in rules
    assert "do not recommend any medication" in rules
    assert "qualified healthcare professional" in rules


def test_missing_key_raises_without_calling_api(sent, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(AIServiceError, match="GEMINI_API_KEY is not set"):
        call()
    assert "url" not in sent
    assert ai_service.is_configured() is False


def test_blank_key_counts_as_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    with pytest.raises(AIServiceError, match="not set"):
        call()


@pytest.mark.parametrize("status, body, expected", [
    (401, {"error": {"message": "unauthorised"}}, "rejected the API key"),
    (403, {"error": {"message": "forbidden"}}, "rejected the API key"),
    (400, {"error": {"message": "API key not valid. Please pass a valid API key."}}, "rejected the API key"),
    (404, {"error": {"message": "model not found"}}, "GEMINI_MODEL"),
    (429, {"error": {"message": "quota"}}, "rate limit"),
    (500, {"error": {"message": "boom"}}, "server error"),
    (503, None, "server error"),
    (400, {"error": {"message": "bad request"}}, "HTTP 400"),
])
def test_http_errors_become_clear_messages(sent, status, body, expected):
    sent["response"] = FakeResponse(status_code=status, body=body, bad_json=body is None)
    with pytest.raises(AIServiceError, match=expected):
        call()


def test_timeout_is_handled(sent):
    sent["response"] = requests.Timeout("slow")
    with pytest.raises(AIServiceError, match="timed out"):
        call()


def test_connection_error_is_handled(sent):
    sent["response"] = requests.ConnectionError("no network")
    with pytest.raises(AIServiceError, match="Could not reach"):
        call()


def test_other_request_errors_are_handled(sent):
    sent["response"] = requests.RequestException("odd")
    with pytest.raises(AIServiceError, match="failed"):
        call()


@pytest.mark.parametrize("body", [
    {}, {"candidates": []}, {"candidates": [{}]}, {"candidates": [{"content": {}}]},
    {"candidates": [{"content": {"parts": "oops"}}]}, ["not", "a", "dict"], None, "text",
])
def test_malformed_responses_are_rejected(sent, body):
    sent["response"] = FakeResponse(body=body)
    with pytest.raises(AIServiceError, match="could not be understood"):
        call()


def test_invalid_json_is_rejected(sent):
    sent["response"] = FakeResponse(bad_json=True)
    with pytest.raises(AIServiceError, match="could not be understood"):
        call()


def test_empty_text_is_rejected(sent):
    sent["response"] = FakeResponse(body=success_body("   "))
    with pytest.raises(AIServiceError, match="empty"):
        call()


def test_blocked_prompt_is_reported(sent):
    sent["response"] = FakeResponse(body={"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(AIServiceError, match="blocked"):
        call()


def test_incomplete_response_is_rejected(sent):
    body = success_body("Cut off mid-sentence")
    body["candidates"][0]["finishReason"] = "MAX_TOKENS"
    sent["response"] = FakeResponse(body=body)
    with pytest.raises(AIServiceError, match="incomplete"):
        call()


def test_very_long_text_is_capped(sent):
    sent["response"] = FakeResponse(body=success_body("x" * 5000))
    assert len(call()) == ai_service.MAX_REMARKS_LENGTH


@pytest.mark.parametrize("failure", [
    FakeResponse(status_code=401, body={"error": {"message": "bad"}}),
    FakeResponse(status_code=500, body={}),
    FakeResponse(body={}),
    requests.Timeout("slow"),
    requests.ConnectionError("down"),
])
def test_api_key_never_appears_in_error_messages(sent, failure):
    sent["response"] = failure
    with pytest.raises(AIServiceError) as error:
        call()
    assert FAKE_KEY not in str(error.value)
