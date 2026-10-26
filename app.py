import os
import secrets
import sqlite3
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for

import ai_service
import database
import validators

BASE_DIR = Path(__file__).resolve().parent


def create_app(test_config=None):
    load_dotenv(BASE_DIR / ".env")
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(16),
        DATABASE=str(BASE_DIR / "instance" / "health_records.db"),
    )
    if test_config:
        app.config.update(test_config)
    database.init_db(app.config["DATABASE"])

    @app.template_filter("display_date")
    def display_date(iso_text):
        return date.fromisoformat(iso_text).strftime(validators.DATE_FORMAT)

    @app.template_filter("number")
    def number(value):
        return f"{value:g}"

    def db_path():
        return app.config["DATABASE"]

    def get_patient_or_404(patient_id):
        patient = database.get_patient(db_path(), patient_id)
        if patient is None:
            abort(404)
        return patient

    def fetch_ai_remarks(patient_id, data):
        """Ask the AI service for remarks and store the outcome. Returns (ok, error_message)."""
        age = validators.calculate_age(data["date_of_birth"])
        try:
            remarks = ai_service.generate_remarks(
                age, data["glucose"], data["haemoglobin"], data["cholesterol"]
            )
        except ai_service.AIServiceError as error:
            database.set_remarks(db_path(), patient_id, None, str(error))
            return False, str(error)
        database.set_remarks(db_path(), patient_id, remarks, None)
        return True, None

    def flash_ai_result(patient_id, ok, error):
        if ok:
            flash(f"AI remarks generated for record #{patient_id}.", "success")
        else:
            flash(
                f"AI remarks could not be generated for record #{patient_id}: {error} "
                "The record is saved. Use Retry AI remarks when the problem is fixed.",
                "warning",
            )

    @app.route("/")
    def index():
        patients = database.list_patients(db_path())
        with_remarks = sum(1 for patient in patients if patient["remarks"])
        return render_template(
            "index.html",
            patients=patients,
            total=len(patients),
            with_remarks=with_remarks,
            without_remarks=len(patients) - with_remarks,
            possible_duplicates=sum(1 for patient in patients if patient["duplicate_count"]),
            ai_configured=ai_service.is_configured(),
        )

    @app.route("/patients/new", methods=["GET", "POST"])
    def add_patient():
        if request.method == "GET":
            return render_template("add_patient.html", form={}, errors={})

        data, errors = validators.validate_patient(request.form)
        if errors:
            return render_template("add_patient.html", form=request.form, errors=errors), 400

        duplicate_ids = database.find_duplicate_ids(db_path(), data)
        patient_id = database.add_patient(db_path(), data)
        flash(f"Record #{patient_id} for {data['full_name']} was saved.", "success")
        if duplicate_ids:
            matches = ", ".join(f"#{found}" for found in duplicate_ids)
            flash(
                f"Possible duplicate: record #{patient_id} has the same name, date of birth and "
                f"email as {matches}. It was still saved because a duplicate is a warning, "
                "not a validation error.",
                "warning",
            )
        ok, error = fetch_ai_remarks(patient_id, data)
        flash_ai_result(patient_id, ok, error)
        return redirect(url_for("index"))

    @app.route("/patients/<int:patient_id>")
    def patient_detail(patient_id):
        return render_template("patient_detail.html", patient=get_patient_or_404(patient_id))

    @app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
    def edit_patient(patient_id):
        patient = get_patient_or_404(patient_id)
        if request.method == "GET":
            form = {
                "full_name": patient["full_name"],
                "date_of_birth": date.fromisoformat(patient["date_of_birth"]).strftime(
                    validators.DATE_FORMAT
                ),
                "email": patient["email"],
                "glucose": f"{patient['glucose']:g}",
                "haemoglobin": f"{patient['haemoglobin']:g}",
                "cholesterol": f"{patient['cholesterol']:g}",
            }
            return render_template("edit_patient.html", patient=patient, form=form, errors={})

        data, errors = validators.validate_patient(request.form)
        if errors:
            return (
                render_template("edit_patient.html", patient=patient, form=request.form, errors=errors),
                400,
            )

        # Remarks describe the blood values and age, so they are only regenerated
        # when one of those changes. Editing just the name or email keeps them.
        inputs_changed = (
            data["date_of_birth"].isoformat() != patient["date_of_birth"]
            or data["glucose"] != patient["glucose"]
            or data["haemoglobin"] != patient["haemoglobin"]
            or data["cholesterol"] != patient["cholesterol"]
        )
        database.update_patient(db_path(), patient_id, data)
        flash(f"Record #{patient_id} was updated. Email: {data['email']}.", "success")
        if inputs_changed:
            ok, error = fetch_ai_remarks(patient_id, data)
            flash_ai_result(patient_id, ok, error)
        return redirect(url_for("index"))

    @app.route("/patients/<int:patient_id>/retry-ai", methods=["POST"])
    def retry_ai(patient_id):
        patient = get_patient_or_404(patient_id)
        data = {
            "date_of_birth": date.fromisoformat(patient["date_of_birth"]),
            "glucose": patient["glucose"],
            "haemoglobin": patient["haemoglobin"],
            "cholesterol": patient["cholesterol"],
        }
        ok, error = fetch_ai_remarks(patient_id, data)
        flash_ai_result(patient_id, ok, error)
        return redirect(url_for("index"))

    @app.route("/patients/<int:patient_id>/delete", methods=["GET", "POST"])
    def delete_patient(patient_id):
        patient = get_patient_or_404(patient_id)
        if request.method == "GET":
            return render_template("confirm_delete.html", patient=patient)
        database.delete_patient(db_path(), patient_id)
        flash(f"Record #{patient_id} ({patient['full_name']}) was deleted.", "success")
        return redirect(url_for("index"))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", title="Page not found",
                               message="That page or record does not exist."), 404

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        app.logger.error("Database error: %s", error)
        return render_template("error.html", title="Database error",
                               message="The database could not complete that action. "
                                       "No partial changes were saved."), 500

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("error.html", title="Something went wrong",
                               message="An unexpected error occurred."), 500

    return app


if __name__ == "__main__":
    # Debug mode is for local development only. Leave FLASK_DEBUG unset in production.
    create_app().run(debug=os.getenv("FLASK_DEBUG") == "1")
