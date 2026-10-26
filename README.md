# HealthRecord AI

A local Flask web application for managing patient blood-test records. Valid records are saved to SQLite, and an external AI service (Google Gemini) writes short educational remarks for each one.

Built for the Gokul Infocare *AI Growth & Automation Associate* Task 2 (Python skills assessment). It is an educational prototype that uses synthetic data only. It is not affiliated with Gokul Infocare or any healthcare provider, is not deployed anywhere, and is not clinical software.

## Features

- Create, read, update and delete patient records through web forms.
- Server-side validation of name, email, date of birth (`dd/mm/yyyy`, real calendar date, not in the future) and numeric blood-test values.
- Persistent storage in SQLite (`instance/health_records.db`, created automatically).
- AI remarks from the Gemini API, shown in the Remarks column with a visible status: "AI remarks generated" or "AI service unavailable".
- Delete asks for confirmation on a separate page before anything is removed.
- If the AI service fails or no key is set, the valid record is still saved, the missing remarks are labelled, and **Retry AI remarks** is available.
- Possible-duplicate warning (same name, date of birth and email), which is a warning and not a validation failure.
- Automated tests with `pytest` that never touch the real API.

## Technology stack

Python 3, Flask, SQLite (`sqlite3` from the standard library), Jinja2 templates, HTML/CSS/vanilla JavaScript, `requests`, `python-dotenv`, `pytest`.

## Project structure

```
health-risk-app/
    app.py              Flask app factory and routes
    database.py         SQLite schema and all SQL
    validators.py       Input validation and age calculation
    ai_service.py       Gemini API request and response handling
    requirements.txt
    .env.example        Placeholder configuration (copy to .env)
    .gitignore
    pytest.ini          Lets pytest import the modules in this folder
    templates/          base, index, add/edit forms, detail, delete confirmation, error
    static/css/style.css
    static/js/app.js    Disables the submit button while a form is being processed
    tests/              conftest.py, test_validators.py, test_routes.py, test_ai_service.py
    instance/           Created at run time; holds the local database (not committed)
```

## Prerequisites

- Python 3 (developed and tested with 3.12).
- A Gemini API key from Google AI Studio (https://aistudio.google.com/apikey). The app runs without one, but remarks will show as unavailable.
- Internet access for the AI call.

The code was developed and tested with Python 3.12, Flask 3.1, requests 2.33, python-dotenv 1.2 and pytest 9.1.

## Setup

macOS / Linux:

```bash
cd health-risk-app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows (PowerShell): use `py -m venv venv`, then `venv\Scripts\Activate.ps1`, then `pip install -r requirements.txt`, then `copy .env.example .env`. The remaining commands are the same.

## Configure the API key

1. Open `.env` in a text editor and replace the placeholder after `GEMINI_API_KEY=` with your own key.
2. Optionally set `GEMINI_MODEL`. The default is `gemini-3.5-flash-lite`. Model codes get retired, so check https://ai.google.dev/gemini-api/docs/models and change this value if you receive a "model not found" message.
3. `.env` is listed in `.gitignore`. Never paste a real key into `.env.example`, the README, a screenshot or the video. The key is only read on the server and is sent to Google in a request header. It never reaches the browser.

## Run

```bash
python app.py
```

Open http://127.0.0.1:5000. `.env.example` sets `FLASK_DEBUG=1` for local development. Remove it or set it to `0` anywhere else, because Flask's debug mode must not be enabled in production.

To try one real API call without the web app, run `python ai_service.py`. It sends synthetic values and prints the remarks or the error.

## Run the tests

```bash
pytest
```

Tests use a temporary database and mock every HTTP call, so they need neither internet nor an API key. A test fixture makes any accidental real request fail. These tests prove the code handles API success and failure responses correctly. They do not prove that your key and model work, so use `python ai_service.py` or the app itself for that.

## How validation works

All checks are in `validators.py` and run on the server, so they apply even if a browser check is bypassed. The forms use `novalidate` on purpose so the server's messages are shown instead of the browser's.

| Field | Rule |
|---|---|
| Full name | Required, whitespace trimmed, at most 100 characters |
| Email | Needs `@`, a domain with a suffix (`gmail` fails, `gmail.com` passes), no spaces or doubled dots; any real-looking domain is allowed |
| Date of birth | Exactly `dd/mm/yyyy`, parsed by `datetime.strptime`; impossible dates such as 31/11/2001 fail; compared with the system date, so future dates fail; year 1900 or later |
| Glucose, Haemoglobin, Cholesterol | Plain decimal numbers (`94`, `13.5`); text, `nan`, `inf`, `1e5`, negatives and blanks fail; greater than 0 and at most 10000 |

The 10000 limit and the 1900 minimum year only catch typing mistakes. They are not clinical thresholds, and the app does not decide whether a blood value is healthy.

Every problem is reported at once, values are never silently changed, nothing invalid is saved, and the AI service is never called for an invalid submission.

An invalid submission (your input is wrong, nothing is saved) is different from an API failure (your input is fine, the record is saved, only the remarks are missing).

## How the AI integration works

`ai_service.generate_remarks()` is called after a valid record has been saved:

1. It reads `GEMINI_API_KEY` and `GEMINI_MODEL` from the environment. If the key is missing it stops with a clear message and makes no request.
2. It sends a `POST` to the Gemini `generateContent` endpoint with `requests`, using a 5 second connect timeout and a 30 second read timeout. The key goes in the `x-goog-api-key` header, not the URL.
3. Only the age (calculated from the date of birth) and the three blood values go to the API, labelled with the assumed units. The name, email and date of birth stay local.
4. The system instruction asks for plain, educational wording about possible risks. It forbids diagnoses, probabilities, and any medication or treatment advice. It requires a note that the units are assumed and that one set of values proves nothing, and it asks the reader to consult a healthcare professional. It also asks for at most 90 words.
5. The response is checked: HTTP status, valid JSON, expected structure, not blocked, finished normally, non-empty. Only then is the text saved to the `remarks` column.
6. Any failure becomes an `AIServiceError` with a user-safe message (bad key, unknown model, rate limit, server error, timeout, no network, malformed response). The message is stored in `ai_error` and shown in the UI. The key is never included in a message or log.

Editing a record regenerates remarks only when the date of birth or a blood value changes. Changing just the name or email keeps the existing remarks.

## Known limitations and health-safety disclaimer

- This is a programming assessment, not a clinically validated medical product. AI remarks are informational and unvalidated, are not a diagnosis, and do not replace interpretation by a qualified healthcare professional.
- Units are assumed to be mg/dL for glucose and cholesterol and g/dL for haemoglobin. They are not stored per record, and the app uses no reference ranges. The AI is told the units are assumed.
- AI output can be wrong or inconsistent. The app shows it as generated, with no confidence scores or disease probabilities.
- There is no login, user separation or audit trail, and the database is not encrypted. Use synthetic data only.
- Records are stored in one local SQLite file. This is not designed for several users or for production.
- The automated tests mock the Gemini API. A real call needs your own key, so run `python ai_service.py` (or add a record in the app) to confirm that your key and model work before recording the demo.

## Assessment dataset: expected outcomes

Enter the rows in this order. The only change from the brief is `.` becoming `/` in the date, because the form requires `dd/mm/yyyy`.

| Test | Name | DOB entered | Email | Glucose | Hb | Chol | Expected result |
|---|---|---|---|---:|---:|---:|---|
| 1 | Robyn Pears | 28/01/1960 | robyn@gmail.com | 232 | 13.5 | 180 | Saved, AI remarks requested |
| 2 | John Hunter | 10/12/1990 | hunter@gmail | 94 | 15 | 200 | Rejected: the domain `gmail` is incomplete |
| 3 | Darryl Tim | 12/11/1993 | timd@smh.com.au | 240 | 18.6 | 326 | Saved, AI remarks requested |
| 4 | Peter Larry | 31/11/2001 | Larry@hotmail.com | 88 | 11.5 | 165 | Rejected: 31/11/2001 is not a real calendar date |
| 5 | Sam Kerr | 09/12/2006 | sam@news.com.au | 198 | 8.9 | 192 | Saved, AI remarks requested |
| 6 | Robyn Pears | 28/01/1960 | robyn@gmail.com | 232 | 13.5 | 180 | Saved with a possible-duplicate warning; both Robyn rows are flagged |
| 7 | Madison XI | 12/09/1998 | madison@hotmail.com | 85 | 7.6 | 163 | Saved, AI remarks requested |
| 8 | Kris Wu | 19/10/2030 | Kris.wu.gmail.com | 79 | 16.5 | 197 | Rejected with two errors: future date of birth, and email without `@` |
| 9 | Tenille Singh | 30/11/1991 | Tenille@yahoo.com | 101 | 15 | 310 | Saved, AI remarks requested |
| 10 | Prem Kumar | 28/04/1990 | prem@telstra.com | 155 | 12.5 | 265 | Saved, AI remarks requested |

Result: 7 records saved (tests 1, 3, 5, 6, 7, 9, 10) and 3 rejected (tests 2, 4, 8). The records list therefore shows 7 rows, not 10.

**Duplicate policy (test 6):** a record is flagged when another record has the same name, date of birth and email (case-insensitive). It is saved, a warning is shown, and a "Possible duplicate" badge appears on both rows. A shared name alone is never flagged. If you prefer to reject duplicates, change the `find_duplicate_ids` branch in `add_patient` in `app.py` to return an error.

`tests/test_routes.py::test_assessment_dataset_in_order` checks these outcomes automatically.

## Demonstration checklist

1. Show the home page and the empty records list.
2. Add one valid record, for example test 1, and show it in the list. Mention that it is stored in SQLite.
3. Show the list with the AI remarks and status badge.
4. Edit a record and change its email to exactly `gokul@infocare.com`. Show the updated email in the list.
5. Delete one record: click Delete, show the confirmation page, confirm, then show the refreshed list.
6. Enter all ten rows in order. For each rejected row (2, 4, 8) read the error message and say where the check lives in `validators.py`. For test 6, show the duplicate warning.
7. Show real AI remarks for a valid row (needs a working key).
8. Show the failure state: blank `GEMINI_API_KEY` in `.env`, restart the app and add a record. It is saved with "AI service unavailable". Restore the key and use **Retry AI remarks**.
9. Walk through `validators.py`, `database.py` and the request code in `ai_service.py`.
10. Show the repository structure on GitHub and that `.env` and the database are not in it.

Before uploading, run `git status` and confirm that `.env` and `instance/health_records.db` are not listed.

## Key files to study

- `validators.py`
  - `clean_email`, `clean_date_of_birth`, `clean_measurement`, `clean_full_name`: one rule set each; they raise `ValidationError` with a field-level message.
  - `validate_patient`: runs every cleaner and returns `(cleaned_values, errors)`.
  - `calculate_age`: age from date of birth, used for the AI prompt.
- `database.py`
  - `connect`: context manager that commits on success, rolls back on error and always closes.
  - `add_patient`, `list_patients`, `get_patient`, `update_patient`, `delete_patient`, `set_remarks`: parameterised SQL.
  - `find_duplicate_ids` and `LIST_SQL`: the duplicate rule.
- `ai_service.py`
  - `generate_remarks`: builds and sends the request.
  - `_check_status`: turns HTTP errors into user-safe messages.
  - `_extract_text`: validates the response structure and finish reason.
- `app.py`
  - `create_app`: configuration, routes and error handlers.
  - `fetch_ai_remarks`: calls the AI service and stores the result or the error.
  - `add_patient`, `edit_patient`, `delete_patient`, `retry_ai`: the request flows.
