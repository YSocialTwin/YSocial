# Multi-Experiment Support Implementation

## Overview

This implementation extends YSocial to support multiple active experiments simultaneously, allowing users to join and switch between different experiments without deactivating others.

## Key Changes

### 1. Experiment Context Management (`y_web/experiment_context.py`)

New module that handles dynamic database binding for multiple experiments:

- **`get_db_bind_key_for_exp(exp_id)`**: Generates database bind keys (e.g., `db_exp_5` for experiment ID 5)
- **`register_experiment_database(app, exp_id, db_name)`**: Dynamically registers experiment databases in SQLAlchemy binds
- **`setup_experiment_context()`**: Before-request handler that extracts exp_id from URL and sets up context
- **`get_current_experiment_id()`**: Returns the current experiment ID from request context
- **`initialize_active_experiment_databases(app)`**: Called on app startup to register all active experiments

### 2. URL Structure Changes

All experiment-scoped routes now include `/<exp_id>/` prefix:

**Before:**
```
/feed/1/feed/rf/1
/profile/5/recent/1
/thread/123
```

**After:**
```
/5/feed/1/feed/rf/1
/5/profile/5/recent/1
/5/thread/123
```

Where `5` is the experiment ID.

### 3. Route Updates

#### Main Routes (`y_web/main.py`)
All feed, profile, thread, and API routes updated to accept `exp_id`:
- `/` → redirects to experiment selection or first active experiment
- `/<int:exp_id>/feed/...` → experiment-scoped feed
- `/<int:exp_id>/profile/...` → experiment-scoped profile
- `/<int:exp_id>/thread/...` → experiment-scoped thread
- And all API routes for infinite scrolling

#### User Interaction Routes (`y_web/user_interaction.py`)
All user action routes updated:
- `/<int:exp_id>/follow/...`
- `/<int:exp_id>/share_content`
- `/<int:exp_id>/react_to_content`
- `/<int:exp_id>/publish`
- `/<int:exp_id>/publish_comment`
- etc.

### 4. Experiment Activation Changes

#### Before:
- Only one experiment could have status=1 (active)
- Activating a new experiment deactivated the previous one
- Single `db_exp` bind pointed to the active experiment

#### After:
- Multiple experiments can have status=1 simultaneously
- Each active experiment gets its own bind: `db_exp_{exp_id}`
- Toggle activation/deactivation via `/admin/select_experiment/<exp_id>`

### 5. Join Simulation Flow

#### New Routes:
- **`/admin/join_simulation`**: Shows experiment selection menu if multiple active, or redirects directly if single
- **`/admin/join_experiment/<exp_id>`**: Joins a specific active experiment

#### UI Changes:
- Main "Join Simulation" button → Shows menu for multiple experiments
- Each experiment in admin panels has individual "Join" button
- Active experiments show both "Deactivate" and "Join" buttons

### 6. Template Updates

#### Context Injection:
Added global context processor in `y_web/__init__.py`:
```python
@app.context_processor
def inject_exp_id():
    return dict(exp_id=get_current_experiment_id())
```

#### URL Updates:
All templates updated to use `{{exp_id}}` prefix:
- `feed.html`
- `profile.html`
- `thread.html`
- `friends.html`
- `edit_profile.html`
- `reddit/feed.html`
- `reddit/thread.html`
- Components: `posts.html`, `reddit/components/posts.html`

#### JavaScript Integration:
Added global variables to templates:
```javascript
window.EXP_ID = {{ exp_id if exp_id else 'null' }};
window.EXP_PREFIX = window.EXP_ID ? '/' + window.EXP_ID : '';
```

### 7. JavaScript Updates

Updated AJAX calls to use experiment prefix:
- `y_web/static/assets/js/async_updates.js`
- `y_web/static/assets/js/reddit/async_updates.js`

All AJAX URLs now use:
```javascript
url: (window.EXP_PREFIX || '') + '/publish'
```

## Database Binding Architecture

### Legacy (Single Experiment):
```
SQLALCHEMY_BINDS = {
    "db_admin": "sqlite:///dashboard.db",
    "db_exp": "sqlite:///dummy.db"  # Changed when switching experiments
}
```

### New (Multiple Experiments):
```
SQLALCHEMY_BINDS = {
    "db_admin": "sqlite:///dashboard.db",
    "db_exp": "sqlite:///dummy.db",      # Legacy fallback
    "db_exp_5": "sqlite:///exp_5.db",    # Experiment 5
    "db_exp_7": "sqlite:///exp_7.db",    # Experiment 7
    ...
}
```

The `db_exp` bind is still updated for backward compatibility, but each experiment also has its unique bind.

## Request Flow

1. User clicks "Join Simulation" button
2. If multiple experiments active → Show selection menu (`/admin/join_simulation`)
3. User selects experiment → Redirects to `/admin/join_experiment/<exp_id>`
4. System redirects to experiment feed: `/<exp_id>/feed/...`
5. `before_request` handler extracts exp_id from URL
6. Sets `g.current_exp_id` and `g.current_db_bind`
7. Makes exp_id available to templates via context processor
8. All subsequent links use `{{exp_id}}` prefix
9. All AJAX calls use `window.EXP_PREFIX`

## Backward Compatibility

### Legacy Routes:
Legacy routes without exp_id still work:
- `/feed` → redirects to experiment selection or first active experiment
- `/profile` → redirects to experiment selection or first active experiment

### Single Experiment Mode:
If only one experiment is active, users are redirected directly without showing the selection menu.

## Testing

Basic tests verify:
1. Bind key generation for different experiment IDs
2. Context management functions
3. Import integrity

To run tests:
```bash
python3 /tmp/test_multi_exp2.py
```

## Future Enhancements

1. **Session-based experiment preference**: Remember user's last visited experiment
2. **Experiment switcher in UI**: Add dropdown to switch between active experiments without going to admin panel
3. **Per-experiment permissions**: Control which users can access which experiments
4. **Experiment isolation**: Ensure data doesn't leak between experiments
5. **Tests**: Add comprehensive integration tests for multi-experiment scenarios

## Migration Notes

For existing deployments:
1. No database schema changes required
2. Existing single-experiment setups continue to work
3. URLs automatically redirect to experiment-scoped versions
4. Admin users can gradually activate multiple experiments

## Files Modified

### Python Backend:
- `y_web/__init__.py` - Added context processor and before_request handler
- `y_web/experiment_context.py` - New module for experiment context management
- `y_web/main.py` - Updated all routes to accept exp_id
- `y_web/user_interaction.py` - Updated all routes to accept exp_id
- `y_web/routes_admin/experiments_routes.py` - Updated activation logic and join routes

### Templates:
- `y_web/templates/feed.html`
- `y_web/templates/profile.html`
- `y_web/templates/thread.html`
- `y_web/templates/friends.html`
- `y_web/templates/edit_profile.html`
- `y_web/templates/reddit/feed.html`
- `y_web/templates/reddit/thread.html`
- `y_web/templates/components/posts.html`
- `y_web/templates/reddit/components/posts.html`
- `y_web/templates/admin/select_experiment.html` - New template
- `y_web/templates/admin/dashboard.html`
- `y_web/templates/admin/settings.html`
- `y_web/templates/admin/experiment_details.html`
- `y_web/templates/admin/dash_head.html`

### JavaScript:
- `y_web/static/assets/js/async_updates.js`
- `y_web/static/assets/js/reddit/async_updates.js`

## Conclusion

This implementation successfully extends YSocial to support multiple active experiments while maintaining backward compatibility. The experiment-scoped URL structure provides clear isolation and makes it easy to identify which experiment a user is interacting with.
