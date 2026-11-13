"""Text form fields are guarded against NUL characters, which PostgreSQL text cannot store.

The NUL middleware does not parse multipart bodies, so a form field must be checked where it is read. The login
form (``LoginForm``) and the back-channel logout form (``LogoutToken``) are the text forms in the API and each does
that; a new one needs the same guard.
"""

import pathlib

_APP = pathlib.Path("app")
_GUARDED_FORMS = frozenset(
    {
        pathlib.Path("app/modules/auth/authentication/dependencies.py"),
        pathlib.Path("app/modules/auth/identity_providers/dependencies.py"),
    }
)


def test_no_route_declares_a_text_form_field_beyond_the_guarded_forms():
    offenders = [
        str(path)
        for path in sorted(_APP.rglob("*.py"))
        if path not in _GUARDED_FORMS
        and not path.is_relative_to("app/logs")
        and (
            "OAuth2PasswordRequestForm" in path.read_text()
            or "= Form(" in path.read_text()
            or "Form()" in path.read_text()
        )
    ]

    assert offenders == [], (
        "A text form field must refuse NUL characters like LoginForm and LogoutToken do (the NUL middleware skips multipart): "
        f"{offenders}"
    )
