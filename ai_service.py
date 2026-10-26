"""Calls the Google Gemini API to produce short, educational remarks for a record.

Run `python ai_service.py` to try one real request with synthetic values.
"""
import os

import requests

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Check https://ai.google.dev/gemini-api/docs/models for current model codes
# and override this with GEMINI_MODEL in .env if it has been retired.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
TIMEOUT = (5, 30)  # seconds to connect, seconds to wait for the response
MAX_REMARKS_LENGTH = 1500

UNITS = {"glucose": "mg/dL", "haemoglobin": "g/dL", "cholesterol": "mg/dL"}

SYSTEM_INSTRUCTION = (
    "You write short educational notes for a programming-assessment prototype that stores "
    "synthetic blood-test records. You are not a doctor. "
    "Using only the values supplied, describe health risks or conditions that values like these "
    "can be associated with, phrased as possibilities and never as findings. "
    "Rules: do not give a diagnosis; do not give probabilities or percentages; do not recommend "
    "any medication, supplement, diet or treatment; do not quote reference ranges unless you also "
    "say that ranges vary between laboratories; state that the units are assumed and that one set "
    "of values cannot establish a condition; finish by saying a qualified healthcare professional "
    "should interpret the results. Reply in plain text only, with no markdown, lists or headings, "
    "in at most 90 words."
)


class AIServiceError(Exception):
    """Raised with a message that is safe to show to the user (it never contains the API key)."""


def is_configured():
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def build_prompt(age, glucose, haemoglobin, cholesterol):
    # Only age and the three measurements are sent. Name, email and date of birth stay local.
    return (
        f"Patient (anonymised): {age} years old, sex not provided.\n"
        f"Glucose: {glucose:g} (assumed {UNITS['glucose']})\n"
        f"Haemoglobin: {haemoglobin:g} (assumed {UNITS['haemoglobin']})\n"
        f"Total cholesterol: {cholesterol:g} (assumed {UNITS['cholesterol']})\n"
        "Write the remarks for this record."
    )


def generate_remarks(age, glucose, haemoglobin, cholesterol):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AIServiceError("GEMINI_API_KEY is not set, so AI remarks could not be generated.")
    model = os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [
            {"role": "user", "parts": [{"text": build_prompt(age, glucose, haemoglobin, cholesterol)}]}
        ],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
    }
    # The key travels in a header, not the URL, so it cannot leak through logged URLs.
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    try:
        response = requests.post(
            API_URL.format(model=model), headers=headers, json=payload, timeout=TIMEOUT
        )
    except requests.Timeout:
        raise AIServiceError("The AI service timed out. Try again.") from None
    except requests.ConnectionError:
        raise AIServiceError("Could not reach the AI service. Check the internet connection.") from None
    except requests.RequestException:
        raise AIServiceError("The request to the AI service failed.") from None

    _check_status(response)
    return _extract_text(response)


def _error_message(response):
    try:
        return str(response.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return ""


def _check_status(response):
    status = response.status_code
    if status == 200:
        return
    detail = _error_message(response).lower()
    if status in (401, 403) or (status == 400 and "api key" in detail):
        raise AIServiceError("The AI service rejected the API key. Check GEMINI_API_KEY.")
    if status == 404:
        raise AIServiceError("The AI model was not found. Check GEMINI_MODEL.")
    if status == 429:
        raise AIServiceError("The AI service rate limit was reached. Try again later.")
    if status >= 500:
        raise AIServiceError(f"The AI service reported a server error (HTTP {status}). Try again later.")
    raise AIServiceError(f"The AI service rejected the request (HTTP {status}).")


def _extract_text(response):
    unreadable = AIServiceError("The AI service returned a response that could not be understood.")
    try:
        data = response.json()
    except ValueError:
        raise unreadable from None
    if not isinstance(data, dict):
        raise unreadable

    block_reason = (data.get("promptFeedback") or {}).get("blockReason")
    if block_reason:
        raise AIServiceError("The AI service blocked this request, so no remarks were produced.")

    try:
        candidate = data["candidates"][0]
        finish_reason = candidate.get("finishReason", "STOP")
        if finish_reason != "STOP":
            raise AIServiceError(
                f"The AI response was incomplete (finish reason: {finish_reason})."
            )
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
    except (KeyError, IndexError, TypeError, AttributeError):
        raise unreadable from None

    text = text.strip()
    if not text:
        raise AIServiceError("The AI service returned an empty response.")
    return text[:MAX_REMARKS_LENGTH]


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    try:
        print(generate_remarks(45, 110, 14.2, 190))
    except AIServiceError as error:
        print(f"AI call failed: {error}")
