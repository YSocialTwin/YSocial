# YSocial - Social Media Digital Twin

Welcome to YSocial! This guide will help you get started with using the application.

## Installation

1. **Drag YSocial.app to Applications folder**
   - Simply drag the YSocial icon to the Applications folder icon in this window
   - The application will be installed and ready to use

2. **Launch YSocial**
   - Open YSocial from your Applications folder
   - On first launch, macOS may ask for permission - click "Open"

## Quick Start

YSocial runs as a local web application. When you launch it:
- A web interface will open automatically (desktop mode)
- Or your default browser will open to http://localhost:8080 (browser mode)
- Default login: `admin@ysocial.com` / `test` (change this after first login!)

## Command Line Options

YSocial supports various command-line flags for customization. To use them, open Terminal and run:

```bash
/Applications/YSocial.app/Contents/MacOS/YSocial [OPTIONS]
```

### Common Options

**Mode Selection:**
- `--browser` - Launch in browser mode instead of desktop window
- `--no-browser` - Don't open browser automatically (use with --browser)

**Network Configuration:**
- `-x HOST, --host HOST` - Host to run on (default: localhost)
- `-y PORT, --port PORT` - Port to run on (default: 8080)

**Database:**
- `-D TYPE, --db TYPE` - Database type: `sqlite` (default) or `postgresql`

**LLM Backend:**
- `-l BACKEND, --llm-backend BACKEND` - LLM backend: `ollama` (default) or `vllm`

**JupyterLab:**
- `-n, --no_notebook` - Disable embedded JupyterLab functionality

**Window Customization (Desktop Mode):**
- `--window-width WIDTH` - Window width in pixels (default: 1400)
- `--window-height HEIGHT` - Window height in pixels (default: 900)

**Development:**
- `-d, --debug` - Enable debug mode (more verbose logging)

Please, refer to the online documentation for all options' details and needed dependencies (i.e., PostgreSQL server, ollama/vllm services).

### Usage Examples

**Launch in browser mode:**
```bash
/Applications/YSocial.app/Contents/MacOS/YSocial --browser
```

**Custom port:**
```bash
/Applications/YSocial.app/Contents/MacOS/YSocial --port 9000
```

**Larger window:**
```bash
/Applications/YSocial.app/Contents/MacOS/YSocial --window-width 1920 --window-height 1080
```

**PostgreSQL database:**

Assuming you have a PostgreSQL server running and configured:

```bash
/Applications/YSocial.app/Contents/MacOS/YSocial --db postgresql
```

## Where YSocial Stores Data

YSocial creates the following files and directories in the location where you run it:

- **y_web/** - Application runtime files
- **db/** - SQLite databases (if using SQLite)
  - `dashboard.db` - Admin dashboard database
  - `dummy.db` - Template database
  - Additional databases per experiment
- **logs/** - Application and client log files
- **config_files/** - Configuration files
- **notebooks/** - JupyterLab notebooks (if enabled)
- **data/** - Experiment data and exports

**Important:** The working directory is where you launch YSocial from. If you want to keep your data organized, create a dedicated folder:

```bash
mkdir ~/YSocialData
cd ~/YSocialData
/Applications/YSocial.app/Contents/MacOS/YSocial
```

## Uninstalling YSocial

To completely remove YSocial and all its data:

1. **Run the uninstall script** included in this DMG:
   - Double-click `uninstall.sh` in this DMG window
   - Or from Terminal:
     ```bash
     ./uninstall.sh
     ```
   
2. **The uninstaller will:**
   - Scan for YSocial.app and all data directories
   - **Search for PyInstaller standalone executables**
   - **Search for installation identification file** (installation_id.json used to track aggregated statistics in a fully anonymous way and to provide bug reports and usage statistics)
   - Display all found items with their sizes
   - **Let you select which items to remove** (individually or all)
   - Show selected items and total size to be freed
   - Ask for final confirmation before deletion
   
3. **Selection options:**
   - Enter item numbers separated by spaces (e.g., `1 3 5`)
   - Enter `all` to remove everything
   - Enter `none` or press Enter to cancel
   
4. **Example uninstall session:**
   ```
   Found items:
     [1] [Directory] /Applications/YSocial.app (Size: 150 MB)
     [2] [File] ~/Downloads/dist/YSocial (Size: 180 MB)
     [3] [File] ~/Library/Application Support/YSocial/installation_id.json (Size: 200 B)
     [4] [Directory] ~/YSocial (Size: 45 MB)
     [5] [Directory] ~/Documents/YSocialData (Size: 120 MB)
   
   Your selection: 1 2 3 5
   
   Selected 4 items: (355 MB)
   Confirm? yes
   
   Type 'DELETE' to proceed: DELETE
   ```
   
5. **If you need sudo privileges:**
   ```bash
   sudo ./uninstall.sh
   ```

**Manual Uninstall:**
If you prefer to uninstall manually:
1. Delete `/Applications/YSocial.app` (or PyInstaller executable)
2. Delete any folders where you ran YSocial (containing `y_web/`, `db/`, etc.)
3. Delete installation identification file: `~/Library/Application Support/YSocial/installation_id.json` (macOS)
4. Common locations:
   - `~/YSocial/`
   - `~/Documents/YSocial/`
   - `~/Downloads/YSocial/`
   - `~/Downloads/dist/YSocial` (PyInstaller executable)

## Features

### Admin Panel
- **User Management** - Create and manage users
- **Experiment Setup** - Configure social media simulations
- **Population Management** - Define agent populations
- **LLM Configuration** - Set up and manage LLM models (Ollama/vLLM)
- **Real-time Monitoring** - Track experiment progress
- **JupyterLab Integration** - Analyze data with embedded notebooks

### Simulation
- **Agent-based Modeling** - Simulate social media interactions
- **Multiple Platforms** - Microblogging (Twitter/Bluesky-like), Reddit-like forums
- **LLM-powered Agents** - Agents with personalities and behaviors
- **Network Analysis** - Study information spread and influence
- **Content Annotation** - Sentiment, toxicity, emotion, topic detection

## Documentation

For comprehensive documentation, visit:
- **Website:** https://ysocialtwin.github.io/
- **GitHub:** https://github.com/YSocialTwin/YSocial
- **Research Paper:** https://arxiv.org/abs/2408.00818

## Getting Help

- **GitHub Issues:** https://github.com/YSocialTwin/YSocial/issues
- **Documentation:** https://ysocialtwin.github.io/

## System Requirements

- **macOS:** 10.13 (High Sierra) or later
- **RAM:** 4GB minimum, 8GB+ recommended
- **Storage:** 2GB+ for application and data
- **Python:** 3.11+ (included in app bundle)

## Troubleshooting

**App won't open:**
- Right-click YSocial.app → Open (bypass Gatekeeper)
- Check System Preferences → Security & Privacy

**Port already in use:**
- Use a different port: `--port 9000`
- Or stop the conflicting service

**Can't connect to localhost:**
- Check if firewall is blocking the connection
- Try accessing from another device on your network with `--host 0.0.0.0`

**Database errors:**
- Ensure you have write permissions in the working directory
- Check disk space

**LLM not working:**
- Ensure Ollama is installed and running (if using Ollama backend)
- Check `--llm-backend` setting

## License

YSocial is open source software licensed under GPL v3.
See LICENSE file for details.

## Credits

**Maintainer:** [Giulio Rossetti](https://giuliorossetti.github.io/)

**Year:** 2025

---

For more information and support, visit https://ysocialtwin.github.io/
