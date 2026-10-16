# i18n conventions (F0-4)

Rules for writing translatable code in YSocial and its plugins. They follow the multilingual plan and the F0-2/F0-3 spikes. Decisions D3 and D4 of the plan are still pending approval; sections that depend on them are marked *provisional*.

## 1. Python and Jinja (gettext)

- The **English source string is the msgid** (`_('Welcome back')`). No symbolic keys in Python or templates.
- Templates: `{{ _('Text') }}`; with variables `{{ _('Hello %(name)s', name=user.name) }}`; plurals `{{ ngettext('%(n)d post', '%(n)d posts', n) }}`.
- Request-time code uses `flask_babel.gettext`. Module-level constants, form labels and anything evaluated at import time use `lazy_gettext` (import as `_l`).
- **Never build sentences by concatenation or f-strings.** Use named placeholders: `_('Experiment %(name)s created', name=name)`. The 129 f-string `flash()` calls found by the audit are rewritten this way.
- Keep punctuation and markup inside the msgid; do not split a sentence around a link: use `Markup` with a placeholder for the link.
- Do not translate identifiers, route names, database values, log messages and exceptions that are not shown to users.
- Add a translator comment for ambiguous strings: `{# TRANSLATORS: button, not noun #}` or `# TRANSLATORS:` before the call.
- Dates and numbers use Babel (`format_datetime`, `format_number`), never `strftime` or manual separators in user-facing text.

## 2. JavaScript (symbolic keys)

- JS strings are looked up with `YI18n.t('area.key', {name: x})`. Keys are lowercase, dot-separated, `area.thing` (`login.show_password`).
- Catalogs: `y_web/translations/js/<domain>/<lang>.json`, served at `/i18n/<domain>/<lang>.json`. `en.json` is mandatory and is the fallback for missing keys.
- Placeholders use `{name}`. No HTML in catalog values; build markup in JS.
- Load extra domains (plugins) with `YI18n.load('<domain>')`; `t()` searches all loaded domains.
- Code that needs the text at start-up waits for `YI18n.ready`.
- No inline `<script>` blocks: JS stays in static files (project test constraint). Server-rendered values reach JS through `data-*` attributes.

## 3. Catalogs and workflow

- Extraction config: `babel.cfg` (tests and static are ignored). Commands: `pybabel extract -F babel.cfg -o y_web/translations/messages.pot --project=YSocial y_web`, then `pybabel update -i y_web/translations/messages.pot -d y_web/translations`, then `pybabel compile -d y_web/translations`.
- `.po`, `.pot` and the compiled `.mo` of `y_web/translations` are committed (decision at G0: no compile step in build or packaging). Always run `pybabel compile` before committing a catalog change. Translations are kept as `.po` files in the repository and reviewed through pull requests.
- Pilot languages: English and Italian. Supported languages are listed in `y_web/i18n.py` (`SUPPORTED_LOCALES`); a language is added by a catalog plus an entry there.
- Language selection order: user choice stored in the session, `Accept-Language`, English. The admin language is per user (D3, pending approval). The simulation frontend language is set per experiment, with an optional user override (D4).
- Pseudo-locale `en-XA` (planned) is used in CI to catch untranslated strings.
- `<html lang>` always comes from `get_locale()`; never hard-code it.

## 4. Plugins

- A plugin owns a gettext domain and a JS domain named after the plugin, declared by an `i18n` key in its manifest (*provisional*, to be validated in phase 3).
- Manifest strings (names, descriptions, labels) are symbolic keys resolved in the plugin domain, with the English text as fallback.
- Plugins ship their own catalogs; the core never edits plugin catalogs.

## 5. Review checklist

1. No user-visible string left outside `_()`/`t()` in the touched files.
2. No concatenation or f-strings in translated messages.
3. `pybabel extract` shows the new strings; the `.pot` is committed.
4. Italian catalog updated or the strings listed as untranslated in the PR.
5. UI checked with a long language (German-like width) for overflow.
