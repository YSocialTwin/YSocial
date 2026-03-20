"""
Error handler routes sub-package.

Contains the "errors" Blueprint which registers Flask app-level error
handlers for HTTP 400, 403, 404, and 500 responses.

  _blueprint.py – Blueprint("errors") singleton
  handlers.py   – @errors.app_errorhandler decorators
"""
