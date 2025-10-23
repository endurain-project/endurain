"""
File Security Exceptions Module

Contains all exception classes used by the file security system.
"""
from typing import List
from dataclasses import dataclass


@dataclass
class ConfigValidationError:
    error_type: str
    message: str
    severity: str  # 'error', 'warning', 'info'
    component: str
    recommendation: str = ""


class FileSecurityConfigurationError(Exception):
    
    def __init__(self, errors: List[ConfigValidationError]):
        self.errors = errors
        error_messages = [f"{error.severity.upper()}: {error.message}" for error in errors]
        super().__init__(f"Configuration validation failed: {'; '.join(error_messages)}")