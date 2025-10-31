from be.model import db_conn


def test_nullconn_execute_and_cursor_methods():
    dbc = db_conn.DBConn()
    # execute should return a _NullCursor with rowcount = 0 and fetchone() = None
    cur = dbc.conn.execute("SELECT 1")
    assert hasattr(cur, "rowcount") and cur.rowcount == 0
    assert cur.fetchone() is None

    # executemany also returns a cursor-like object
    cur2 = dbc.conn.executemany("INSERT ...", [(1,), (2,)])
    assert hasattr(cur2, "rowcount") and cur2.rowcount == 0
    assert cur2.fetchone() is None

    # commit/rollback/close are no-ops and should not raise
    assert dbc.conn.commit() is None
    assert dbc.conn.rollback() is None
    assert dbc.conn.close() is None


def test_legacy_exist_helpers_return_false():
    dbc = db_conn.DBConn()
    assert dbc.user_id_exist("u") is False
    assert dbc.book_id_exist("st", "bk") is False
    assert dbc.store_id_exist("st") is False
