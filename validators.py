import re
from datetime import date, datetime

DATE_FORMAT = "%d/%m/%Y"
MIN_BIRTH_YEAR = 1900
MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 254
# Sanity limit to catch typos such as an extra zero; it is not a clinical threshold.
MAX_MEASUREMENT = 10000

DATE_PATTERN = re.compile(r"[0-9]{2}/[0-9]{2}/[0-9]{4}")
NUMBER_PATTERN = re.compile(r"[0-9]+(\.[0-9]+)?")
EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+-]+"                              # local part
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"  # domain labels
    r"[A-Za-z]{2,}"                                    # top-level domain
)


class ValidationError(ValueError):
    """Raised with a message that is safe to show next to a form field."""


def clean_full_name(value):
    name = (value or "").strip()
    if not name:
        raise ValidationError("Full name is required.")
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"Full name must be {MAX_NAME_LENGTH} characters or fewer.")
    return name


def clean_email(value):
    email = (value or "").strip()
    if not email:
        raise ValidationError("Email address is required.")
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValidationError(f"Email address must be {MAX_EMAIL_LENGTH} characters or fewer.")
    if "@" not in email:
        raise ValidationError("Email address must contain '@', for example name@example.com.")
    domain = email.rsplit("@", 1)[1]
    if "." not in domain:
        raise ValidationError(
            f"The domain '{domain}' is incomplete. It needs a suffix, for example 'gmail.com'."
        )
    if ".." in email or not EMAIL_PATTERN.fullmatch(email):
        raise ValidationError("Enter a valid email address, for example name@example.com.")
    return email


def clean_date_of_birth(value, today=None):
    text = (value or "").strip()
    if not text:
        raise ValidationError("Date of birth is required.")
    if not DATE_PATTERN.fullmatch(text):
        raise ValidationError("Use the format dd/mm/yyyy, for example 28/01/1960.")
    try:
        born = datetime.strptime(text, DATE_FORMAT).date()
    except ValueError:
        raise ValidationError(f"{text} is not a real calendar date.") from None
    if born > (today or date.today()):
        raise ValidationError("Date of birth cannot be in the future.")
    if born.year < MIN_BIRTH_YEAR:
        raise ValidationError(f"Date of birth must be {MIN_BIRTH_YEAR} or later.")
    return born


def clean_measurement(value, label):
    text = (value or "").strip()
    if not text:
        raise ValidationError(f"{label} is required.")
    # A strict pattern rejects "nan", "inf", "1e5", "1_000" and negative numbers,
    # all of which float() would otherwise accept or parse in surprising ways.
    if not NUMBER_PATTERN.fullmatch(text):
        raise ValidationError(f"{label} must be a number, for example 94 or 13.5.")
    number = float(text)
    if not 0 < number <= MAX_MEASUREMENT:
        raise ValidationError(f"{label} must be greater than 0 and no more than {MAX_MEASUREMENT}.")
    return number


def validate_patient(form, today=None):
    """Check every field and return (cleaned_values, errors) so all problems show at once."""
    steps = {
        "full_name": lambda: clean_full_name(form.get("full_name")),
        "date_of_birth": lambda: clean_date_of_birth(form.get("date_of_birth"), today),
        "email": lambda: clean_email(form.get("email")),
        "glucose": lambda: clean_measurement(form.get("glucose"), "Glucose"),
        "haemoglobin": lambda: clean_measurement(form.get("haemoglobin"), "Haemoglobin"),
        "cholesterol": lambda: clean_measurement(form.get("cholesterol"), "Cholesterol"),
    }
    cleaned, errors = {}, {}
    for field, step in steps.items():
        try:
            cleaned[field] = step()
        except ValidationError as error:
            errors[field] = str(error)
    return cleaned, errors


def calculate_age(born, today=None):
    today = today or date.today()
    had_birthday = (today.month, today.day) >= (born.month, born.day)
    return today.year - born.year - (0 if had_birthday else 1)
