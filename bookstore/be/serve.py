import logging
import os
import threading
from flask import Flask
from flask import Blueprint
from flask import request
from be.view import auth
from be.view import seller
from be.view import buyer
from be.view import admin
from be.view import search
init_completed_event = threading.Event()
from be.model import mongo_store
from be.model import store_mongo

bp_shutdown = Blueprint("shutdown", __name__)


def shutdown_server():
    func = request.environ.get("werkzeug.server.shutdown")
    if func is None:
        raise RuntimeError("Not running with the Werkzeug Server")
    func()


@bp_shutdown.route("/shutdown")
def be_shutdown():
    shutdown_server()
    return "Server shutting down..."


def be_run():
    this_path = os.path.dirname(__file__)
    parent_path = os.path.dirname(this_path)
    log_file = os.path.join(parent_path, "app.log")
    # SQLite initialization removed (Mongo-only)
    # Ensure Mongo collections have required indexes (idempotent)
    try:
        db = mongo_store.get_db()
        mongo_store.ensure_indexes(db)
        store_mongo.ensure_indexes(db)
    except Exception:
        # Mongo may be unavailable in certain test runs; index creation is best-effort
        pass

    logging.basicConfig(filename=log_file, level=logging.ERROR)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s"
    )
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)

    app = Flask(__name__)
    app.register_blueprint(bp_shutdown)
    app.register_blueprint(auth.bp_auth)
    app.register_blueprint(seller.bp_seller)
    app.register_blueprint(buyer.bp_buyer)
    app.register_blueprint(admin.bp_admin)
    app.register_blueprint(search.bp_search)
    init_completed_event.set()
    app.run()
