import sqlite3

import pytest

import ai_service
import database
from app import create_app

# The ten supplied assessment rows, exactly as given. Only the date separators are
# converted from "." to "/" when a row is submitted, as the form requires dd/mm/yyyy.
ASSESSMENT_ROWS = [
    ("Robyn Pears", "28.01.1960", "robyn@gmail.com", "232", "13.5", "180"),
    ("John Hunter", "10.12.1990", "hunter@gmail", "94", "15", "200"),
    ("Darryl Tim", "12.11.1993", "timd@smh.com.au", "240", "18.6", "326"),
    ("Peter Larry", "31.11.2001", "Larry@hotmail.com", "88", "11.5", "165"),
    ("Sam Kerr", "09.12.2006", "sam@news.com.au", "198", "8.9", "192"),
    ("Robyn Pears", "28.01.1960", "robyn@gmail.com", "232", "13.5", "180"),
    ("Madison XI", "12.09.1998", "madison@hotmail.com", "85", "7.6", "163"),
    ("Kris Wu", "19.10.2030", "Kris.wu.gmail.com", "79", "16.5", "197"),
    ("Tenille Singh", "30.11.1991", "Tenille@yahoo.com", "101", "15", "310"),
    ("Prem Kumar", "28.04.1990", "prem@telstra.com", "155", "12.5", "265"),
]
FIELDS = ("full_name", "date_of_birth", "email", "glucose", "haemoglobin", "cholesterol")


def row_to_form(row):
    form = dict(zip(FIELDS, row))
    form["date_of_birth"] = form["date_of_birth"].replace(".", "/")
    return form


def saved_patients(db_file):
    return database.list_patients(db_file)


def test_home_page_loads_and_shows_empty_state(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"No records saved yet" in response.data


def test_create_saves_record_and_lists_it(client, db_file, valid_form):
    response = client.post("/patients/new", data=valid_form, follow_redirects=True)
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Robyn Pears" in page and "28/01/1960" in page and "robyn@gmail.com" in page
    assert "Stub remarks for tests." in page
    assert "AI remarks generated" in page
    patients = saved_patients(db_file)
    assert len(patients) == 1
    assert patients[0]["date_of_birth"] == "1960-01-28"
    assert patients[0]["glucose"] == 232.0 and patients[0]["haemoglobin"] == 13.5


def test_invalid_submission_is_not_saved_and_does_not_call_ai(client, db_file, valid_form, ai_calls):
    valid_form["email"] = "hunter@gmail"
    response = client.post("/patients/new", data=valid_form)
    assert response.status_code == 400
    assert "incomplete" in response.get_data(as_text=True)
    assert saved_patients(db_file) == []
    assert ai_calls == []


def test_invalid_form_keeps_what_the_user_typed(client, valid_form):
    valid_form["date_of_birth"] = "31/11/2001"
    page = client.post("/patients/new", data=valid_form).get_data(as_text=True)
    assert 'value="31/11/2001"' in page
    assert "not a real calendar date" in page


def test_submission_with_two_errors_shows_both(client, db_file):
    form = row_to_form(ASSESSMENT_ROWS[7])
    response = client.post("/patients/new", data=form)
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "cannot be in the future" in page and "must contain &#39;@&#39;" in page
    assert saved_patients(db_file) == []


def test_non_numeric_blood_value_is_rejected(client, db_file, valid_form):
    valid_form["glucose"] = "high"
    response = client.post("/patients/new", data=valid_form)
    assert response.status_code == 400
    assert "Glucose must be a number" in response.get_data(as_text=True)
    assert saved_patients(db_file) == []


def test_ai_receives_age_and_values_only(client, valid_form, ai_calls):
    client.post("/patients/new", data=valid_form)
    assert len(ai_calls) == 1
    age, glucose, haemoglobin, cholesterol = ai_calls[0]
    assert isinstance(age, int) and age >= 65
    assert (glucose, haemoglobin, cholesterol) == (232.0, 13.5, 180.0)


def test_ai_failure_saves_record_without_fake_remarks(client, db_file, valid_form, monkeypatch):
    def failing(*args):
        raise ai_service.AIServiceError("The AI service timed out. Try again.")
    monkeypatch.setattr(ai_service, "generate_remarks", failing)

    response = client.post("/patients/new", data=valid_form, follow_redirects=True)
    page = response.get_data(as_text=True)
    assert "AI service unavailable" in page
    assert "could not be generated" in page
    assert "AI remarks generated" not in page
    patient = saved_patients(db_file)[0]
    assert patient["remarks"] is None
    assert "timed out" in patient["ai_error"]


def test_retry_after_failure_stores_remarks(client, db_file, valid_form, monkeypatch):
    monkeypatch.setattr(ai_service, "generate_remarks",
                        lambda *a: (_ for _ in ()).throw(ai_service.AIServiceError("down")))
    client.post("/patients/new", data=valid_form)
    assert saved_patients(db_file)[0]["remarks"] is None

    monkeypatch.setattr(ai_service, "generate_remarks", lambda *a: "Recovered remarks.")
    client.post("/patients/1/retry-ai")
    patient = saved_patients(db_file)[0]
    assert patient["remarks"] == "Recovered remarks."
    assert patient["ai_error"] is None


def test_missing_api_key_is_reported_not_faked(client, db_file, valid_form, monkeypatch):
    monkeypatch.undo()  # drop the stub so the real generate_remarks runs (no network is reachable)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post("/patients/new", data=valid_form, follow_redirects=True)
    page = response.get_data(as_text=True)
    assert "GEMINI_API_KEY is not set" in page
    assert "AI service unavailable" in page
    assert saved_patients(db_file)[0]["remarks"] is None


def test_edit_email_keeps_remarks_and_skips_ai(client, db_file, valid_form, ai_calls):
    client.post("/patients/new", data=valid_form)
    assert len(ai_calls) == 1

    valid_form["email"] = "gokul@infocare.com"
    response = client.post("/patients/1/edit", data=valid_form, follow_redirects=True)
    page = response.get_data(as_text=True)
    assert "gokul@infocare.com" in page
    assert "robyn@gmail.com" not in page
    assert len(ai_calls) == 1
    assert saved_patients(db_file)[0]["remarks"] == "Stub remarks for tests."


def test_edit_blood_value_requests_new_remarks(client, valid_form, ai_calls):
    client.post("/patients/new", data=valid_form)
    valid_form["glucose"] = "100"
    client.post("/patients/1/edit", data=valid_form)
    assert len(ai_calls) == 2
    assert ai_calls[1][1] == 100.0


def test_edit_form_is_prefilled_in_display_format(client, valid_form):
    client.post("/patients/new", data=valid_form)
    page = client.get("/patients/1/edit").get_data(as_text=True)
    assert 'value="28/01/1960"' in page and 'value="13.5"' in page and 'value="232"' in page


def test_invalid_edit_is_not_saved(client, db_file, valid_form):
    client.post("/patients/new", data=valid_form)
    valid_form["email"] = "not-an-email"
    response = client.post("/patients/1/edit", data=valid_form)
    assert response.status_code == 400
    assert saved_patients(db_file)[0]["email"] == "robyn@gmail.com"


def test_delete_requires_confirmation(client, db_file, valid_form):
    client.post("/patients/new", data=valid_form)
    confirmation = client.get("/patients/1/delete")
    assert confirmation.status_code == 200
    assert b"Delete record #1?" in confirmation.data
    assert len(saved_patients(db_file)) == 1  # opening the page deletes nothing


def test_delete_removes_record_from_list(client, db_file, valid_form):
    client.post("/patients/new", data=valid_form)
    response = client.post("/patients/1/delete", follow_redirects=True)
    page = response.get_data(as_text=True)
    assert "was deleted" in page and "No records saved yet" in page
    assert saved_patients(db_file) == []


def test_unknown_record_returns_404_page(client):
    assert client.get("/patients/999").status_code == 404
    assert client.post("/patients/999/delete").status_code == 404
    assert client.get("/patients/999/edit").status_code == 404


def test_records_persist_after_restart(db_file, ai_calls, valid_form):
    first = create_app({"TESTING": True, "DATABASE": db_file, "SECRET_KEY": "x"})
    first.test_client().post("/patients/new", data=valid_form)

    second = create_app({"TESTING": True, "DATABASE": db_file, "SECRET_KEY": "x"})
    page = second.test_client().get("/").get_data(as_text=True)
    assert "Robyn Pears" in page and "robyn@gmail.com" in page


def test_database_error_shows_safe_message(client, valid_form, monkeypatch):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error at /secret/path")
    monkeypatch.setattr(database, "add_patient", broken)
    response = client.post("/patients/new", data=valid_form)
    page = response.get_data(as_text=True)
    assert response.status_code == 500
    assert "Database error" in page
    assert "secret" not in page and "Traceback" not in page


def test_failed_write_rolls_back(db_file):
    database.init_db(db_file)
    with pytest.raises(sqlite3.IntegrityError):
        with database.connect(db_file) as connection:
            connection.execute(
                "INSERT INTO patients (full_name, date_of_birth, email, glucose, haemoglobin, cholesterol)"
                " VALUES ('A', '2000-01-01', 'a@b.co', 1, 1, 1)")
            connection.execute("INSERT INTO patients (full_name) VALUES ('missing required columns')")
    assert database.list_patients(db_file) == []


def test_sql_injection_text_is_stored_as_plain_text(client, db_file, valid_form):
    valid_form["full_name"] = "Robert'); DROP TABLE patients;--"
    client.post("/patients/new", data=valid_form)
    assert saved_patients(db_file)[0]["full_name"] == "Robert'); DROP TABLE patients;--"


def test_html_in_name_is_escaped(client, valid_form):
    valid_form["full_name"] = "<script>alert(1)</script>"
    page = client.post("/patients/new", data=valid_form, follow_redirects=True).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_assessment_dataset_in_order(client, db_file, ai_calls):
    accepted, rejected = [], []
    for number, row in enumerate(ASSESSMENT_ROWS, start=1):
        response = client.post("/patients/new", data=row_to_form(row))
        (rejected if response.status_code == 400 else accepted).append(number)

    assert rejected == [2, 4, 8]
    assert accepted == [1, 3, 5, 6, 7, 9, 10]
    assert len(ai_calls) == 7  # invalid rows never reached the AI service

    patients = saved_patients(db_file)
    assert [p["full_name"] for p in patients] == [
        "Robyn Pears", "Darryl Tim", "Sam Kerr", "Robyn Pears",
        "Madison XI", "Tenille Singh", "Prem Kumar"]
    # Test 6 is saved and both copies are flagged as possible duplicates.
    assert [p["duplicate_count"] for p in patients] == [1, 0, 0, 1, 0, 0, 0]
    page = client.get("/").get_data(as_text=True)
    assert page.count("Possible duplicate") == 2


def test_duplicate_is_a_warning_not_a_validation_failure(client, db_file, valid_form):
    client.post("/patients/new", data=valid_form)
    response = client.post("/patients/new", data=valid_form, follow_redirects=True)
    page = response.get_data(as_text=True)
    assert "Possible duplicate: record #2" in page and "#1" in page
    assert len(saved_patients(db_file)) == 2


def test_same_name_alone_is_not_a_duplicate(client, db_file, valid_form):
    client.post("/patients/new", data=valid_form)
    valid_form["email"] = "someone.else@example.com"
    page = client.post("/patients/new", data=valid_form, follow_redirects=True).get_data(as_text=True)
    assert "Possible duplicate" not in page
