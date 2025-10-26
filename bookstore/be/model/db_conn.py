class _NullCursor:
    def __init__(self):
        self.rowcount = 0

    def fetchone(self):
        return None


class _NullConn:
    def execute(self, *args, **kwargs):
        return _NullCursor()

    def executemany(self, *args, **kwargs):
        return _NullCursor()

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


class DBConn:
    """SQLite-free base class.

    Provides a no-op .conn with minimal cursor interface so that legacy
    .conn.close() calls in views won't fail during the Mongo-only phase.
    """

    def __init__(self):
        self.conn = _NullConn()

    # Legacy helpers retained as placeholders; prefer Mongo checks in subclasses
    def user_id_exist(self, user_id):
        return False

    def book_id_exist(self, store_id, book_id):
        return False

    def store_id_exist(self, store_id):
        return False
