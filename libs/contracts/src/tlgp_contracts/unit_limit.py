"""Default unit limit constants for analysis complexity validation.

Each component and screen has a complexity budget measured in "units":
- Each annotation (child element) costs a fixed number of units.
- Each API costs a fixed number of units.
- The total must not exceed the configured maximum.
"""

DEFAULT_UNIT_COST_ANNOTATION = 1
DEFAULT_UNIT_COST_API = 3
DEFAULT_UNIT_LIMIT = 15
