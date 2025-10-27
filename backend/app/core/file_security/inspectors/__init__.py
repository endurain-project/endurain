"""
File content inspection modules for security validation.

This package provides inspectors that analyze the internal structure
and contents of uploaded files to detect potential security threats.
"""

from .zip_inspector import ZipContentInspector

__all__ = ["ZipContentInspector"]
