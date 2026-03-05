"""
Composed access/auth router split by concern.
"""

from .shared import router

# Import modules for side-effect registration on shared router.
from . import api_keys  # noqa: F401
from . import audit  # noqa: F401
from . import authentication  # noqa: F401
from . import groups  # noqa: F401
from . import mfa  # noqa: F401
from . import users  # noqa: F401

__all__ = ["router"]
