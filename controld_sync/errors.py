"""Exceptions raised by Control D synchronization."""


class SyncError(RuntimeError):
    """A recoverable synchronization or configuration error."""


class SchemaError(SyncError):
    """The input resembles a Control D export but is not a valid one."""


__all__ = ["SchemaError", "SyncError"]
