"""Copy the login-scene assets (CSS, JS, logo) into the installer UI.

The launcher reuses the look of the application's login page. The installer
cannot reference ``y_web/static`` at runtime, so the files are copied here;
``y_web/tests/test_installer_scaffold.py`` fails if the copies drift.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "installer" / "ui" / "assets"
FILES = {
    "y_web/static/assets/css/login-scene.css": "login-scene.css",
    "y_web/static/assets/js/login-scene.js": "login-scene.js",
    "y_web/static/assets/img/vector/logo/Ysocial.png": "Ysocial.png",
}

if __name__ == "__main__":
    DEST.mkdir(parents=True, exist_ok=True)
    for src, name in FILES.items():
        shutil.copyfile(ROOT / src, DEST / name)
        print("copied", name)
