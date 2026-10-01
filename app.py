import os
import re
import secrets
from datetime import timedelta

import phonenumbers
from dotenv import load_dotenv
from email_validator import EmailNotValidError, validate_email
from flask import Flask, abort, redirect, render_template, request, session, url_for
from supabase import ClientOptions, create_client

load_dotenv()


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
    MAX_CONTENT_LENGTH=16 * 1024,
)


def auth_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise RuntimeError("SMS login is not available yet. Please try again later.")
    # A separate client per request prevents sharing authentication between users.
    return create_client(url, key, options=ClientOptions(
        auto_refresh_token=False, persist_session=False,
    )).auth


@app.before_request
def protect_forms():
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    if request.method == "POST" and not secrets.compare_digest(
        session["csrf_token"], request.form.get("csrf_token", "")
    ):
        abort(400)


def normalized_phone(value):
    if not value.startswith("+"):
        raise ValueError("Include your country code, for example +33 6 12 34 56 78.")
    try:
        phone = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException:
        raise ValueError("Enter a valid international phone number.") from None
    if not phonenumbers.is_valid_number(phone):
        raise ValueError("Enter a valid international phone number.")
    return phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.E164)


def recovery_email(value):
    try:
        return validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError:
        raise ValueError("Enter a valid recovery email.") from None


def phone_form(register=False):
    template = "register.html" if register else "login.html"
    error = None
    status = 200
    if request.method == "POST":
        try:
            phone = normalized_phone(request.form.get("phone", "").strip())
            options = {"should_create_user": register}
            if register:
                city = request.form.get("city", "").strip()
                if not city or len(city) > 100:
                    raise ValueError("Enter your city (100 characters maximum).")
                metadata = {"city": city}
                email = request.form.get("recovery_email", "").strip()
                if email:
                    metadata["recovery_email"] = recovery_email(email)
                options["data"] = metadata
            auth_client().sign_in_with_otp({"phone": phone, "options": options})
            session["pending_phone"] = phone
            session["pending_register"] = register
            return redirect(url_for("verify_code"))
        except ValueError as exc:
            error, status = str(exc), 400
        except RuntimeError as exc:
            error, status = str(exc), 503
        except Exception:
            error, status = "Unable to send a code. Please try again later.", 502
    return render_template(template, error=error), status


@app.route("/")
@app.route("/home")
def home():
    token = session.get("access_token")
    if not token:
        return redirect(url_for("login"))
    try:
        if not auth_client().get_user(token).user:
            raise ValueError("Invalid session")
    except Exception:
        session.clear()
        return redirect(url_for("login"))
    return render_template("home.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    return phone_form()


@app.route("/register", methods=["GET", "POST"])
def register():
    return phone_form(register=True)


@app.route("/verify-code", methods=["GET", "POST"])
def verify_code():
    phone = session.get("pending_phone")
    if not phone:
        return redirect(url_for("login"))
    error = None
    status = 200
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if not re.fullmatch(r"[0-9]{6}", code):
            error, status = "Enter the 6-digit verification code.", 400
        else:
            try:
                result = auth_client().verify_otp({"phone": phone, "token": code, "type": "sms"})
                if not result.session or not result.user:
                    raise ValueError("Invalid code")
                session.clear()
                session.permanent = True
                session["access_token"] = result.session.access_token
                return redirect(url_for("home"))
            except RuntimeError as exc:
                error, status = str(exc), 503
            except Exception:
                error, status = "This code is invalid or expired. Please try again.", 400
    return render_template("verify_code.html", phone=phone, error=error), status


@app.route("/account-recovery", methods=["GET", "POST"])
def account_recovery():
    error = None
    status = 200
    if request.method == "POST":
        try:
            recovery_email(request.form.get("recovery_email", "").strip())
            # Recovery needs a verified email and a dedicated number-change flow.
            error, status = "Account recovery is not available yet. Please try again later.", 503
        except ValueError as exc:
            error, status = str(exc), 400
    return render_template("account_recovery.html", error=error), status


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
