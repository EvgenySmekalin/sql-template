"""Custom exceptions for sql-template."""


class SQLTemplateError(Exception):
    """Base exception for all sql-template errors."""


class SQLTemplateSecurityError(SQLTemplateError):
    """Raised when a security violation is detected."""


class UnsafeIdentifierError(SQLTemplateSecurityError):
    """Raised when an identifier fails validation."""

    def __init__(self, identifier: str, reason: str = "") -> None:
        self.identifier = identifier
        self.reason = reason
        msg = f"Unsafe SQL identifier: {identifier!r}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class EmptyInClauseError(SQLTemplateError):
    """Raised when an IN clause receives an empty collection."""

    def __init__(self) -> None:
        super().__init__(
            "Empty collection passed to IN clause. "
            "Use empty_in_behavior='false_condition' to generate (1=0) instead."
        )


class MultiStatementError(SQLTemplateSecurityError):
    """Raised when multiple SQL statements are detected but not allowed."""

    def __init__(self) -> None:
        super().__init__(
            "Multiple SQL statements detected (semicolon found). "
            "Set allow_multistatement=True to allow this."
        )


class TemplateSizeLimitError(SQLTemplateSecurityError):
    """Raised when a template string exceeds the configured size limit."""

    def __init__(self, size: int, limit: int) -> None:
        self.size = size
        self.limit = limit
        super().__init__(
            f"Template size {size} bytes exceeds the limit of {limit} bytes."
        )
