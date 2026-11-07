"""Text form fields are guarded against NUL characters, which PostgreSQL text cannot store.

The NUL middleware does not parse multipart bodies, so a form field must be checked where it is read. The login
form is the only text form in the API and does that in ``LoginForm``; a new one needs the same guard.
"""

import pathlib

_APP = pathlib.Path("app")
_GUARDED_FORM = pathlib.Path("app/modules/auth/authentication/dependencies.py")


def test_no_route_declares_a_text_form_field_beyond_the_guarded_login_form():
    offenders = [
        str(path)
        for path in sorted(_APP.rglob("*.py"))
        if path != _GUARDED_FORM
        and not path.is_relative_to("app/logs")
        and (
            "OAuth2PasswordRequestForm" in path.read_text()
            or "= Form(" in path.read_text()
            or "Form()" in path.read_text()
        )
    ]

    assert offenders == [], (
        "A text form field must refuse NUL characters like LoginForm does (the NUL middleware skips multipart): "
        f"{offenders}"
    )
