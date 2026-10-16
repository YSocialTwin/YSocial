# i18n performance check (G1 criterion: overhead under 5%)

Method: `create_app("sqlite")` on a clean copy of the repository at the commit before the i18n branch (`frontend_settings_forum_photo`) and at the Phase 1 head; Flask test client, admin session, 150 requests per page after 10 warm-up requests, median time, three alternating runs. Sandbox timings, so only the ratio is meaningful.

| Page | Before (ms) | After (ms) | Change |
|---|---:|---:|---:|
| `/admin/dashboard` | 4.45 to 4.59 | 4.67 to 4.77 | +2% to +7% |
| `/admin/user_details/<id>` (also gained the language box, +2.5 KB) | 2.65 to 2.84 | 2.83 to 3.25 | +4% to +23% |
| `/admin/experiments` | 2.99 to 3.20 | 3.24 to 3.46 | +2% to +16% |
| `/login` (0.3 ms render) | 0.30 | 0.44 | +0.14 ms |
| 404 page | 2.8 | 2.8 | 0% |

Run-to-run noise is about 5%, so the figures above are at the limit of the criterion for the heavier pages and above it for the trivial login page (+0.14 ms absolute).

Unit costs (Python 3.10, one request context): language selection 9 us once per request, `gettext()` 5 us per call.

## Risk for Phase 2

Today only a few dozen strings go through `gettext`. The admin templates hold about 1,900 unique strings and a page renders hundreds of them: at 5 us each that is 1 to 3 ms on pages that currently render in 3 to 5 ms, well beyond 5%. Before F2-1 starts, the cost per call should be reduced (for example by resolving the translations object once per request and calling it directly instead of going through Flask-Babel's per-call lookup) and the measurement repeated on a converted page. Tracked as an open point of gate G1.
