from datetime import date

import pytest

import validators
from validators import ValidationError

TODAY = date(2026, 10, 26)


@pytest.mark.parametrize("email", [
    "robyn@gmail.com", "timd@smh.com.au", "Larry@hotmail.com", "Tenille@yahoo.com",
    "gokul@infocare.com", "first.last+tag@sub.example.org", "user@unfamiliar-domain.xyz",
])
def test_valid_emails_are_accepted(email):
    assert validators.clean_email(email) == email


@pytest.mark.parametrize("email", [
    "hunter@gmail", "Kris.wu.gmail.com", "", "   ", "@gmail.com", "name@.com",
    "name@gmail.", "na me@gmail.com", "name@@gmail.com", "name..x@gmail.com",
])
def test_malformed_emails_are_rejected(email):
    with pytest.raises(ValidationError):
        validators.clean_email(email)


def test_incomplete_domain_message_names_the_problem():
    with pytest.raises(ValidationError, match="incomplete"):
        validators.clean_email("hunter@gmail")
    with pytest.raises(ValidationError, match="'@'"):
        validators.clean_email("Kris.wu.gmail.com")


def test_valid_date_is_parsed():
    assert validators.clean_date_of_birth("28/01/1960", TODAY) == date(1960, 1, 28)
    assert validators.clean_date_of_birth(" 09/12/2006 ", TODAY) == date(2006, 12, 9)


def test_leap_day_is_only_valid_in_leap_years():
    assert validators.clean_date_of_birth("29/02/2000", TODAY) == date(2000, 2, 29)
    with pytest.raises(ValidationError, match="not a real calendar date"):
        validators.clean_date_of_birth("29/02/2001", TODAY)


@pytest.mark.parametrize("text", ["31/11/2001", "32/01/2000", "00/01/2000", "15/13/2000"])
def test_impossible_dates_are_rejected(text):
    with pytest.raises(ValidationError, match="not a real calendar date"):
        validators.clean_date_of_birth(text, TODAY)


@pytest.mark.parametrize("text", ["28.01.1960", "1960-01-28", "1/2/2000", "28/01/60", "abc", ""])
def test_wrong_date_format_is_rejected(text):
    with pytest.raises(ValidationError):
        validators.clean_date_of_birth(text, TODAY)


def test_future_date_is_rejected():
    with pytest.raises(ValidationError, match="future"):
        validators.clean_date_of_birth("19/10/2030", TODAY)
    with pytest.raises(ValidationError, match="future"):
        validators.clean_date_of_birth("27/10/2026", TODAY)


def test_today_is_accepted_and_uses_real_current_date_by_default():
    assert validators.clean_date_of_birth("26/10/2026", TODAY) == TODAY
    tomorrow = date.fromordinal(date.today().toordinal() + 1)
    with pytest.raises(ValidationError, match="future"):
        validators.clean_date_of_birth(tomorrow.strftime("%d/%m/%Y"))


@pytest.mark.parametrize("text, expected", [("232", 232.0), ("13.5", 13.5), ("0.5", 0.5), (" 94 ", 94.0)])
def test_numeric_values_are_accepted(text, expected):
    assert validators.clean_measurement(text, "Glucose") == expected


@pytest.mark.parametrize("text", [
    "", "  ", "abc", "12abc", "nan", "NaN", "inf", "-inf", "1e5", "1_000", "-5", "0", "1,5", "13.", ".5",
    "10001",
])
def test_non_numeric_or_unreasonable_values_are_rejected(text):
    with pytest.raises(ValidationError):
        validators.clean_measurement(text, "Glucose")


def test_full_name_is_trimmed_and_required():
    assert validators.clean_full_name("  Sam Kerr  ") == "Sam Kerr"
    for blank in ("", "   ", None):
        with pytest.raises(ValidationError):
            validators.clean_full_name(blank)


def test_validate_patient_reports_every_problem_at_once():
    form = {
        "full_name": "Kris Wu", "date_of_birth": "19/10/2030", "email": "Kris.wu.gmail.com",
        "glucose": "79", "haemoglobin": "16.5", "cholesterol": "197",
    }
    cleaned, errors = validators.validate_patient(form, TODAY)
    assert set(errors) == {"date_of_birth", "email"}
    assert "future" in errors["date_of_birth"]
    assert "full_name" in cleaned and "glucose" in cleaned


def test_validate_patient_accepts_valid_input_without_altering_values(valid_form):
    cleaned, errors = validators.validate_patient(valid_form, TODAY)
    assert errors == {}
    assert cleaned["date_of_birth"] == date(1960, 1, 28)
    assert (cleaned["glucose"], cleaned["haemoglobin"], cleaned["cholesterol"]) == (232.0, 13.5, 180.0)


def test_calculate_age_accounts_for_birthday_not_yet_reached():
    assert validators.calculate_age(date(1960, 1, 28), date(2026, 1, 27)) == 65
    assert validators.calculate_age(date(1960, 1, 28), date(2026, 1, 28)) == 66
