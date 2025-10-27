"""
Base validator interface for file security checks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


class BaseValidator(ABC):
    """
    Abstract base class for file security validators.

    Attributes:
        config: File security configuration parameters.
    """

    def __init__(self, config: FileSecurityConfig):
        """
        Initialize validator with configuration.

        Args:
            config: File security settings to apply.
        """
        self.config = config

    @abstractmethod
    def validate(self, *args, **kwargs) -> Any:
        """
        Validate data using subclass-specific logic.

        Args:
            *args: Positional arguments for concrete validator.
            **kwargs: Keyword arguments for concrete validator.

        Returns:
            Validated result defined by subclass.
        """
        pass
