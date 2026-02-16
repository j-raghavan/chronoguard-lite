"""Access decision outcomes for policy evaluation."""
from enum import Enum, auto


class AccessDecision(Enum):
    ALLOW = auto()
    DENY = auto()
    RATE_LIMITED = auto()
    NO_MATCHING_POLICY = auto()

    def is_permitted(self) -> bool:
        """Returns True only for ALLOW."""
        return self is AccessDecision.ALLOW
