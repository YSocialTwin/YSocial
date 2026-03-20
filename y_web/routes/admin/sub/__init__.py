"""
Admin sub-blueprint re-exports.

This package re-exports every Blueprint from the existing ``routes_admin``
modules so that the central ``register_blueprints()`` factory can import
them all from a single location without requiring the underlying source
files to be moved.
"""
