# Publishing a plugin

A plugin is a public GitHub repository. Listing it in the
[plugin registry](https://github.com/YSocialTwin/plugin-registry) makes it appear in the
**Plugins** page of every installed YSocial (the next time the application starts), without a new
YSocial or installer release.

## 1. Prepare the repository

- `meta/info.json`: `plugin_name`, `description`, `authors`, `category`, `group`, `repository_url`.
- `meta/registry.json`: only if the plugin adds features (agent types, frontend settings, backend suite);
  see [External Runtime Plugins](external-runtime-management.md#backend-plugin-extension-points).
- Dependencies in `requirements.txt` or `pyproject.toml`. They are installed with the core's package versions
  pinned, so a plugin cannot silently change what YSocial depends on.
- A licence, and a README that explains what the plugin does.

## 2. Try it before it is listed

Point YSocial at a local registry file while you develop:

```bash
cat > /tmp/registry.json <<'JSON'
{"schema_version": 1, "plugins": [{
  "id": "my_plugin", "name": "My Plugin", "category": "backend_extensions",
  "repo": "me/my-plugin", "recipe": "pip-editable", "trust": "community"}]}
JSON
YSOCIAL_PLUGIN_REGISTRY_URL=/tmp/registry.json python y_social.py
```

The plugin shows up in the Plugins page with the Community badge. Private repositories are listed only with
`--development`; a repository that becomes public is detected automatically.

## 3. Publish

Open a pull request on the registry adding one object to `registry.json`; the checks of
`scripts/validate_registry.py --check-repos` run in CI. Fields, recipes and review criteria are described in the
registry's README and CONTRIBUTING.

## What users see

Plugins from repositories that are not the YSocial team's are marked **Community**: the plugin page shows the
repository link and asks for confirmation before installing or updating, because installing a plugin runs its code.
