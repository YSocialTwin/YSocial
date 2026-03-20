# Templates Folder Refactoring Plan

## Overview

This document describes the refactoring of the `y_web/templates/` directory from a flat layout (with templates scattered in the root) into a clean, homogeneous subfolder hierarchy grouped by application domain.

---

## Target Folder Structure

```
y_web/templates/
├── admin/                          # Admin dashboard (unchanged)
│   ├── about.html
│   ├── agent_details.html
│   ├── agents.html
│   ├── client_details.html
│   ├── client_details_forum.html
│   ├── client_details_hpc.html
│   ├── clients.html
│   ├── clients_forum.html
│   ├── clients_hpc.html
│   ├── dash_head.html
│   ├── dashboard.html
│   ├── download_notifications.html
│   ├── embedding_settings.html
│   ├── experiment_details.html
│   ├── experiment_details_forum.html
│   ├── feed_limits.html
│   ├── footer.html
│   ├── head.html
│   ├── image_feeds.html
│   ├── jupyter.html
│   ├── miscellanea.html
│   ├── opinion_configuration.html
│   ├── opinion_configuration_forum.html
│   ├── opinion_configuration_hpc.html
│   ├── opinion_evolution.html
│   ├── page_details.html
│   ├── pages.html
│   ├── population_details.html
│   ├── populations.html
│   ├── prompts.html
│   ├── prompts_forum.html
│   ├── prompts_hpc.html
│   ├── rss_feeds.html
│   ├── select_experiment.html
│   ├── settings.html
│   ├── user_details.html
│   ├── users.html
│   ├── visibility_settings.html
│   └── tutorials/
│       ├── agents_tutorial.html
│       ├── client_details_tutorial.html
│       ├── clients_tutorial.html
│       ├── dashboard_tutorial.html
│       ├── exp_details_tutorial.html
│       ├── experiments_tutorial.html
│       ├── miscellanea_tutorial.html
│       ├── pages_tutorial.html
│       ├── populations_tutorial.html
│       ├── tutorial_base.html
│       ├── tutorial_overlay.html
│       ├── user_details_tutorial.html
│       └── users_tutorial.html
├── error_pages/                    # Error pages (unchanged)
│   ├── 400.html
│   ├── 403.html
│   ├── 404.html
│   └── 500.html
├── forum/                          # Forum/Reddit interface (was: reddit/)
│   ├── feed.html
│   ├── header.html
│   ├── interview.html
│   ├── notifications.html
│   ├── profile.html
│   ├── thread.html
│   └── components/
│       ├── comment.html
│       ├── list.html
│       ├── posts.html
│       └── thread-post.html
├── login/                          # Login/registration (was: root-level)
│   ├── login.html
│   └── register.html
└── microblogging/                  # Microblogging interface (was: root-level)
    ├── edit_profile.html
    ├── emotions.html
    ├── feed.html
    ├── friends.html
    ├── hashtag.html
    ├── header.html
    ├── index.html
    ├── interest.html
    ├── interview.html
    ├── profile.html
    ├── thread.html
    └── components/
        ├── list.html
        ├── posts.html
        ├── suggested_friends.html
        ├── suggested_pages.html
        └── thread-post.html
```

---

## Refactoring Steps

### Step 1: Create New Directory Structure

```bash
cd y_web/templates
mkdir -p microblogging/components
mkdir -p forum/components
mkdir -p login
```

### Step 2: Move Templates (use `git mv` to preserve history)

#### 2a. Rename `reddit/` → `forum/`
```bash
git mv templates/reddit/feed.html           templates/forum/feed.html
git mv templates/reddit/header.html         templates/forum/header.html
git mv templates/reddit/interview.html      templates/forum/interview.html
git mv templates/reddit/notifications.html  templates/forum/notifications.html
git mv templates/reddit/profile.html        templates/forum/profile.html
git mv templates/reddit/thread.html         templates/forum/thread.html
git mv templates/reddit/components/comment.html     templates/forum/components/comment.html
git mv templates/reddit/components/list.html        templates/forum/components/list.html
git mv templates/reddit/components/posts.html       templates/forum/components/posts.html
git mv templates/reddit/components/thread-post.html templates/forum/components/thread-post.html
```

#### 2b. Move root microblogging templates → `microblogging/`
```bash
git mv templates/header.html       templates/microblogging/header.html
git mv templates/index.html        templates/microblogging/index.html
git mv templates/feed.html         templates/microblogging/feed.html
git mv templates/profile.html      templates/microblogging/profile.html
git mv templates/edit_profile.html templates/microblogging/edit_profile.html
git mv templates/friends.html      templates/microblogging/friends.html
git mv templates/hashtag.html      templates/microblogging/hashtag.html
git mv templates/emotions.html     templates/microblogging/emotions.html
git mv templates/interest.html     templates/microblogging/interest.html
git mv templates/interview.html    templates/microblogging/interview.html
git mv templates/thread.html       templates/microblogging/thread.html
```

#### 2c. Move `components/` → `microblogging/components/`
```bash
git mv templates/components/list.html              templates/microblogging/components/list.html
git mv templates/components/posts.html             templates/microblogging/components/posts.html
git mv templates/components/thread-post.html       templates/microblogging/components/thread-post.html
git mv templates/components/suggested_friends.html templates/microblogging/components/suggested_friends.html
git mv templates/components/suggested_pages.html   templates/microblogging/components/suggested_pages.html
```

#### 2d. Move login templates → `login/`
```bash
git mv templates/login.html    templates/login/login.html
git mv templates/register.html templates/login/register.html
```

---

## Required Code/Route Updates

### Python Files — `render_template()` Calls

#### `y_web/auth.py`

| Old Path | New Path |
|----------|----------|
| `"login.html"` | `"login/login.html"` |

#### `y_web/main.py`

| Old Path | New Path |
|----------|----------|
| `"login.html"` | `"login/login.html"` |
| `"profile.html"` | `"microblogging/profile.html"` |
| `"edit_profile.html"` | `"microblogging/edit_profile.html"` |
| `"feed.html"` | `"microblogging/feed.html"` |
| `"hashtag.html"` | `"microblogging/hashtag.html"` |
| `"interest.html"` | `"microblogging/interest.html"` |
| `"emotions.html"` | `"microblogging/emotions.html"` |
| `"friends.html"` | `"microblogging/friends.html"` |
| `"thread.html"` | `"microblogging/thread.html"` |
| `"interview.html"` | `"microblogging/interview.html"` |
| `"components/posts.html"` | `"microblogging/components/posts.html"` |
| `"reddit/profile.html"` | `"forum/profile.html"` |
| `"reddit/feed.html"` | `"forum/feed.html"` |
| `"reddit/thread.html"` | `"forum/thread.html"` |
| `"reddit/interview.html"` | `"forum/interview.html"` |
| `"reddit/notifications.html"` | `"forum/notifications.html"` |
| `"reddit/components/posts.html"` | `"forum/components/posts.html"` |

#### `y_web/routes_api/reddit.py`

| Old Path | New Path |
|----------|----------|
| `"reddit/components/posts.html"` | `"forum/components/posts.html"` |

### Template Files — `{% include %}` Paths

#### Microblogging templates

| Template | Old Include | New Include |
|----------|-------------|-------------|
| `microblogging/feed.html` | `"header.html"` | `"microblogging/header.html"` |
| `microblogging/feed.html` | `"components/posts.html"` | `"microblogging/components/posts.html"` |
| `microblogging/feed.html` | `"components/suggested_friends.html"` | `"microblogging/components/suggested_friends.html"` |
| `microblogging/feed.html` | `"components/suggested_pages.html"` | `"microblogging/components/suggested_pages.html"` |
| `microblogging/profile.html` | `"header.html"` | `"microblogging/header.html"` |
| `microblogging/profile.html` | `"components/posts.html"` | `"microblogging/components/posts.html"` |
| `microblogging/edit_profile.html` | `"header.html"` | `"microblogging/header.html"` |
| `microblogging/emotions.html` | `"header.html"` | `"microblogging/header.html"` |
| `microblogging/emotions.html` | `"components/posts.html"` | `"microblogging/components/posts.html"` |
| `microblogging/hashtag.html` | `"header.html"` | `"microblogging/header.html"` |
| `microblogging/hashtag.html` | `"components/posts.html"` | `"microblogging/components/posts.html"` |
| `microblogging/interest.html` | `"header.html"` | `"microblogging/header.html"` |
| `microblogging/interest.html` | `"components/posts.html"` | `"microblogging/components/posts.html"` |
| `microblogging/interview.html` | `"header.html"` | `"microblogging/header.html"` |
| `microblogging/friends.html` | `"header.html"` | `"microblogging/header.html"` |
| `microblogging/thread.html` | `"header.html"` | `"microblogging/header.html"` |
| `microblogging/thread.html` | `"components/thread-post.html"` | `"microblogging/components/thread-post.html"` |
| `microblogging/thread.html` | `"components/list.html"` | `"microblogging/components/list.html"` |
| `microblogging/components/list.html` | `"components/thread-post.html"` | `"microblogging/components/thread-post.html"` |
| `microblogging/components/list.html` | `"components/list.html"` | `"microblogging/components/list.html"` |

#### Forum templates

| Template | Old Include | New Include |
|----------|-------------|-------------|
| `forum/feed.html` | `"reddit/header.html"` | `"forum/header.html"` |
| `forum/feed.html` | `"reddit/components/posts.html"` | `"forum/components/posts.html"` |
| `forum/interview.html` | `"reddit/header.html"` | `"forum/header.html"` |
| `forum/notifications.html` | `"reddit/header.html"` | `"forum/header.html"` |
| `forum/profile.html` | `"reddit/header.html"` | `"forum/header.html"` |
| `forum/profile.html` | `"reddit/components/posts.html"` | `"forum/components/posts.html"` |
| `forum/thread.html` | `"reddit/header.html"` | `"forum/header.html"` |
| `forum/thread.html` | `"reddit/components/thread-post.html"` | `"forum/components/thread-post.html"` |
| `forum/thread.html` | `"reddit/components/list.html"` | `"forum/components/list.html"` |
| `forum/components/list.html` | `"reddit/components/comment.html"` | `"forum/components/comment.html"` |
| `forum/components/list.html` | `"reddit/components/list.html"` | `"forum/components/list.html"` |

---

## Shared Components & Reuse

### Microblogging Components (`microblogging/components/`)

| Component | Used By | Purpose |
|-----------|---------|---------|
| `posts.html` | `feed.html`, `profile.html`, `hashtag.html`, `interest.html`, `emotions.html` | Post card rendering |
| `thread-post.html` | `thread.html`, `components/list.html` | Single post in thread |
| `list.html` | `thread.html` (recursive) | Nested comment list |
| `suggested_friends.html` | `feed.html` | Sidebar friend suggestions |
| `suggested_pages.html` | `feed.html` | Sidebar page suggestions |

### Forum Components (`forum/components/`)

| Component | Used By | Purpose |
|-----------|---------|---------|
| `posts.html` | `forum/feed.html`, `forum/profile.html` | Forum post card rendering |
| `thread-post.html` | `forum/thread.html` | Single post in forum thread |
| `list.html` | `forum/thread.html` (recursive) | Nested forum comment list |
| `comment.html` | `forum/components/list.html` | Individual comment |

### Note on Cross-Domain Sharing

Microblogging and forum components are intentionally separated because they serve distinct UI patterns (Twitter-style vs. Reddit-style). Merging them would introduce conditional complexity. Shared logic belongs in the backend (Python), not templates.

---

## Testing Plan

### Unit / Regression Tests

1. **Route Response Tests** — For each route that was updated with a new template path:
   - Verify HTTP 200 response for authenticated requests.
   - Check that the response body contains expected HTML landmarks (e.g., nav elements, page titles).
   - Files to check: `y_web/tests/test_auth_routes.py`, `y_web/tests/test_admin_routes.py`, `y_web/tests/test_error_routes.py`.

2. **Template Render Tests** — Use Flask's test client with `app.test_request_context()`:
   ```python
   def test_login_renders(client):
       response = client.get('/login')
       assert response.status_code == 200
   ```

3. **Include Path Validation** — Verify no broken `{% include %}` or `{% extends %}` references by attempting to render each template in test mode.

### Integration Tests

1. **Login Flow** — POST to `/login` with valid credentials; verify redirect to feed.
2. **Feed Page** — GET `/feed`; verify posts component is embedded.
3. **Forum Feed** — GET `/reddit/feed`; verify forum layout with `forum/header.html`.
4. **Thread Page** — GET `/thread/<id>`; verify recursive comment list renders.
5. **Error Pages** — Trigger 404/500 errors; verify error_pages templates render.

### Validation Criteria for Success

- [x] All existing tests pass (622 tests passing before refactoring; 718 passing after with 96 new tests).
- [x] No `TemplateNotFound` exceptions at runtime (verified by `TestRouteIntegration` and `TestIncludePathsValid`).
- [x] All `render_template()` calls reference paths that exist under `y_web/templates/` (verified by `TestNoStaleTemplatePaths::test_all_render_template_paths_exist`).
- [x] No old-style paths remain — no `"reddit/"`, `"components/"` at root, or bare `"login.html"` (verified by `TestNoStaleTemplatePaths` and `TestOldLocationsGone`).
- [x] Flask dev server: Jinja2 can load all refactored templates without error (verified by `TestRouteIntegration::test_all_refactored_templates_loadable`).

---

## Risks and Mitigation Strategies

### Risk 1: Broken Template Paths at Runtime

**Description:** Any `render_template()` call or `{% include %}` directive that references an old path will raise a `TemplateNotFound` exception.

**Mitigation:**
- Use `git grep` to audit all template string references before and after moving files.
- Run the full test suite after each batch of moves.
- Verify with `grep -rn '"reddit/' y_web/ --include="*.py" --include="*.html"` returns empty.

### Risk 2: Dynamic Template Name Variables

**Description:** Some routes use a variable for the template name (e.g., `template_name = "admin/clients.html"`). These string-building patterns may be missed by simple grep.

**Mitigation:**
- Review `y_web/routes_admin/clients_routes.py` and `y_web/routes_admin/experiments_routes.py` for dynamic template name construction.
- The admin templates are not moved in this refactoring, so no admin dynamic names are affected.

### Risk 3: Git History Loss

**Description:** Using `cp` + `git add` + `git rm` instead of `git mv` loses file history.

**Mitigation:** Always use `git mv` for all file moves. Verify with `git log --follow <new_path>`.

### Risk 4: Recursive `{% include %}` Breaking

**Description:** `components/list.html` and `forum/components/list.html` include themselves recursively for nested threads. If the path is updated incorrectly, infinite redirect or TemplateNotFound occurs.

**Mitigation:**
- After updating, verify both files include themselves with the new full path.
- Test a thread page that contains nested comments end-to-end.

### Risk 5: Cached Templates in Production

**Description:** Production environments may cache compiled Jinja2 templates. After deployment, old cached templates may reference moved files.

**Mitigation:** Restart the Flask/WSGI server after deployment. Clear `__pycache__` and any Jinja2 bytecode cache directories.

### Risk 6: CI/CD Pipeline Template References

**Description:** CI scripts or deployment configs that reference template paths directly may break.

**Mitigation:** Search CI workflow files (`.github/workflows/`) for any hardcoded template path references before deploying.
