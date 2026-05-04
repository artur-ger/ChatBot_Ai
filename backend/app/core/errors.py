class AppError(Exception):
    def __init__(self, error_code: str, message: str, retry_allowed: bool) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.retry_allowed = retry_allowed


class ValidationAppError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("validation_error", message, retry_allowed=False)


class DependencyAppError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("dependency_unavailable", message, retry_allowed=True)
