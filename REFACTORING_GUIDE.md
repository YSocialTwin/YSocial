# Route Structure Refactoring Guide

This document describes **how to refactor the YSocial route layer** from its current
flat-file layout into a well-structured `routes/` package.  
It does **not** make the changes; it tells you exactly what to do and how to verify
each step.

---

## 1. Context and Goals

### 1.1 Current structure

| File / directory | Blueprint name | Lines | Responsibility |
|---|---|---|---|
| `y_web/main.py` | `main` | 2 514 | Microblogging + forum views, helper functions, internal API endpoints |
| `y_web/user_interaction.py` | `user_actions` | 1 104 | Follow, share, react, publish, delete, cancel notification |
| `y_web/auth.py` | `auth` | 241 | Login, logout, experiment selection |
| `y_web/error_routes.py` | `errors` | 180 | 400/403/404/500 handlers |
| `y_web/admin_dashboard.py` | `admin` | 664 | Dashboard, model fetch, Jupyter data, about |
| `y_web/routes_admin/` | (multiple) | ~21 000 | Admin sub-features (agents, clients, experiments, jupyterlab, ollama, pages, populations, tutorial, users) |
| `y_web/routes_api/` | (multiple) | ~4 600 | REST APIs (interview, reddit/forum uploads) |

### 1.2 Target structure

```
y_web/routes/
├── __init__.py                   # register_blueprints() factory
├── social/
│   ├── __init__.py               # assembles microblogging + forum sub-packages
│   ├── _blueprint.py             # Blueprint("main", __name__)
│   ├── helpers.py                # get_safe_profile_pic, is_admin, _forum_* helpers, _experiment_memory_enabled
│   ├── common.py                 # index, profile*, edit_profile*, update_profile_data*, update_password*
│   ├── microblogging.py          # feeed_logged, feed, get_post_hashtags, get_post_interest,
│   │                             #   get_post_emotion, get_friends, get_thread, api_feed,
│   │                             #   api_hashtag_posts, api_interest_posts, api_emotion_posts, api_profile_posts
│   └── forum.py                  # interview, get_thread_reddit, feeed_logged_reddit, rnotifications*,
│                                 #   rfeed_redirect, feed_reddit, search_reddit, api_feed_reddit
├── interactions/
│   ├── __init__.py
│   ├── _blueprint.py             # Blueprint("user_actions", __name__)
│   ├── common.py                 # follow, share_content, react, delete_post, cancel_notification
│   ├── microblogging.py          # publish_post
│   └── forum.py                  # publish_post_reddit, publish_comment
├── auth/
│   ├── __init__.py
│   └── routes.py                 # login, login_post, select_experiment, logout (Blueprint "auth")
├── errors/
│   ├── __init__.py
│   └── handlers.py               # 400/403/404/500 handlers (Blueprint "errors")
├── admin/
│   ├── __init__.py               # assembles admin sub-packages
│   ├── dashboard.py              # Blueprint("admin") – moved from admin_dashboard.py
│   └── sub/                      # thin re-exports of routes_admin/* (keep existing files in place)
│       └── __init__.py
└── api/
    ├── __init__.py
    ├── reddit.py                 # thin re-export of routes_api/reddit.py
    └── interview.py              # thin re-export of routes_api/interview.py
```

### 1.3 Constraints that must be preserved

* **Blueprint names must not change.**  
  The following names are hardcoded in `url_for()` calls across Python files
  *and* Jinja templates:

  | Blueprint name | Used in |
  |---|---|
  | `auth` | Python code and templates (`url_for("auth.login")`, `url_for("auth.logout")`); `url_for("auth.signup")` appears in `templates/login/register.html` but **has no matching route in `auth.py`** — this is a pre-existing bug; do not add a `signup` route during the refactoring, but note it for a follow-up fix |
  | `main` | Python code and templates (`url_for("main.index")`, `url_for("main.feeed_logged")`, `url_for("main.search_reddit")`) |
  | `user_actions` | Redirect targets inside `user_interaction.py` itself |
  | `admin` | `url_for("admin.dashboard")` |
  | `errors` | None, but Flask error handlers look up by registered name |
  | `experiments` | `url_for("experiments.experiments")`, `url_for("experiments.settings")`, `url_for("experiments.download_notifications_page")`, `url_for("experiments.miscellanea")`, `url_for("experiments.visibility_settings")`, `url_for("experiments.experiment_details")` |
  | `users` | `url_for("users.user_data")` |

* **`y_web/__init__.py` calls `app.register_blueprint(...)` with local imports.**  
  Every blueprint object must remain importable at its current import path, *or*
  `__init__.py` must be updated to point at the new paths (see Step 5).

* **`y_web/tests/test_memory_enabled_detection.py`** imports
  `y_web.main._experiment_memory_enabled` directly (line 72) and patches
  `y_web.main.Exps` / `y_web.main.os.path.abspath`.  After moving
  `_experiment_memory_enabled` to `routes/social/helpers.py` you **must** add a
  backward-compat shim in `y_web/main.py`:
  ```python
  from y_web.routes.social.helpers import _experiment_memory_enabled  # noqa: F401
  ```
  *or* update the test's patch targets.

---

## 2. Pre-refactoring checklist

Run these commands **before** making any changes and record the outputs.  
They form your baseline.

```bash
# 1. Establish the test baseline
cd /path/to/YSocial
pip install pytest flask flask-login flask-sqlalchemy werkzeug faker numpy
python -m pytest y_web/tests/ -x -q 2>&1 | tee /tmp/baseline_tests.txt
grep -E "passed|failed|error" /tmp/baseline_tests.txt | tail -3

# 2. Count routes so you can verify nothing is lost
grep -c "@main\." y_web/main.py             # expect ~28 decorated routes
grep -c "@user\." y_web/user_interaction.py # expect ~8 decorated routes
grep -c "@auth\." y_web/auth.py             # expect ~4 decorated routes
grep -c "@errors\." y_web/error_routes.py   # expect ~4 error handlers

# 3. Record all url_for targets referenced in Python and templates
grep -rn 'url_for(' y_web/ --include="*.py" | grep -oP "url_for\(\"[^\"]+\"" | sort -u
grep -rn 'url_for(' y_web/templates/ | grep -oP "url_for\('[^']+'" | sort -u
```

---

## 3. Step-by-step migration

Complete each step, then run its validation block before proceeding.

---

### Step 1 — Create the `routes/` skeleton (no code moved yet)

```bash
mkdir -p y_web/routes/social
mkdir -p y_web/routes/interactions
mkdir -p y_web/routes/auth
mkdir -p y_web/routes/errors
mkdir -p y_web/routes/admin/sub
mkdir -p y_web/routes/api
```

Create empty `__init__.py` files in every new directory:

```bash
for d in y_web/routes \
          y_web/routes/social \
          y_web/routes/interactions \
          y_web/routes/auth \
          y_web/routes/errors \
          y_web/routes/admin \
          y_web/routes/admin/sub \
          y_web/routes/api; do
  touch "$d/__init__.py"
done
```

**Validation**

```bash
python3 -c "import y_web.routes; print('OK')"
# Expected: OK   (no errors)
python -m pytest y_web/tests/ -x -q 2>&1 | tail -3
# Expected: same counts as baseline (no regression)
```

---

### Step 2 — Create Blueprint singletons

These tiny files define a Blueprint object and nothing else. All other files in
the same package will import from them, preventing circular imports.

**`y_web/routes/social/_blueprint.py`**
```python
from flask import Blueprint

main = Blueprint("main", __name__)
```

**`y_web/routes/interactions/_blueprint.py`**
```python
from flask import Blueprint

user = Blueprint("user_actions", __name__)
```

**`y_web/routes/auth/_blueprint.py`**
```python
from flask import Blueprint

auth = Blueprint("auth", __name__)
```

**`y_web/routes/errors/_blueprint.py`**
```python
from flask import Blueprint

errors = Blueprint("errors", __name__)
```

**Validation**

```bash
python3 -c "
from y_web.routes.social._blueprint import main
from y_web.routes.interactions._blueprint import user
from y_web.routes.auth._blueprint import auth
from y_web.routes.errors._blueprint import errors
print(main.name, user.name, auth.name, errors.name)
"
# Expected: main user_actions auth errors
```

---

### Step 3 — Migrate `y_web/auth.py`

1. Copy the full content of `y_web/auth.py` into `y_web/routes/auth/routes.py`.
2. In `routes.py`, replace:
   ```python
   auth = Blueprint("auth", __name__)
   ```
   with:
   ```python
   from y_web.routes.auth._blueprint import auth
   ```
3. Update `y_web/routes/auth/__init__.py`:
   ```python
   from . import routes  # registers all routes with the blueprint
   from ._blueprint import auth

   __all__ = ["auth"]
   ```
4. Turn `y_web/auth.py` into a backward-compat shim (keep for now to avoid
   breaking `y_web/__init__.py`'s import):
   ```python
   # backward-compat shim — do not delete until __init__.py is updated (Step 5)
   from y_web.routes.auth import auth  # noqa: F401
   ```

**Validation**

```bash
python3 -c "from y_web.auth import auth; print(auth.name)"
# Expected: auth
python3 -c "from y_web.routes.auth import auth; print(len(auth.deferred_functions))"
# Expected: 4  (login GET, login POST, select_experiment, logout)
python -m pytest y_web/tests/test_auth_routes.py y_web/tests/test_simple_auth.py -v 2>&1 | tail -8
```

---

### Step 4 — Migrate `y_web/error_routes.py`

1. Copy the content of `y_web/error_routes.py` into `y_web/routes/errors/handlers.py`.
2. In `handlers.py`, replace `errors = Blueprint(...)` with:
   ```python
   from y_web.routes.errors._blueprint import errors
   ```
3. Update `y_web/routes/errors/__init__.py`:
   ```python
   from . import handlers
   from ._blueprint import errors

   __all__ = ["errors"]
   ```
4. Turn `y_web/error_routes.py` into a shim:
   ```python
   from y_web.routes.errors import errors  # noqa: F401
   ```

**Validation**

```bash
python3 -c "from y_web.error_routes import errors; print(errors.name)"
# Expected: errors
python -m pytest y_web/tests/test_error_routes.py -v 2>&1 | tail -10
```

---

### Step 5 — Migrate `y_web/admin_dashboard.py`

1. Copy `y_web/admin_dashboard.py` content into `y_web/routes/admin/dashboard.py`.
2. In `dashboard.py`, replace `admin = Blueprint(...)` with:
   ```python
   from flask import Blueprint
   admin = Blueprint("admin", __name__)
   ```
   (there are no existing shims to worry about here).
3. Update `y_web/routes/admin/__init__.py`:
   ```python
   from . import dashboard
   from .dashboard import admin

   __all__ = ["admin"]
   ```
4. Create `y_web/routes/admin/sub/__init__.py` as a thin re-export of all
   `routes_admin` blueprints (do **not** move those files yet):
   ```python
   from y_web.routes_admin.agents_routes import agents
   from y_web.routes_admin.clients_routes import clientsr
   from y_web.routes_admin.experiments_routes import experiments
   from y_web.routes_admin.jupyterlab_routes import lab
   from y_web.routes_admin.ollama_routes import ollama
   from y_web.routes_admin.pages_routes import pages
   from y_web.routes_admin.populations_routes import population
   from y_web.routes_admin.tutorial_routes import tutorial
   from y_web.routes_admin.users_routes import users

   __all__ = [
       "agents", "clientsr", "experiments", "lab",
       "ollama", "pages", "population", "tutorial", "users",
   ]
   ```
5. Turn `y_web/admin_dashboard.py` into a shim:
   ```python
   from y_web.routes.admin import admin  # noqa: F401
   ```

**Validation**

```bash
python3 -c "from y_web.admin_dashboard import admin; print(admin.name)"
# Expected: admin
python -m pytest y_web/tests/test_admin_routes.py -v 2>&1 | tail -10
```

---

### Step 6 — Migrate `y_web/user_interaction.py`

This is the safest split because routes in this file share only the `user`
Blueprint and a handful of imports; there are no mutual function calls between
routes.

#### 6.1 Create `y_web/routes/interactions/common.py`

Move here: `follow`, `share_content`, `react`, `delete_post`, `cancel_notification`
(lines 43–124, 125–196, 197–260, 1067–1085, 1086–1104 in the original file).

Template header for `common.py`:
```python
from y_web.routes.interactions._blueprint import user

# copy all top-level imports from user_interaction.py that these routes need
# e.g. from . import db; from .models import ...
```

#### 6.2 Create `y_web/routes/interactions/microblogging.py`

Move here: `publish_post` (lines 261–491).

#### 6.3 Create `y_web/routes/interactions/forum.py`

Move here: `publish_post_reddit` (lines 492–820), `publish_comment` (lines 821–1066).

#### 6.4 Update `y_web/routes/interactions/__init__.py`

```python
from ._blueprint import user
from . import common, microblogging, forum  # registers all routes

__all__ = ["user"]
```

#### 6.5 Turn `y_web/user_interaction.py` into a shim

```python
# backward-compat shim
from y_web.routes.interactions import user  # noqa: F401
```

**Validation**

```bash
python3 -c "
from y_web.routes.interactions import user
routes = [str(r) for r in user.url_map.bind('').match.__self__._rules]
" 2>/dev/null
# If the above fails, use this alternative check:
python3 -c "
from y_web.routes.interactions._blueprint import user
print(len(user.deferred_functions))
"
# Expected: 8 (one per @user.route decorator)

python -m pytest y_web/tests/test_user_interaction_routes.py -v 2>&1 | tail -10
```

---

### Step 7 — Migrate `y_web/main.py`

`main.py` contains two conceptually separate platforms (microblogging and forum),
plus shared helpers and internal API endpoints. Split it into four files.

#### 7.1 Create `y_web/routes/social/helpers.py`

Move here all private/helper functions that are **not** decorated with `@main.`:
- `get_safe_profile_pic` (lines 44–85)
- `is_admin` (lines 86–101)
- `__expand_tree`, `recursive_visit`, `__get_discussions` (lines 1214–1461)
- `_forum_logged_user`, `_forum_profile_pic`, `_forum_current_profile_pic` (lines 1465–1481)
- `_experiment_memory_enabled` (lines 1482–1550) — **critical**: see constraint note
- `_forum_memory_enabled` (lines 1551–1557)
- `_forum_paginate_posts` (lines 1558–1603)
- `_forum_resolve_back_url` (lines 1604–1615)

`helpers.py` imports only from `y_web` (db, models, utils); it must not import
from the blueprint module to avoid circular imports.

#### 7.2 Create `y_web/routes/social/common.py`

Move here routes that are shared across both platforms or are profile-related:
- `index` (lines 102–160)
- `profile` (lines 161–178)
- `profile_logged` (lines 179–363)
- `edit_profile` (lines 364–415)
- `update_profile_data` (lines 416–448)
- `update_password` (lines 449–476)

Header:
```python
from y_web.routes.social._blueprint import main
# … copy the imports that these 6 routes require from the original main.py header
```

#### 7.3 Create `y_web/routes/social/microblogging.py`

Move here all microblogging (Twitter-style) routes:
- `feeed_logged` (lines 477–530)
- `feed` (lines 531–653)
- `get_post_hashtags` (lines 654–726)
- `get_post_interest` (lines 727–799)
- `get_post_emotion` (lines 800–873)
- `get_friends` (lines 874–969)
- `get_thread` (lines 970–1213)
- `api_feed` (lines 2205–2261)
- `api_hashtag_posts` (lines 2381–2409)
- `api_interest_posts` (lines 2410–2438)
- `api_emotion_posts` (lines 2439–2471)
- `api_profile_posts` (lines 2472–2514)

#### 7.4 Create `y_web/routes/social/forum.py`

Move here all forum (Reddit-style) routes:
- `interview` (lines 1616–1685)
- `get_thread_reddit` (lines 1686–1883)
- `feeed_logged_reddit` (lines 1884–1906)
- `rnotifications_logged` (lines 1907–1918)
- `rnotifications` (lines 1919–2049)
- `rfeed_redirect` (lines 2050–2059)
- `feed_reddit` (lines 2060–2128)
- `search_reddit` (lines 2129–2201)
- `api_feed_reddit` (lines 2262–2380)

#### 7.5 Update `y_web/routes/social/__init__.py`

```python
from ._blueprint import main
from . import helpers, common, microblogging, forum  # side-effect: registers routes

__all__ = ["main"]
```

#### 7.6 Add backward-compat shims to `y_web/main.py`

Because `test_memory_enabled_detection.py` imports
`y_web.main._experiment_memory_enabled` directly, and patches `y_web.main.Exps`
and `y_web.main.os.path.abspath`, the shim must also re-export those names:

```python
"""
Backward-compatibility shim. Do not delete until all consumers are updated.
"""
from y_web.routes.social import main  # noqa: F401  (re-registers all routes)
from y_web.routes.social.helpers import (  # noqa: F401
    _experiment_memory_enabled,
    get_safe_profile_pic,
    is_admin,
)
# Re-export the modules that the tests patch so their patch paths keep working.
from y_web.models import Exps  # noqa: F401
import os  # noqa: F401 – already imported; keep for patch target y_web.main.os
```

> **Why is this the hardest step?**  
> `helpers.py` calls `_forum_logged_user()` which is in the same file, and both
> `microblogging.py` and `forum.py` call helpers.  Ensure that every helper call
> is resolved as `from y_web.routes.social.helpers import X` (an absolute import)
> rather than a relative call that assumes co-location.

**Validation**

```bash
python3 -c "
from y_web.main import _experiment_memory_enabled, main
print('Blueprint:', main.name)
print('Helper importable: OK')
"
# Expected:
# Blueprint: main
# Helper importable: OK

python -m pytest y_web/tests/test_memory_enabled_detection.py -v 2>&1 | tail -10
python -m pytest y_web/tests/test_blog_posts.py y_web/tests/test_forum_time_display.py -v 2>&1 | tail -10
```

---

### Step 8 — Migrate `y_web/routes_api/`

1. Copy `y_web/routes_api/reddit.py` content into `y_web/routes/api/reddit.py`.
   Replace the inline `api_reddit = Blueprint(...)` declaration with:
   ```python
   from flask import Blueprint
   api_reddit = Blueprint("api_reddit", __name__)
   ```
2. Copy `y_web/routes_api/interview.py` content into `y_web/routes/api/interview.py`.
   Replace `api_interview = Blueprint(...)` analogously.
3. Update `y_web/routes/api/__init__.py`:
   ```python
   from .reddit import api_reddit
   from .interview import api_interview

   __all__ = ["api_reddit", "api_interview"]
   ```
4. Turn the originals into shims:
   - `y_web/routes_api/reddit.py` → `from y_web.routes.api.reddit import api_reddit  # noqa: F401`
   - `y_web/routes_api/interview.py` → `from y_web.routes.api.interview import api_interview  # noqa: F401`

**Validation**

```bash
python3 -c "
from y_web.routes.api import api_reddit, api_interview
print(api_reddit.name, api_interview.name)
"
# Expected: api_reddit api_interview

python -m pytest y_web/tests/test_interview_server_runtime.py -v 2>&1 | tail -10
```

---

### Step 9 — Create the `register_blueprints()` factory

Update `y_web/routes/__init__.py` to expose a single function that registers every
blueprint with the Flask app:

```python
"""
Central blueprint registry.

Call ``register_blueprints(app)`` from ``y_web/__init__.py`` instead of the
current manual import-and-register block.
"""


def register_blueprints(app):
    """Register all application blueprints with *app*."""
    from .social import main
    from .interactions import user
    from .auth import auth
    from .errors import errors
    from .admin import admin
    from .admin.sub import (
        agents, clientsr, experiments, lab,
        ollama, pages, population, tutorial, users,
    )
    from .api import api_reddit, api_interview

    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(user)
    app.register_blueprint(admin)
    app.register_blueprint(ollama)
    app.register_blueprint(population)
    app.register_blueprint(pages)
    app.register_blueprint(agents)
    app.register_blueprint(users)
    app.register_blueprint(experiments)
    app.register_blueprint(clientsr)
    app.register_blueprint(errors)
    app.register_blueprint(lab)
    app.register_blueprint(tutorial)
    app.register_blueprint(api_reddit)
    app.register_blueprint(api_interview)
```

**Validation**

```bash
python3 -c "from y_web.routes import register_blueprints; print('OK')"
# Expected: OK
```

---

### Step 10 — Update `y_web/__init__.py`

Replace the entire "Register your blueprints here" block (currently spanning
~50 lines of interleaved imports and `app.register_blueprint(...)` calls) with
a single call:

```python
from y_web.routes import register_blueprints
register_blueprints(app)
```

**Validation**

```bash
python3 -c "
from y_web import create_app
app = create_app()
# Check that all expected blueprints are registered
expected = {'auth', 'main', 'user_actions', 'admin', 'errors',
            'agents', 'clientsr', 'experiments', 'lab', 'ollama',
            'pages', 'population', 'tutorial', 'users', 'api_reddit', 'api_interview'}
registered = set(app.blueprints.keys())
missing = expected - registered
if missing:
    print('MISSING blueprints:', missing)
else:
    print('All blueprints registered OK')
" 2>&1 | grep -E "OK|MISSING"
```

---

### Step 11 — Remove (or archive) the shim files

Once Step 10 is validated and all tests pass, the backward-compat shims in the
old locations can be removed:

```bash
git rm y_web/auth.py
git rm y_web/error_routes.py
git rm y_web/admin_dashboard.py
git rm y_web/user_interaction.py
git rm y_web/main.py
```

> **Do this only after** the full test suite passes and the app starts cleanly.  
> If any external project or documentation references these paths, update those
> references first.

---

## 4. Full test validation sequence

Run these after completing all steps:

```bash
# Unit tests
python -m pytest y_web/tests/ -x -q 2>&1 | tee /tmp/post_refactor_tests.txt

# Compare against baseline
diff <(grep -E "PASSED|FAILED|ERROR" /tmp/baseline_tests.txt) \
     <(grep -E "PASSED|FAILED|ERROR" /tmp/post_refactor_tests.txt)
# Expected: identical counts, no new failures

# Smoke-test the app starts
python3 -c "
from y_web import create_app
app = create_app()
with app.test_client() as c:
    r = c.get('/login')
    assert r.status_code == 200, f'Login page returned {r.status_code}'
print('App smoke test: OK')
"

# Verify url_for still resolves
python3 -c "
from y_web import create_app
app = create_app()
with app.test_request_context('/'):
    from flask import url_for
    targets = [
        'auth.login', 'auth.logout',
        'main.index', 'main.feeed_logged', 'main.search_reddit',
        'admin.dashboard',
        'experiments.settings', 'experiments.experiments',
        'users.user_data',
    ]
    for t in targets:
        try:
            url_for(t)
            print(f'  OK  {t}')
        except Exception as e:
            print(f'  FAIL {t}: {e}')
"
```

---

## 5. Avoiding common pitfalls

### 5.1 Circular imports

The most common mistake when splitting a Flask file is creating a circular
import chain.  The safe pattern is:

```
_blueprint.py   ← defines Blueprint only; imports nothing from the package
helpers.py      ← imports from y_web.* (models, db, utils); does NOT import blueprint
routes/*.py     ← imports Blueprint from _blueprint.py AND helpers from helpers.py
__init__.py     ← imports routes/* (side-effect) and re-exports Blueprint
```

Never let `helpers.py` import from `__init__.py` or from a sibling route module.

### 5.2 Wildcard imports

`y_web/main.py` contains `from .data_access import *`.  When splitting, replace
the wildcard with explicit imports in each new module:

```python
# Instead of:
from .data_access import *

# Write:
from y_web.data_access import get_posts_by_user, get_thread_by_id  # etc.
```

Run `python3 -c "from y_web.data_access import *; print(dir())"` to list all
exported names from `data_access.py`.

### 5.3 The `_experiment_memory_enabled` test constraint

`y_web/tests/test_memory_enabled_detection.py` patches:
- `y_web.main.Exps`
- `y_web.main.os.path.abspath`

After the migration, `_experiment_memory_enabled` lives in
`y_web.routes.social.helpers`.  The patches in the test will silently stop
working unless you **either**:

**Option A** – Keep the shim in `y_web/main.py` (Step 7.6 above) so that
`y_web.main.Exps` and `y_web.main.os` still exist as module-level names.

**Option B** – Update the test to patch `y_web.routes.social.helpers.Exps`
and `y_web.routes.social.helpers.os.path.abspath` instead.

Option A is lower risk for an initial migration; Option B is cleaner long-term.

### 5.4 `routes_admin/__init__.py` star-exports

`y_web/routes_admin/__init__.py` currently contains:
```python
from .agents_routes import *
from .clients_routes import *
# …
```
This means any test that does `from y_web.routes_admin import agents_routes`
will trigger the import of *all* sub-modules.  If any sub-module cannot be
imported (e.g., missing `numpy` or `faker`), the entire `routes_admin` package
fails.

Fix the `__init__.py` to use explicit named imports instead of wildcards:
```python
from .agents_routes import agents
from .clients_routes import clientsr
from .experiments_routes import experiments
from .jupyterlab_routes import lab
from .ollama_routes import ollama
from .pages_routes import pages
from .populations_routes import population
from .tutorial_routes import tutorial
from .users_routes import users
```

This also fixes the **existing test failure**
`TestRoutesAdminIntegration::test_all_admin_routes_importable`
(currently fails because `agents_routes` transitively requires `numpy`/`faker`
which are not installed in the CI environment).

---

## 6. Existing CI test failure (unrelated to refactoring)

Before starting the refactoring, address this pre-existing failure:

**`y_web/tests/test_routes_admin_basic.py::TestRoutesAdminIntegration::test_all_admin_routes_importable`**

Root cause: `y_web/routes_admin/__init__.py` uses `from .agents_routes import *`,
which triggers the import of `y_web/utils/__init__.py`, which imports
`y_web/utils/agents.py`, which imports `numpy` and `faker` — neither is in the
CI requirements.

Fix options (pick one):

1. **Preferred**: Change `routes_admin/__init__.py` star-imports to named imports
   (see Section 5.4).  This makes import of individual modules independent.

2. **Alternative**: Add `numpy` and `faker` to the test environment requirements
   (e.g., `requirements-dev.txt`), and install them in the CI pip step.

3. **Minimal**: Wrap the problematic imports inside `routes_admin/__init__.py`
   with `try/except ImportError: pass`.

To verify fix option 1:
```bash
python3 -c "import y_web.routes_admin.populations_routes; print('OK')"
# Expected: OK

python -m pytest y_web/tests/test_routes_admin_basic.py::TestRoutesAdminIntegration::test_all_admin_routes_importable -v
# Expected: PASSED
```

---

## 7. Suggested commit sequence

Each commit should leave the test suite green (or at worst no worse than the
pre-refactoring baseline).

```
feat: fix routes_admin __init__ wildcard imports → named imports
feat: create y_web/routes/ skeleton with empty packages
feat: add Blueprint singleton files for all route packages
feat: migrate y_web/auth.py → y_web/routes/auth/
feat: migrate y_web/error_routes.py → y_web/routes/errors/
feat: migrate y_web/admin_dashboard.py → y_web/routes/admin/
feat: migrate y_web/user_interaction.py → y_web/routes/interactions/
feat: migrate y_web/main.py → y_web/routes/social/
feat: migrate y_web/routes_api/ → y_web/routes/api/
feat: add y_web/routes/__init__.py register_blueprints() factory
refactor: update y_web/__init__.py to use register_blueprints()
chore: remove backward-compat shims (auth, error_routes, admin_dashboard, user_interaction, main)
```

---

## 8. Quick reference: Blueprint names and their new home

| Blueprint name | Old import path | New import path |
|---|---|---|
| `auth` | `y_web.auth.auth` | `y_web.routes.auth.auth` |
| `errors` | `y_web.error_routes.errors` | `y_web.routes.errors.errors` |
| `admin` | `y_web.admin_dashboard.admin` | `y_web.routes.admin.admin` |
| `main` | `y_web.main.main` | `y_web.routes.social.main` |
| `user_actions` | `y_web.user_interaction.user` | `y_web.routes.interactions.user` |
| `agents` | `y_web.routes_admin.agents_routes.agents` | `y_web.routes.admin.sub.agents` |
| `clientsr` | `y_web.routes_admin.clients_routes.clientsr` | `y_web.routes.admin.sub.clientsr` |
| `experiments` | `y_web.routes_admin.experiments_routes.experiments` | `y_web.routes.admin.sub.experiments` |
| `lab` | `y_web.routes_admin.jupyterlab_routes.lab` | `y_web.routes.admin.sub.lab` |
| `ollama` | `y_web.routes_admin.ollama_routes.ollama` | `y_web.routes.admin.sub.ollama` |
| `pages` | `y_web.routes_admin.pages_routes.pages` | `y_web.routes.admin.sub.pages` |
| `population` | `y_web.routes_admin.populations_routes.population` | `y_web.routes.admin.sub.population` |
| `tutorial` | `y_web.routes_admin.tutorial_routes.tutorial` | `y_web.routes.admin.sub.tutorial` |
| `users` | `y_web.routes_admin.users_routes.users` | `y_web.routes.admin.sub.users` |
| `api_reddit` | `y_web.routes_api.reddit.api_reddit` | `y_web.routes.api.api_reddit` |
| `api_interview` | `y_web.routes_api.interview.api_interview` | `y_web.routes.api.api_interview` |
