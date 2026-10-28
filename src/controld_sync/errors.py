class SyncError(RuntimeError):
    pass


class SchemaError(SyncError):
    pass


__all__ = ["SchemaError", "SyncError"]
