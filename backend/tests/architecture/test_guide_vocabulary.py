"""The file-role vocabulary in the guide and in the enforcement helpers is one list.

``docs/developer-guide/module-structure.md`` states what each file name means and
``tests/_helpers/module_roles.py`` is what the rules match on. Two lists drift, and a
role the rules know but the guide does not (or the reverse) is exactly the silent
exemption the guide warns about, so the guide's table is checked against the helper.
"""

import pathlib
import re

from tests._helpers.module_roles import ROLES

_GUIDE = pathlib.Path(__file__).resolve().parents[3] / "docs" / "developer-guide" / "module-structure.md"

#: Table filenames that stand for one role. ``router.py`` / ``public_router.py`` share a row.
_ALIASES = {"public_router": "public_router", "router": "router"}


def _roles_in_the_file_roles_table() -> set[str]:
    """Return every role the guide's "File roles" table names.

    Returns:
        The role names, without the ``.py`` suffix.
    """
    text = _GUIDE.read_text()
    section = text[text.index("## File roles") : text.index("## Visibility")]
    first_cells = re.findall(r"^\| ((?:`[a-z_]+\.py`(?: / )?)+) \|", section, re.M)
    return {name for cell in first_cells for name in re.findall(r"`([a-z_]+)\.py`", cell)}


def test_the_guide_table_and_the_role_vocabulary_agree():
    documented = _roles_in_the_file_roles_table()
    known = set(ROLES)

    assert documented == known, (
        "docs/developer-guide/module-structure.md (File roles) and tests/_helpers/module_roles.py disagree; "
        f"only in the guide: {sorted(documented - known)}; only in ROLES: {sorted(known - documented)}"
    )
