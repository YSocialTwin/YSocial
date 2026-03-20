"""
Admin routes sub-package.

Contains the "admin" Blueprint (dashboard, model fetching, Jupyter data,
about page) and a ``sub/`` package that re-exports all existing
``routes_admin`` blueprints without moving their source files.

  dashboard.py  – Blueprint("admin") routes (moved from admin_dashboard.py)
  sub/          – re-exports agents, clients, experiments, jupyterlab, …
"""
