"""
Base Validator Module

Contains base classes and interfaces for file security validators.
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


class BaseValidator(ABC):
    """Base class for all file security validators."""
    
    def __init__(self, config: "FileSecurityConfig"):
        self.config = config
    
    @abstractmethod
    def validate(self, *args, **kwargs) -> Any:
        """Validate input according to the specific validator's requirements."""
        pass