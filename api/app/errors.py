"""Errors that routes turn into HTTP responses. Database messages stay generic."""


class FleetError(Exception):
    pass


class DatabaseUnavailable(FleetError):
    def __init__(self, cause: str) -> None:
        self.cause = cause
        super().__init__(cause)


class DuplicateVehicle(FleetError):
    pass
