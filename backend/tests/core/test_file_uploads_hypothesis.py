"""Property-based fuzzing of ``core.file_uploads._resolve_upload_path``."""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

import core.exceptions as core_exceptions
from core.file_uploads import _resolve_upload_path

# Filenames may contain anything a multipart parser could surface:
# arbitrary unicode, NUL bytes, separators, leading dots, control
# characters. The resolver MUST either return a path strictly under
# ``upload_dir`` or raise a domain error (400).
_FILENAME_STRATEGY = st.text(
    alphabet=st.characters(min_codepoint=0, max_codepoint=0x2FFF),
    min_size=0,
    max_size=64,
)


@given(filename=_FILENAME_STRATEGY)
@settings(max_examples=300, deadline=None)
def test_resolve_upload_path_never_escapes(tmp_path_factory, filename):
    """Property: resolver either accepts under root or raises 400."""
    upload_dir = tmp_path_factory.mktemp("uploads")
    try:
        resolved = _resolve_upload_path(str(upload_dir), filename)
    except core_exceptions.DomainError as err:
        assert err.status_code == 400
        return
    # Accepted: must resolve strictly under the upload directory.
    root = Path(upload_dir).resolve()
    resolved_resolved = Path(resolved).resolve()
    assert resolved_resolved.parent == root or root in (resolved_resolved.parents)
