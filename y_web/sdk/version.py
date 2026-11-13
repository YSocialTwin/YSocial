"""Version of the platform API (the contract between the core and the platform providers).

Semantic versioning (decision D-4): a minor version only adds, a major one may break. A name that leaves the SDK is
deprecated for one minor version first. ``y_web/tests/data/sdk_api.json`` records the surface of each version and
``y_web/tests/test_sdk_contract.py`` refuses a change to it that is not a recorded one.
"""

PLATFORM_API = "1.0"
