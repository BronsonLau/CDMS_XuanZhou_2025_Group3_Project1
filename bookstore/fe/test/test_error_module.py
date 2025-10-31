from be.model import error as e


def test_error_helpers_cover():
    assert e.error_non_exist_user_id("u")[0] == 511
    assert e.error_exist_user_id("u")[0] == 512
    assert e.error_non_exist_store_id("s")[0] == 513
    assert e.error_exist_store_id("s")[0] == 514
    assert e.error_non_exist_book_id("b")[0] == 515
    assert e.error_exist_book_id("b")[0] == 516
    assert e.error_stock_level_low("b")[0] == 517
    assert e.error_invalid_order_id("o")[0] == 518
    assert e.error_not_sufficient_funds("o")[0] == 519
    assert e.error_authorization_fail()[0] == 401
    assert e.error_and_message(418, "x") == (418, "x")
    assert e.error_order_not_active()[0] == 529
    assert e.error_order_not_shipped()[0] == 530
    assert e.error_order_already_paid()[0] == 531
