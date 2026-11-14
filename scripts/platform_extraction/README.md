# Platform extraction tools

Scripts used to move a platform out of the core (decoupling plan, phases F4-F7). They are kept for whoever continues the
work (phase F9 repeats the operation for the Standard runtimes). They are not part of the application and are not run by
the tests.

* `generate_sdk_wrappers.py` writes the wrapper modules of `y_web/sdk/` from the `SPECS` table (name of the wrapper,
  module and function of the core). Run it from the repository root: `PYTHONPATH=. python scripts/platform_extraction/generate_sdk_wrappers.py`,
  then record the new surface with `UPDATE_SDK_API=1 pytest y_web/tests/test_sdk_contract.py`. `services.py` and `commons/`
  are written by hand.
* `rewrite_imports.py` (`convert()`) rewrites the core imports of a module being moved into `y_web.sdk` imports. A name it
  does not know is reported as *unmapped*: add a wrapper (above) and an entry to its `TABLE`.
* `extract_funcs.py` / `move_admin.py` (`move()`) cut the functions of a platform out of a core module and return the text
  of the new module plus the core helpers it still needs.
* `move_assets.py` / `move_forum.py` / `move_platform_dating.py` are the one-off drivers used for the forum and dating:
  templates retargeted to `@<key>/...`, static files to `platform_static_<key>`, library and routes copied with imports
  rewritten. **The paths at the top (`/tmp/ws/...`) are those of the session that wrote them: edit them first.**

After a move: `black`, `isort --profile black`, `pyflakes` (no undefined names), update
`y_web/tests/data/platform_baseline/moved.json` (templates, url_map, known_platforms), run the suite with and without the
repository.
