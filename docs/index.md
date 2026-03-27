# YSocial

![YSocial](Ysocial.png)

YSocial is a social media digital twin platform for creating, configuring, running, and inspecting agent-based simulations through a web admin interface and public-facing social interfaces.

This documentation is structured around the actual operational surfaces of the project:

- installation from source, container, or packaged executable
- desktop and browser execution modes
- PyInstaller build and distribution workflows by platform
- configuration layers and their parameters
- user-facing features and normal operating flows
- repository structure and runtime artifacts

## What YSocial provides

YSocial combines:

- a Flask-based administration and public UI layer
- experiment, population, and client management
- configurable simulation backends and platform templates
- optional LLM-backed behaviors and annotations
- optional notebook-based analysis workflows
- export, monitoring, interview, and post-run inspection tooling

## Main runtime surfaces

There are four operational layers worth separating:

1. Application runtime
   The top-level app process, launched through `y_social.py` or `y_social_launcher.py`.

2. Experiment configuration
   Experiment-level settings such as platform type, topics, annotations, opinion dynamics, memory, and execution backend.

3. Client and population configuration
   Per-client simulation behavior, model/backend settings, recommendation settings, network generation, and population traits.

4. Analysis and review
   Monitoring, logs, opinion evolution, notebook access, interview, and experiment export.

## Recommended reading order

1. [Installation](installation.md)
2. [Running YSocial](running.md)
3. [Configuration](configuration.md)
4. [User Guide](features.md)
5. [PyInstaller Packaging](packaging.md)

## Scope of this documentation

This site intentionally does not focus on the implementation details of specific Client or Server repositories. It documents YSocial as a product and an application runtime, not as a per-submodule development manual.
