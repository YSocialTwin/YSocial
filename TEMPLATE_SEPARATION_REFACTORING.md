# Template CSS/JS Separation Refactoring Plan

This document analyzes the `y_web/templates/` directory and proposes a phase-organized
refactoring to enforce the separation of HTML structure, CSS presentation, and JavaScript
behaviour across all 83 Jinja2 templates.

---

## Table of Contents

1. [Current State and Problems](#1-current-state-and-problems)
2. [Target Architecture](#2-target-architecture)
3. [Phased Implementation Plan](#3-phased-implementation-plan)
   - [Phase T1 — Audit Baseline and Tooling](#phase-t1--audit-baseline-and-tooling)
   - [Phase T2 — Shared Layout CSS Extraction](#phase-t2--shared-layout-css-extraction)
   - [Phase T3 — Shared Layout JavaScript Extraction](#phase-t3--shared-layout-javascript-extraction)
   - [Phase T4 — Admin Feature-Level CSS Extraction](#phase-t4--admin-feature-level-css-extraction)
   - [Phase T5 — Forum and Microblogging CSS Extraction](#phase-t5--forum-and-microblogging-css-extraction)
   - [Phase T6 — Admin Feature-Level JavaScript Extraction](#phase-t6--admin-feature-level-javascript-extraction)
   - [Phase T7 — Forum and Microblogging JavaScript Extraction](#phase-t7--forum-and-microblogging-javascript-extraction)
   - [Phase T8 — Inline Style Attribute Replacement](#phase-t8--inline-style-attribute-replacement)
4. [Validation Reference](#4-validation-reference)
5. [Risk Register](#5-risk-register)

---

## 1. Current State and Problems

### 1.1 Template Inventory

```
y_web/templates/ (83 files, 46,371 lines total — pre-T2 baseline)
├── admin/           51 files  — admin dashboard, settings, experiment controls
│   └── tutorials/  13 files  — interactive tour overlays (included in the 51)
├── error_pages/      4 files  — HTTP 400/403/404/500
├── forum/           12 files  — discussion board interface
│   └── components/  4 files  — reusable post/comment/thread partials
├── login/            2 files  — authentication pages
└── microblogging/   14 files  — social-feed interface
    └── components/  5 files  — reusable post/thread/suggestion partials
```

### 1.2 Mixing Metrics

| Concern | Occurrences | Files affected |
|---------|------------:|---------------:|
| Inline `<style>` blocks | 73 | 35 / 83 (42 %) |
| Inline `style=` attributes | 2,827 | 63 / 83 (76 %) |
| Inline `<script>` blocks (non-external) | 148 | 50 / 83 (60 %) |
| External CSS `<link>` references | ~15 per page | via shared includes |
| External JS `<script src>` references | ~18 per page | via shared includes |

### 1.3 Top Offenders

#### Inline `style=` attribute density

| Template | `style=` count |
|----------|---------------:|
| `admin/settings.html` | 205 |
| `admin/experiment_details_forum.html` | 200 |
| `admin/experiment_details.html` | 191 |
| `admin/tutorials/tutorial_overlay.html` | 186 |
| `admin/clients_forum.html` | 174 |
| `admin/dashboard.html` | 157 |
| `admin/clients.html` | 152 |
| `admin/clients_hpc.html` | 151 |
| `microblogging/components/posts.html` | 60 |
| `forum/components/posts.html` | 56 |

#### Inline `<style>` block count per file

| Template | `<style>` blocks | Approximate lines |
|----------|---------------:|------------------:|
| `admin/head.html` | 1 | 200 |
| `admin/dash_head.html` | 1 | 180 |
| `admin/settings.html` | 4 | ~250 |
| `admin/miscellanea.html` | 5 | ~200 |
| `admin/clients*.html` (×3) | 1–6 each | ~150 total |
| `admin/experiment_details*.html` (×2) | 3 each | ~120 total |
| `forum/components/posts.html` | 1 | ~40 |
| `microblogging/interview.html` | 1 | ~30 |

#### Inline `<script>` block density (non-external)

| Template | Inline scripts |
|----------|---------------:|
| `admin/miscellanea.html` | 20 |
| `admin/population_details.html` | 10 |
| `admin/experiment_details.html` | 9 |
| `admin/experiment_details_forum.html` | 8 |
| `admin/settings.html` | 5 |
| `admin/populations.html` | 6 |
| `admin/clients_hpc.html` | 6 |
| `admin/head.html` | 2 |
| `admin/dash_head.html` | 3 |
| `microblogging/feed.html` | 3 |
| `microblogging/interest.html` | 3 |
| `microblogging/hashtag.html` | 3 |
| `microblogging/emotions.html` | 3 |

### 1.4 Structural Problems

1. **Duplicated responsive CSS**: Mobile sidebar styles (~200 lines) appear in both
   `admin/head.html` (lines 190–389) and `admin/dash_head.html` (line 419+), multiplied
   across all 35+ admin pages that include both files.

2. **Business logic in templates**: Functions like `openExternalUrl`, `markBlogPostAsRead`,
   and `dismissBlogPost` are defined inline in `dash_head.html` (lines 66–165) even though
   they belong in a static JS file.

3. **Development artifacts in templates**: The BrowserSync client script
   (`<script id="__bs_script__">`) is conditionally injected inline in 5 templates rather
   than being managed by a single dev-only include.

4. **Unmaintainable component files**: `microblogging/components/posts.html` (60
   `style=` attributes) and `forum/components/posts.html` (56 `style=` attributes) define
   ad-hoc presentation styles that cannot be overridden, tested, or reused independently.

5. **No shared CSS source of truth**: Despite having `admin-layout.css`, `app.css`, and
   `core.css`, many layout rules appear only as inline styles, making it impossible to audit
   or change the visual language in one place.

---

## 2. Target Architecture

### 2.1 New Static File Layout

After all phases are complete, the following new files will exist under `y_web/static/assets/`:

```
y_web/static/assets/
├── css/
│   ├── admin-layout.css        (EXISTING — unchanged)
│   ├── admin-responsive.css    (NEW — T2) sidebar/mobile extracted from head.html
│   ├── admin-components.css    (NEW — T4) admin table, grid, card components
│   ├── admin-settings.css      (NEW — T4) settings page controls
│   ├── admin-clients.css       (NEW — T4) clients / experiment detail tables
│   ├── admin-tutorials.css     (NEW — T4) tutorial overlay components
│   ├── forum-components.css    (NEW — T5) post/comment/thread styles (inside reddit/ namespace)
│   └── social-components.css   (NEW — T5) microblogging post/thread styles
└── js/
    ├── admin-layout.js         (NEW — T3) alert dismissal + sidebar toggle
    ├── admin-nav.js            (NEW — T3) blog-banner + external URL helpers
    ├── admin-settings.js       (NEW — T6) settings page interactions
    ├── admin-miscellanea.js    (NEW — T6) miscellanea page interactions
    ├── admin-experiments.js    (NEW — T6) experiment detail interactions
    ├── admin-populations.js    (NEW — T6) populations page interactions
    ├── admin-clients.js        (NEW — T6) clients page interactions
    ├── reddit/
    │   └── forum-feed.js       (NEW — T7) forum feed interactions (inside reddit/ namespace)
    └── social-feed.js          (NEW — T7) microblogging feed interactions
```

### 2.2 Template Rules (Post-Refactoring)

| Rule | Rationale |
|------|-----------|
| No `<style>` blocks inside `.html` files | All CSS lives in `.css` files |
| No `style=` attributes except for dynamic/computed values set by Jinja2 at render time | Static styles use CSS classes |
| No `<script>` blocks with function definitions | All reusable functions live in `.js` files |
| Allowed inline `<script>`: one-liner data bridges (e.g., `var config = {{ config_json }};`) | Template-to-JS data passing only |
| Allowed BrowserSync `<script id="__bs_script__">`: isolated in one dev include | Single point of control |

---

## 3. Phased Implementation Plan

---

### Phase T1 — Audit Baseline and Tooling

**Goal**: Establish quantitative metrics and tooling to track progress across all phases.

**Steps**:

1. Record baseline metrics by running the commands in [Section 4](#4-validation-reference).
   Save the output to `docs/template_audit_baseline.txt` for comparison after each phase.

2. Add a `Makefile` target (or a shell script at `scripts/audit_templates.sh`) with the
   following checks:

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   ROOT="y_web/templates"
   
   echo "--- Inline <style> blocks ---"
   grep -r '<style>' "$ROOT" --include="*.html" -l | wc -l
   grep -r '<style>' "$ROOT" --include="*.html" | wc -l
   
   echo "--- Inline style= attributes ---"
   grep -r 'style=' "$ROOT" --include="*.html" | wc -l
   
   echo "--- Inline <script> blocks (non-external) ---"
   grep -r '<script>' "$ROOT" --include="*.html" | wc -l
   ```

3. Capture the initial numbers:

   | Metric | Baseline |
   |--------|----------|
   | Files with `<style>` blocks | 35 |
   | Total `<style>` blocks | 73 |
   | Total `style=` attributes | 2,827 |
   | Total inline `<script>` blocks | 148 |

**Success Criteria**:

- [x] `scripts/audit_templates.sh` (or equivalent) executes without error.
- [x] Baseline numbers are recorded and committed.
- [x] Every developer on the team can reproduce the baseline numbers.

---

### Phase T2 — Shared Layout CSS Extraction

**Goal**: Extract the mobile-responsive sidebar CSS that is duplicated across the two master
include files (`admin/head.html` and `admin/dash_head.html`), creating a single authoritative
source used by all 35+ admin pages.

**Files Modified**:

| File | Change |
|------|--------|
| `y_web/templates/admin/head.html` | Remove `<style>` block at lines 190–389; add `<link>` for `admin-responsive.css` |
| `y_web/templates/admin/dash_head.html` | Remove duplicate `<style>` block at line 419+; confirm `admin-responsive.css` already linked via head.html |
| `y_web/static/assets/css/admin-responsive.css` | **New file** — contains all extracted sidebar/mobile rules |

**Extraction Target**:

The following CSS ruleset lives at `admin/head.html` lines 190–389 and must be moved verbatim
into `admin-responsive.css`:

```
.sidebar-toggle-btn { … }
.sidebar-toggle-btn svg { … }
.sidebar-overlay { … }
.sidebar-overlay.active { … }
@media screen and (max-width: 768px) { … }
```

Any identical or near-identical rules found in `dash_head.html` must be removed; the single
copy in `admin-responsive.css` serves both includes.

**Link Placement** in `admin/head.html` (after existing CSS links):

```html
<link rel="stylesheet" href="{{ url_for('static', filename='assets/css/admin-responsive.css') }}"/>
```

**Success Criteria**:

- [x] `admin/head.html` contains zero `<style>` blocks.
- [x] `admin/dash_head.html` contains zero duplicate responsive CSS rules.
- [x] `y_web/static/assets/css/admin-responsive.css` exists and is non-empty.
- [x] Running `grep -r '<style>' y_web/templates/admin/head.html` returns nothing.
- [ ] Visual regression: the admin sidebar toggle still opens/closes correctly on a
  viewport ≤ 768 px (manual or screenshot test).
- [x] Baseline `<style>` block count decreases by at least 2.

---

### Phase T3 — Shared Layout JavaScript Extraction

**Goal**: Remove the three inline `<script>` blocks from `admin/head.html` (alert dismissal,
BrowserSync injector, sidebar toggle) and the three from `admin/dash_head.html` (external-URL
helper, blog-banner helpers, tutorial-button detector), placing them in proper static JS files.

**Sub-phase T3a — Alert Dismissal and Sidebar Toggle**

| File | Change |
|------|--------|
| `y_web/templates/admin/head.html` | Remove inline `<script>` at lines 35–45 (alert dismissal) and lines 391–425 (sidebar toggle) |
| `y_web/static/assets/js/admin-layout.js` | **New file** — contains `alertDismissalInit()` and `sidebarToggle()` functions; auto-invoked on `DOMContentLoaded` |
| `y_web/templates/admin/footer.html` | Add `<script src="…/admin-layout.js">` |

Extracted functions:

```javascript
// admin-layout.js

// Alert dismissal (extracted from head.html lines 36–44)
$(document).ready(function () {
    $(document).on('click', '[data-dismiss="alert"]', function (e) {
        e.preventDefault();
        $(this).closest('.alert').fadeOut(300, function () { $(this).remove(); });
    });
});

// Sidebar toggle (extracted from head.html lines 392–425)
function toggleSidebar() { … }
function closeSidebar() { … }
document.addEventListener('DOMContentLoaded', function () { … });
```

**Sub-phase T3b — Navigation Helper Functions**

| File | Change |
|------|--------|
| `y_web/templates/admin/dash_head.html` | Remove inline `<script>` at lines 66–165 (openExternalUrl, markBlogPostAsRead, dismissBlogPost) and lines 165–296 (tutorial button detector) |
| `y_web/static/assets/js/admin-nav.js` | **New file** — contains all navigation helpers |
| `y_web/templates/admin/footer.html` | Add `<script src="…/admin-nav.js">` |

**Sub-phase T3c — BrowserSync Isolation**

The BrowserSync `<script id="__bs_script__">` block appears in 5 templates:

```
admin/head.html, forum/header.html, microblogging/header.html,
login/login.html, login/register.html
```

Steps:

1. Create `y_web/templates/shared/browser_sync.html` containing exactly the BrowserSync
   snippet once.
2. Replace every occurrence of the raw BrowserSync block with
   `{% include 'shared/browser_sync.html' %}`.

**Success Criteria**:

- [ ] `admin/head.html` contains zero inline `<script>` blocks.
- [ ] `admin/dash_head.html` contains zero inline function definitions.
- [ ] `y_web/static/assets/js/admin-layout.js` and `admin-nav.js` exist.
- [ ] `y_web/templates/shared/browser_sync.html` exists and is included in all 5 files.
- [ ] `grep -rn 'id="__bs_script__"' y_web/templates/` returns exactly 1 result (the new shared partial).
- [ ] Functional regression: alert banners dismiss without page reload; sidebar toggles on mobile; blog-banner dismiss works.
- [ ] Baseline inline `<script>` count decreases by at least 8.

---

### Phase T4 — Admin Feature-Level CSS Extraction

**Goal**: Extract all remaining `<style>` blocks from admin page templates into dedicated
feature CSS files. This phase targets the 26 admin templates that still have `<style>` blocks
after Phase T2.

**Sub-phase T4a — Settings Page**

| File | Change |
|------|--------|
| `admin/settings.html` | Remove 4 `<style>` blocks (lines 3–377, 460–523, 2324–2436, 2776–2817); add link to `admin-settings.css` |
| `y_web/static/assets/css/admin-settings.css` | **New file** — sidebar-box, form-grid, toggle-switch rules |

**Sub-phase T4b — Clients and Experiment Detail Pages**

| File | Change |
|------|--------|
| `admin/clients.html` | Remove 6 `<style>` blocks; add link to `admin-clients.css` |
| `admin/clients_forum.html` | Remove 5 `<style>` blocks; add link to `admin-clients.css` |
| `admin/clients_hpc.html` | Remove 6 `<style>` blocks; add link to `admin-clients.css` |
| `admin/experiment_details.html` | Remove 3 `<style>` blocks; add link to `admin-clients.css` |
| `admin/experiment_details_forum.html` | Remove 3 `<style>` blocks; add link to `admin-clients.css` |
| `y_web/static/assets/css/admin-clients.css` | **New file** — shared table, status-badge, chart-wrapper rules |

**Sub-phase T4c — Populations, Agents, Opinion Pages**

| File | Change |
|------|--------|
| `admin/populations.html` | Remove 7 `<style>` blocks; add link to `admin-components.css` |
| `admin/agents.html` | Remove 2 `<style>` blocks; add link to `admin-components.css` |
| `admin/opinion_configuration*.html` (×3) | Remove style blocks; add link to `admin-components.css` |
| `admin/opinion_evolution.html` | Remove 1 `<style>` block; add link to `admin-components.css` |
| `admin/pages.html` | Remove 4 `<style>` blocks; add link to `admin-components.css` |
| `y_web/static/assets/css/admin-components.css` | **New file** — shared admin card, chart, badge components |

**Sub-phase T4d — Tutorial Overlays**

| File | Change |
|------|--------|
| `admin/tutorials/tutorial_overlay.html` | Remove 1 `<style>` block; add link to `admin-tutorials.css` |
| `admin/tutorials/tutorial_base.html` | Remove `<style>` block; add link to `admin-tutorials.css` |
| `admin/tutorials/exp_details_tutorial.html` | Remove `<style>` block; add link to `admin-tutorials.css` |
| `y_web/static/assets/css/admin-tutorials.css` | **New file** — tutorial step, highlight, tooltip rules |

**Sub-phase T4e — Remaining Admin Templates**

Apply the same extraction pattern to:
- `admin/dashboard.html`
- `admin/miscellanea.html`
- `admin/user_details.html`
- `admin/users.html`
- `admin/jupyter.html`
- `admin/select_experiment.html`
- `admin/client_details.html`, `client_details_forum.html`, `client_details_hpc.html`

CSS rules that appear in three or more files go into `admin-components.css`. Rules unique
to a single page go into a page-specific file (e.g., `admin-miscellanea.css`).

**Success Criteria**:

- [ ] `grep -r '<style>' y_web/templates/admin/ --include="*.html"` returns zero results.
- [ ] All new CSS files (`admin-settings.css`, `admin-clients.css`, `admin-components.css`, `admin-tutorials.css`) exist and pass CSS validation (`npx stylelint` or equivalent).
- [ ] The `<link>` tags for new CSS files are present in the respective templates (verified by `grep`).
- [ ] Baseline `<style>` block count for admin templates reaches 0.
- [ ] Visual regression: admin pages render identically before and after (screenshot comparison or manual walkthrough).

---

### Phase T5 — Forum and Microblogging CSS Extraction

**Goal**: Extract `<style>` blocks from forum and microblogging templates into dedicated
component CSS files.

**Sub-phase T5a — Forum Components**

| File | Change |
|------|--------|
| `forum/components/posts.html` | Remove `<style>` block; add link (via `forum/header.html`) to `forum-components.css` |
| `forum/components/thread-post.html` | Remove `<style>` block; add link to `forum-components.css` |
| `forum/components/comment.html` | Remove `<style>` block; add link to `forum-components.css` |
| `forum/header.html` | Remove `<style>` block; add `<link>` for `forum-components.css` |
| `forum/profile.html` | Remove `<style>` block |
| `forum/interview.html` | Remove `<style>` block |
| `forum/notifications.html` | Remove `<style>` block |
| `y_web/static/assets/css/reddit/forum-components.css` | **New file** — all forum-specific component styles (placed inside the existing `reddit/` namespace, which already hosts `app.css` and `core.css` for the Reddit-like forum interface) |

**Sub-phase T5b — Microblogging Components**

| File | Change |
|------|--------|
| `microblogging/interview.html` | Remove `<style>` block; add link to `social-components.css` |
| `microblogging/header.html` | Confirm no remaining `<style>` blocks |
| `y_web/static/assets/css/social-components.css` | **New file** — all microblogging component styles |

**Note on CSS delivery**: Both `forum/header.html` and `microblogging/header.html` are the
top-level includes for their respective subsections. Add the new CSS `<link>` tags there so
every page in each subsection inherits the styles.

**Success Criteria**:

- [ ] `grep -r '<style>' y_web/templates/forum/ --include="*.html"` returns zero results.
- [ ] `grep -r '<style>' y_web/templates/microblogging/ --include="*.html"` returns zero results.
- [ ] `y_web/static/assets/css/reddit/forum-components.css` and `y_web/static/assets/css/social-components.css` exist.
- [ ] Forum and microblogging pages render without visual regressions (manual or screenshot).
- [ ] Baseline `<style>` block total reaches 0 across all templates.

---

### Phase T6 — Admin Feature-Level JavaScript Extraction

**Goal**: Extract inline `<script>` function blocks from admin page templates into dedicated
feature JS files. Each new JS file is loaded via `footer.html` or a page-specific `<script src>`.

**Sub-phase T6a — Miscellanea Page**

`admin/miscellanea.html` contains 20 inline script blocks (the largest concentration in the
codebase). Each script block manages a distinct UI section (e.g., post creation, reaction
buttons, trend charts, simulation controls).

| File | Change |
|------|--------|
| `admin/miscellanea.html` | Remove all 20 inline `<script>` blocks; add one `<script src="…/admin-miscellanea.js">` at the page bottom |
| `y_web/static/assets/js/admin-miscellanea.js` | **New file** — all extracted functions, namespaced under `AdminMiscellanea.*` |

**Sub-phase T6b — Experiment Detail Pages**

| File | Change |
|------|--------|
| `admin/experiment_details.html` | Remove 9 inline `<script>` blocks; add `<script src="…/admin-experiments.js">` |
| `admin/experiment_details_forum.html` | Remove 8 inline `<script>` blocks; consolidate into same `admin-experiments.js` |
| `y_web/static/assets/js/admin-experiments.js` | **New file** — chart init, filter handlers, export logic |

**Sub-phase T6c — Populations and Clients**

| File | Change |
|------|--------|
| `admin/population_details.html` | Remove 10 inline `<script>` blocks; add `<script src="…/admin-populations.js">` |
| `admin/populations.html` | Remove 6 inline `<script>` blocks; add `<script src="…/admin-populations.js">` |
| `admin/clients_hpc.html` | Remove 6 inline `<script>` blocks; add `<script src="…/admin-clients.js">` |
| `admin/clients.html`, `clients_forum.html` | Remove 3 inline `<script>` each; add `<script src="…/admin-clients.js">` |
| `y_web/static/assets/js/admin-populations.js` | **New file** |
| `y_web/static/assets/js/admin-clients.js` | **New file** |

**Sub-phase T6d — Settings Page**

| File | Change |
|------|--------|
| `admin/settings.html` | Remove 5 inline `<script>` blocks; add `<script src="…/admin-settings.js">` |
| `y_web/static/assets/js/admin-settings.js` | **New file** — tab navigation, form validation, live-preview handlers |

**Sub-phase T6e — Dashboard and Remaining Admin Pages**

Apply the same pattern to `admin/dashboard.html` (5 inline scripts) and any other admin page
still containing inline function definitions after T6a–T6d.

**Namespacing Convention**:

Each new admin JS file must define its functions within a module-level namespace object to
avoid polluting the global scope:

```javascript
// Example: admin-miscellanea.js
var AdminMiscellanea = (function () {
    function initPostCreation() { … }
    function initTrendCharts() { … }
    // …
    return { initPostCreation, initTrendCharts, … };
})();
document.addEventListener('DOMContentLoaded', function () {
    AdminMiscellanea.initPostCreation();
    AdminMiscellanea.initTrendCharts();
});
```

**Success Criteria**:

- [ ] `grep -r '<script>' y_web/templates/admin/ --include="*.html"` returns zero function-definition blocks (only allowed: one-liner data-bridge scripts such as `var config = {{ config_json | tojson }};`).
- [ ] All new JS files exist under `y_web/static/assets/js/`.
- [ ] All extracted functions are namespaced (no bare global function declarations).
- [ ] Admin pages function correctly: experiment charts render, population tables sort, settings forms validate (manual verification or integration test).
- [ ] Baseline inline admin `<script>` count decreases by ≥ 60.

---

### Phase T7 — Forum and Microblogging JavaScript Extraction

**Goal**: Extract inline `<script>` blocks from forum and microblogging templates.

**Sub-phase T7a — Microblogging Feed Pages**

`microblogging/feed.html`, `microblogging/interest.html`, `microblogging/hashtag.html`, and
`microblogging/emotions.html` each contain 3 inline scripts managing infinite scroll,
reaction buttons, and modal dialogs.

| File | Change |
|------|--------|
| `microblogging/feed.html` | Remove 3 inline `<script>` blocks |
| `microblogging/interest.html` | Remove 3 inline `<script>` blocks |
| `microblogging/hashtag.html` | Remove 3 inline `<script>` blocks |
| `microblogging/emotions.html` | Remove 3 inline `<script>` blocks |
| `microblogging/thread.html`, `profile.html`, `friends.html` | Remove 2+ inline `<script>` blocks each |
| `y_web/static/assets/js/social-feed.js` | **New file** — feed init, reaction handlers, modal triggers |

**Sub-phase T7b — Forum Feed Pages**

| File | Change |
|------|--------|
| `forum/feed.html` | Remove inline `<script>` block (line 606) |
| `forum/thread.html` | Remove inline scripts |
| `forum/interview.html` | Remove inline scripts |
| `forum/profile.html` | Remove inline scripts |
| `forum/notifications.html` | Remove inline scripts |
| `y_web/static/assets/js/reddit/forum-feed.js` | **New file** — forum feed init, notification handlers. Placed inside the existing `reddit/` namespace (which already holds `app.js`, `async_updates.js`, etc. for the Reddit-like forum interface) |

**Allowed Exceptions**: Template-to-JavaScript data bridges are acceptable as a narrow
inline pattern. They must be clearly documented with a comment and must contain no function
definitions:

```html
<!-- ALLOWED: data bridge only, no function definitions -->
<script>
var YS_CONFIG = {{ page_config | tojson }};
</script>
<script src="{{ url_for('static', filename='assets/js/social-feed.js') }}"></script>
```

**Success Criteria**:

- [ ] `grep -r '<script>' y_web/templates/forum/ --include="*.html"` returns only data-bridge one-liners or `{% include %}` directives.
- [ ] `grep -r '<script>' y_web/templates/microblogging/ --include="*.html"` returns only data-bridge one-liners.
- [ ] `y_web/static/assets/js/social-feed.js` and `reddit/forum-feed.js` exist.
- [ ] Microblogging and forum feeds load, infinite-scroll works, reactions post correctly (manual or integration test).
- [ ] Baseline inline `<script>` count for forum and microblogging reaches ≤ 5 (data-bridge only).

---

### Phase T8 — Inline Style Attribute Replacement

**Goal**: Replace all `style=` attribute usages in Jinja2 templates with semantic CSS class
names. This is the most labour-intensive phase and should be tackled file-by-file, starting
with the highest-density offenders.

**Priority Order**:

1. `admin/settings.html` (205 attributes) — link to `admin-settings.css`
2. `admin/experiment_details_forum.html` (200) — link to `admin-clients.css`
3. `admin/experiment_details.html` (191) — link to `admin-clients.css`
4. `admin/tutorials/tutorial_overlay.html` (186) — link to `admin-tutorials.css`
5. `admin/clients_forum.html` (174), `clients.html` (152), `clients_hpc.html` (151) — link to `admin-clients.css`
6. `admin/dashboard.html` (157) — link to `admin-components.css`
7. `microblogging/components/posts.html` (60), `forum/components/posts.html` (56) — link to `social-components.css` / `forum-components.css`

**Procedure per file**:

1. Group repeated `style=` values into CSS classes (e.g., `style="display:none"` → class `ys-hidden`; `style="color:#dc3545"` → class `ys-text-danger`).
2. Add the new class rules to the appropriate feature CSS file (already created in T4/T5).
3. Replace `style="…"` in the template with `class="…"`.
4. Exception: `style=` attributes whose value is set by a Jinja2 expression (e.g., `style="width: {{ pct }}%"`) may remain but must be annotated with `{# dynamic #}`.

**Naming Convention for New Utility Classes**:

Use the `ys-` prefix to clearly distinguish YSocial utility classes from Bootstrap or vendor
classes:

```css
/* Example additions to admin-components.css */
.ys-hidden      { display: none; }
.ys-flex-center { display: flex; align-items: center; justify-content: center; }
.ys-text-danger { color: #dc3545; }
.ys-text-muted  { color: #6b7280; }
.ys-mb-0        { margin-bottom: 0; }
```

**Acceptance Threshold**: Because dynamic Jinja2 expressions in `style=` are a legitimate
pattern, the target for this phase is not zero `style=` attributes but a ≥ 80 % reduction:

| Subsection | Baseline | Target (≤) |
|------------|----------:|----------:|
| Admin templates | 2,390 | 478 |
| Forum templates | 141 | 28 |
| Microblogging templates | 213 | 43 |
| Login / Error pages | 83 | 17 |
| **Total** | **2,827** | **566** |

**Success Criteria**:

- [ ] `grep -r 'style=' y_web/templates/ --include="*.html" | wc -l` returns ≤ 566.
- [ ] Every remaining `style=` whose value is static (i.e., not a Jinja2 `{{ … }}` expression) is flagged as a defect in code review.
- [ ] All new `ys-*` CSS classes are documented in a brief style-guide section appended to `admin-components.css` and `social-components.css`.
- [ ] No visual regressions across admin, forum, microblogging, login, and error pages.

---

## 4. Validation Reference

### 4.1 Audit Commands

Run after each phase to track progress:

```bash
# Count files with <style> blocks
grep -r '<style>' y_web/templates/ --include="*.html" -l | wc -l

# Count total <style> blocks
grep -r '<style>' y_web/templates/ --include="*.html" | wc -l

# Count inline style= attributes
grep -r 'style=' y_web/templates/ --include="*.html" | wc -l

# Count inline <script> blocks (non-external)
grep -r '<script>' y_web/templates/ --include="*.html" | wc -l

# Count BrowserSync occurrences (target: exactly 1 after T3c)
grep -r '__bs_script__' y_web/templates/ --include="*.html" | wc -l

# Confirm no <style> blocks remain in admin (after T4)
grep -r '<style>' y_web/templates/admin/ --include="*.html"

# Confirm no <style> blocks remain in forum (after T5)
grep -r '<style>' y_web/templates/forum/ --include="*.html"

# Confirm no <style> blocks remain in microblogging (after T5)
grep -r '<style>' y_web/templates/microblogging/ --include="*.html"
```

### 4.2 Phase-by-Phase Metric Targets

| Phase | `<style>` blocks | `style=` attrs | Inline `<script>` |
|-------|------------------:|---------------:|------------------:|
| Baseline | 73 | 2,827 | 148 |
| After T2 | 71 | 2,827 | 148 |
| After T3 | 71 | 2,827 | 140 |
| After T4 | ~35 | 2,827 | 140 |
| After T5 | 0 | 2,827 | 140 |
| After T6 | 0 | 2,827 | ~20 |
| After T7 | 0 | 2,827 | ≤ 10 |
| After T8 | 0 | ≤ 566 | ≤ 10 |

### 4.3 New File Checklist

After all phases, the following files must exist:

```bash
# CSS
test -f y_web/static/assets/css/admin-responsive.css
test -f y_web/static/assets/css/admin-settings.css
test -f y_web/static/assets/css/admin-clients.css
test -f y_web/static/assets/css/admin-components.css
test -f y_web/static/assets/css/admin-tutorials.css
test -f y_web/static/assets/css/reddit/forum-components.css
test -f y_web/static/assets/css/social-components.css

# JS
test -f y_web/static/assets/js/admin-layout.js
test -f y_web/static/assets/js/admin-nav.js
test -f y_web/static/assets/js/admin-settings.js
test -f y_web/static/assets/js/admin-miscellanea.js
test -f y_web/static/assets/js/admin-experiments.js
test -f y_web/static/assets/js/admin-populations.js
test -f y_web/static/assets/js/admin-clients.js
test -f y_web/static/assets/js/reddit/forum-feed.js
test -f y_web/static/assets/js/social-feed.js

# Shared template partial
test -f y_web/templates/shared/browser_sync.html
```

### 4.4 Flask Integration Test

After each phase, verify the Flask application still renders all templates without error:

```python
# y_web/tests/test_template_separation.py  (add progressively per phase)
import pytest

@pytest.mark.integration
def test_admin_head_no_style_block(admin_head_html):
    """head.html must not contain a <style> block after Phase T2."""
    assert '<style>' not in admin_head_html

@pytest.mark.integration
def test_admin_head_links_responsive_css(admin_head_html):
    """head.html must link admin-responsive.css after Phase T2."""
    assert 'admin-responsive.css' in admin_head_html

@pytest.mark.integration
def test_no_style_blocks_in_admin_templates():
    """No admin template may contain a <style> block after Phase T4."""
    import os, glob
    for path in glob.glob('y_web/templates/admin/**/*.html', recursive=True):
        content = open(path).read()
        assert '<style>' not in content, f'<style> block found in {path}'
```

---

## 5. Risk Register

### Risk R1 — CSS Specificity Conflicts

**Description**: Moving inline styles to external CSS files may change specificity,
causing existing Bootstrap overrides to break.

**Mitigation**:
- Extract rules verbatim first; do not reorganize or simplify during extraction.
- Use `!important` only as a temporary bridge if a specificity conflict is discovered
  during T8; remove it once the root conflict is resolved.
- Visual regression screenshots taken before/after each sub-phase.

---

### Risk R2 — JavaScript Load Order

**Description**: Inline scripts execute synchronously at parse time. Moving them to
external files loaded at the footer changes the execution order and may break code
that relies on immediate execution (e.g., inline scripts that read DOM nodes created
above them).

**Mitigation**:
- Wrap all extracted JS in `document.addEventListener('DOMContentLoaded', …)` or
  `$(document).ready(…)`.
- Load new JS files just before `</body>` (same location as the existing `footer.html`
  script block) to preserve relative ordering.
- Test each extracted file in isolation in a browser console before committing.

---

### Risk R3 — Jinja2 Template Variables Inside Inline Styles

**Description**: Some `style=` attributes contain Jinja2 expressions
(e.g., `style="width: {{ percent }}%"`). These cannot be moved to CSS files.

**Mitigation**:
- During Phase T8, use `grep 'style="[^"]*{{' y_web/templates/` to identify all
  dynamic `style=` attributes.
- Leave dynamic `style=` attributes in place; annotate with `{# dynamic #}`.
- Document the count of approved dynamic exceptions per file.

---

### Risk R4 — Template Caching in Production

**Description**: Deployed environments may cache compiled Jinja2 bytecode. New `<link>`
and `<script>` references will not appear until the server restarts and cache clears.

**Mitigation**:
- Restart the Flask/WSGI server after each deployment.
- Clear `y_web/__pycache__/` and any Jinja2 bytecode cache.
- Add a cache-busting query string to new asset links where relevant
  (e.g., `?v={{ config.ASSET_VERSION }}`).

---

### Risk R5 — Increased HTTP Requests per Page

**Description**: Splitting one large inline block into multiple external files increases
the number of HTTP requests per page load.

**Mitigation**:
- Group related files (e.g., all admin page CSS into `admin-components.css`) to minimise
  the number of new files.
- If the project adopts a build pipeline (Webpack/Vite), the new modular files can be
  bundled back into a single delivery artifact while maintaining source-level separation.

---

*This document supersedes the CSS/JS mixing concerns noted in `TEMPLATES_REFACTORING_PLAN.md`
(which covers only directory reorganization). The two plans are independent and may be executed
in parallel.*
