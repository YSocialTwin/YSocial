# Desktop installer and launcher

The installer is a small graphical app (one per operating system) that installs YSocial, starts it in its own window, keeps it up to date and removes it. You do not need a terminal or a Python installation. Download it as described in [Installation](installation.md#option-1-desktop-installer).

## First start: install

1. Open the app and press **Install YSocial**. The first time it downloads and prepares a private Python 3.12 environment and installs YSocial into it: it takes a few minutes and needs an internet connection. You can leave the window open.
2. When it finishes the app shows **Start**.

Under *Advanced options* (closed by default) you can choose where YSocial keeps its data. The default is described in [Where the data lives](installation.md#where-the-data-lives).

What is not included, by design: LLM servers (run Ollama, vLLM or any OpenAI-compatible service yourself and enter its address in the admin panel), PostgreSQL (SQLite is the default) and the profile pictures of the simulated agents, which are downloaded the first time they are needed. Plugins are installed later from the admin panel.

## Starting and stopping

**Start** opens YSocial in a dedicated window without browser bars, and the launcher closes itself. Log in with the default administrator (`admin@y-not.social` / `admin`) and change the password.

- **Closing the YSocial window stops YSocial** and every service it started. This can take a few seconds: a "Closing YSocial…" screen tells you it is working, do not force-quit.
- Under *More options* you can choose to open YSocial in your **default browser** instead of its own window. In that case the launcher stays open and shows **Stop**; use it when you are done.
- *Serve requests in parallel* (off by default, on for Windows) lets the interface answer while YSocial is busy; try it if pages react slowly. It applies at the next start. From the command line the same switch is `YSOCIAL_THREADED=1`.
- Other options there: start the Jupyter Notebook server (off by default), check for updates at launch, and the address and port (`127.0.0.1:8080` by default; use `0.0.0.0` only if other computers on your network must reach YSocial).

## Downloads and the profile pictures

- **Saving files.** When you download something in the YSocial window (an experiment export, for example), a save dialog asks where to put the file, and a notice at the bottom right tells you when the download starts and where it was saved. Cancel the dialog to cancel the download.
- **Profile pictures.** The images of the simulated agents (about 490 MB) are downloaded once, in the background, soon after the first start. The *Notifications* page of the admin panel shows a progress bar for it, with **Pause** and **Resume**; an interrupted download continues where it left off.

## Toxicity detection (optional)

Toxicity detection needs PyTorch and a model, which are large downloads, so they are not part of the base install. After installing, the launcher offers **Add toxicity detection** when it is missing; installing it needs an internet connection and some GB of disk space.

## Updating

When the launcher opens it checks the latest GitHub release (switch this off in *More options*). If a newer version exists it shows a notice; **Update** downloads it and installs it over the current one after you confirm. Your data and experiments are kept and the database is upgraded automatically the next time YSocial starts. The version in use is shown at the bottom of the window ("Release vX.Y.Z"). Plugins are updated separately from the plugin page of the admin panel, which also shows the installed and the latest release of each plugin installed from a release.

## Uninstalling

Open the launcher and choose **Uninstall**. You decide whether to delete the data folder (experiments and databases) and the downloaded toxicity models; if you keep them, a later reinstall finds them again. The installer app itself is removed like any other app (drag it to the trash on macOS, *Apps* settings on Windows, your package manager on Linux).

## Troubleshooting

| Symptom | What to do |
|---|---|
| "The app cannot be opened" (macOS) or SmartScreen warning (Windows) | The installers are not code-signed. macOS: right-click the app > *Open*, or `xattr -dr com.apple.quarantine /Applications/YSocial.app`. Windows: *More info* > *Run anyway*. |
| "That port is already in use" | Another program uses the port. Choose a different one under *More options*, or stop the other program (an earlier YSocial may still be running: use **Stop**). |
| YSocial does not start | Open `logs/launch.log` inside the data folder: the last lines say why. |
| Install fails with a network message | Check the connection (the installer downloads Python and packages) and press **Install** again. |
| Not enough disk space | Free some space and retry; the base install needs a few GB, toxicity detection several more. |
| A simulation does not progress | Check the experiment logs in its folder under `y_web/experiments/`. The data folder path may contain spaces (the macOS default does): YSocial handles it, but if you chose a custom folder, avoid network or cloud-synced locations. |
| The window looks frozen when closing | Wait for the "Closing YSocial…" screen to end; stopping the services takes a few seconds. |

Linux needs WebKitGTK 4.1 (`libwebkit2gtk-4.1`) and `xdg-open`; the `.deb` package installs them. Windows needs the WebView2 runtime (included in Windows 10/11).
