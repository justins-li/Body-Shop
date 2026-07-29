"""WSGI entry point for production servers (gunicorn, waitress, mod_wsgi)."""

from app import create_app

application = create_app("production")
