# SOGRA

Flask pages for a digital loyalty card, with phone-only SMS authentication.

## Local setup

1. Install dependencies: `python3 -m pip install -r requirements.txt`.
2. Create `.env` using the variables in `.env.example`.
3. Set `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and a random, stable
   `FLASK_SECRET_KEY` (generate one with `python3 -c "import secrets; print(secrets.token_hex(32))"`).
4. Enable phone authentication and configure an SMS provider in Supabase.
5. Run `python3 app.py` and open `http://127.0.0.1:5000/login`.

Set `SESSION_COOKIE_SECURE=true` when serving over HTTPS. The random fallback
Flask secret is for local development and changes when the process restarts.

## Authentication

- `/register`: international phone number and city required, recovery email optional.
- `/login`: sends an SMS OTP only for an existing account.
- `/verify-code`: verifies the SMS code and redirects to the protected `/home`.
- `/logout`: removes the local session. Expired Supabase access tokens require login again.
- Phone numbers are validated with libphonenumber and normalized to E.164.
- City and optional recovery email are stored in Supabase user metadata at signup.
  Metadata must never be used for authorization decisions.
- Recovery email is not passed as the Supabase login email and is not used for marketing.
- Requests validate a CSRF token; Supabase errors do not expose account details.

## Account recovery: pending integration

`/account-recovery` displays the email form and validates the address. It currently
returns an explicit unavailable message: no email is sent and no account is changed.

Before enabling recovery, verify ownership of the recovery email, store a private
verified association to the user, issue expiring single-use recovery tokens, and
verify the new phone number by SMS before replacing the old number. A plain value
in user metadata is not proof of email ownership. Do not use password reset or
ordinary email login for this flow. Aggregated merchant statistics are also pending.

## Verification

Run `python3 -m unittest discover -s tests -v`. Tests mock Supabase and do not send SMS.
