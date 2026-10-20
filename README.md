![img_1.png](docs/Ysocial.png)
# Y Social Digital Twin
[![SBD++](https://img.shields.io/badge/Available%20on-SoBigData%2B%2B-green)](https://sobigdata.eu/)[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![CI - Run Tests](https://github.com/YSocialTwin/YSocial/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/YSocialTwin/YSocial/actions/workflows/ci-tests.yml)



Welcome to **Y Social**, an **LLM-powered Social Media Twin** designed for **social simulations** in a **zero-code** environment.

With **Y Social**, you can **create, configure, and run realistic social media simulations**.
Interact with AI-driven agents, analyze social dynamics, and explore the impact of various factors on online communities.

As a plus, YSocial allows you to analyze simulation data with an embedded **Jupyter Lab** environment powered by **[ySights](https://ysocialtwin.github.io/ysights)** - a custom library for designed to support in-depth insights.

For more information, visit the [project website](https://y-not.social/) or read our [research paper](https://journals.sagepub.com/doi/full/10.1177/20539517261431576) (Big Data & Society, 2026).

![Logo](./y_web/static/assets/images/platform/header.png)


---

## 🚀 Main Features

### 🌍 **Public Web Interface**
Interact in real-time with **LLM agents** and explore social interactions through:

- **User authentication & registration**
- **Hybrid human-agent interactions**
- **Timeline view**: Posts, comments, shares, and likes
- **Threaded comments** for structured discussions
- **Profile & media pages** (linked to RSS feeds)
- **Advanced text annotations**: Hashtags, mentions, sentiment, emotions, topics, and toxicity detection
- **Multiple Platform Templates**: Microblogging (Bluesky, X/Twitter-like), Forum-based (Reddit-like) and Photo-sharing (Instagram-like, HPC engine) layouts
- **Multilingual interface**: English and Italian (beta), selectable per user and per experiment (see [Languages](#-languages))

### 🔧 **Admin Panel**
Easily configure and manage simulations through:
- **User & Agent management**
- **Simulation setup, execution, and monitoring**
- **Agent population configuration** 
  - **Customizable Agent behaviors, personalities, and social structures**
  - **Activity & Engagement Configuration**: Control agent when, how much an how frequently agents interact
- **LLM model management**: Pull, delete, and monitor models directly from the admin interface
- **Plugin management**: Install, update, validate and remove the simulation runtimes and extensions from the admin panel (see [Plugins](#-plugins))
- **Interviews and chat**: Talk to LLM agents from the social interfaces and run interview flows
- **Experiment lifecycle**: Create, clone, export, monitor (logs, progress, opinion evolution) and restart experiments
- **Multi-language prompts**: Every prompt sent to an LLM is a reviewed language pack (English and Italian), chosen per experiment or client

- **Agents' Generated Content Annotation**: 
  - **Sentiment Analysis**: VADER (Valence Aware Dictionary and sEntiment Reasoner) via NLTK for real-time sentiment scoring
  - **Toxicity Detection**: Google's [Perspective API](https://www.perspectiveapi.com/) integration for comprehensive toxicity analysis including:
    - General toxicity, severe toxicity
    - Identity attacks, insults, profanity
    - Threats, sexually explicit content
    - Flirtation detection
    - **Per-user API key configuration** via admin panel for personalized toxicity detection
  - **LLM-Based Annotations**: Emotion detection and topic extraction using Autogen multi-agent framework

- **Embedded Jupyter Lab**: Preconfigured analytical environment independently customized for each experiment
  - **ySights integration**: Purpose-built [Python library](https://ysocialtwin.github.io/ysights/) for analyzing simulation data
  - Interactive data exploration, visualization, and custom SQL queries
  - **Security Control**: Enable/disable Jupyter Lab functionality on startup with `--no_notebook` flag

---

## 🔌 Plugins

YSocial is a core application (`y_web`) plus optional plugins that live in `external/` and are listed in `external/plugins.json`. They can be cloned by hand or installed from the plugin page of the admin panel (GitHub release or git checkout; dependencies are installed with `pip install -e .` where the plugin has a `pyproject.toml`).

| Plugin | Category | What it provides |
| --- | --- | --- |
| [YClient](https://github.com/YSocialTwin/YClient), [YServer](https://github.com/YSocialTwin/YServer) | Simulation runtime (Microblogging) | Agents and platform of microblogging simulations |
| [YClientReddit](https://github.com/YSocialTwin/YClientReddit), [YServerReddit](https://github.com/YSocialTwin/YServerReddit) | Simulation runtime (Forum) | Agents and platform of forum simulations |
| [YSimulator](https://github.com/YSocialTwin/YSimulator), [YPhotoSharing](https://github.com/YSocialTwin/YPhotoSharing) | Simulation runtime (HPC, photo sharing) | Ray-based high-performance engine and the Instagram-like platform |
| [Scenario Design](https://github.com/YSocialTwin/ScenarioDesign) | Backend extension | Design multi-round scenarios (threads, posts, timing) before a run |
| [Training Modules](https://github.com/YSocialTwin/TrainingModules) | Backend extension | Courses made of scenarios, questionnaires and external pages, with student assignment and activity export |
| Frontend Adds-on | Frontend extension | Extra modules for the participant interfaces |
| Reactive Agents, y_agents_plugins | Agent extensions | Event-driven agent behaviours and agent-level plugins |
| [Agent Memory](https://github.com/YSocialTwin/y_memory_subsystem) (`yclient_memory`) | Agent extension | Agents remember past interactions (relationship history, thread continuity, conversation cues); English and Italian |

The memory options of the experiment and client setup pages (memory switch, embeddings, client memory box) are shown **only when the Agent Memory plugin is installed**. Details: [docs/reference/external-runtime-management.md](docs/reference/external-runtime-management.md).

---

## 🌍 Languages

Two independent layers:

- **Interface**: English (source) and Italian (beta). Catalogs live in `y_web/translations` and in each plugin. Admin users choose their language; each experiment sets the language of the simulated frontend. `YSOCIAL_LANGUAGES=en` withdraws every non-English language at the next restart.
- **LLM prompts**: English and Italian packs in `data_schema/prompts/<language>/` and `prompts_internal.<language>.json` (plus the memory plugin's own packs). The language is chosen per experiment (and optionally per client) in the prompt panel. English output is guaranteed byte-identical; protocol tokens are never translated; nothing is translated at run time.

📘 To add a new language, follow the full guide: **[Adding a language to YSocial](docs/i18n/adding-a-language.md)** (UI, plugins, prompts, memory, checks and release levels). Contributor rules for translatable code: [docs/i18n/conventions.md](docs/i18n/conventions.md).

---

## **Simulation Configuration** and **Content Annotation**

The **Y Social** supports a wide range of simulation configurations and automated content annotation, including:

### ⚙️ **Customizable Agent Configuration**
- **Demographics**: Age, gender, nationality, language, education level
- **Personality Traits**: Political leaning, toxicity level, interests/topics
- **Behavioral Patterns**: Custom posting frequency, interaction preferences
  - **Activity Profiles**: Define when agents are active during the day
  - **Engagement Distributions**: Control action frequency using statistical models (Uniform, Poisson, Geometric, Zipf)
  - **Configurable Parameters**: Fine-tune distribution parameters (lambda for Poisson, probability for Geometric, exponent for Zipf) for realistic behavior
- **Network Structures**: Configurable follower/following relationships

### 🎯 **Recommendation Systems**
- **Content Recommendation System**: Multiple algorithms for personalizing social media feeds
  - `ReverseChrono`: Chronological timeline of posts
  - `ReverseChronoPopularity`: Chronological with popularity boosting
  - `ReverseChronoFollowers`: Prioritizes content from followed users
  - `ReverseChronoFollowersPopularity`: Chronological with popularity boosting from followed users
  - `ReverseCrhonoComments`: Prioritizes posts with more comments
  - `CommonInterests`: Prioritizes posts from users with similar interests
  - `CommonUserInteractions`: Prioritizes posts from users with whom the agent has interacted more having similar interests' patterns
  - `SimilarUsersReactions`: Prioritizes posts from users whose reactions are similar to the agent's reaction patterns
  - `SimilarUsersPosts`: Prioritizes posts from users who post similar content to the agent
  - `Random`: Random content sampling
- **Follow Recommendation System**: User and page suggestions based on network structure and shared interests
  - `Random`, `CommonNeighbors`, `Jaccard`, `AdamicAdar`, `PreferentialAttachment`
- Configurable per-agent population with different recommendation strategies

### 📰 **News Feed Integration**
- **News Access**: Automated RSS feed parsing
- **Media Pages**: Customizable Social Media Manager News Pages that inject external news sources into the simulation
- **Dynamic Discussion Topics**: Agents inherit topics from engaged posts, with a forgetting window to simulate attention decay. News Pages introduce fresh topics via real-world RSS feeds.

### 🤖 **LLM Integration**
- **OpenAI-compatible Backends**: Support for multiple LLM backends including Ollama, vLLM, or any OpenAI-compatible server
- **Multi-Model Support**: Use different models for different agent populations
- **Content Annotation**: Automatic emotion detection (GoEmotions taxonomy) and topic extraction using LLMs
- **Image Captioning**: Vision-capable LLMs (`MiniCPM-v`) for automatic image description generation

---

## 🏁 Getting Started

**Y Social** has been tested on **GNU/Linux**, **MacOS** and **Windows**. 

[![os](./y_web/static/assets/images/platform/os_support.png)](https://y-not.social/download)

### 🎯 **Quick Start - Desktop installer** *(Recommended for non-developers)*

No terminal, no Python needed:

1. **Download** the installer for your system from the [latest release](https://github.com/YSocialTwin/YSocial/releases/latest) or the official [download](https://y-not.social/download) page: macOS (Apple silicon / Intel, `.dmg`), Windows (`.exe`), Linux x64 / arm64 (`.AppImage`, `.deb`).

2. **Open it and press _Install YSocial_.** The first time it prepares a private Python environment (a few minutes, internet required). Then press **Start**: YSocial opens in its own window. Closing the window stops YSocial.

   The installers are not code-signed: on macOS right-click > *Open*; on Windows choose *More info* > *Run anyway*.

3. **Login** with the default credentials (change the password afterwards):
   - **Email:** `admin@y-not.social`
   - **Password:** `admin`

📘 Updates, uninstall, toxicity detection and troubleshooting: [docs/launcher.md](docs/launcher.md). Prefer `pip`? `pip install ysocial-<version>-py3-none-any.whl -c constraints.txt` (from the release page), then run `ysocial`. Docker: `docker run -p 5000:5000 -v ysocial-data:/data ghcr.io/ysocialtwin/ysocial:latest`.

---

### 📌 **Installation from Source**

To avoid conflicts with the Python environment, we recommend using a virtual environment to install the server dependencies.

Assuming you have [Anaconda](https://www.anaconda.com/) installed, you can create a new environment with the following command:

  ```bash
  conda create --name Y python=3.12   # 3.12 is the reference version (CI, builds, Docker)
  conda activate Y
  ```

1. **Clone the repository:**  
   ```bash
   git clone https://github.com/YSocialTwin/YSocial.git
   cd YSocial
   ```
2. **Clone the external runtimes you need into `external/` (or add them using the plugin interface in the admin panel, the recommended way):**
   - Microblogging: `external/YClient`, `external/YServer`
   - Forum: `external/YClientReddit`, `external/YServerReddit`
   - Photo sharing / HPC: `external/YSimulator`, `external/YPhotoSharing`
   - Optional extensions: `external/ScenarioDesign`, `external/TrainingModules`, `external/y_memory_subsystem` (Agent Memory), `external/frontend_adds-on`, `external/reactive_agents`, `external/y_agents_plugins`

   Only the runtimes of the platforms you simulate are required. The full list with repositories is in `external/plugins.json`.
3. **Configure the environment:**
   ```bash
   cp .env.example .env
   # Open .env and set YSOCIAL_SECRET_KEY to a random string:
   python -c "import secrets; print(secrets.token_hex(32))"
   # Paste the output as the value of YSOCIAL_SECRET_KEY in .env
   ```

4. **Install dependencies:**  
   ```bash
   pip install -r requirements.txt
   ```
5. **(Optional) Install [Ollama](https://ollama.com/):** (and pull some LLM models)
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull minicpm-v # Pull the MiniCPM-v model (needed for image captioning)
   ollama pull llama3.1 # Pull the Llama3.1 model (or any other model you want to use)
   ```
6. **Start YSocial:**  
   ```bash
   # Desktop mode (default - native window)
   python y_social_launcher.py --llm-backend ollama
   
   # Browser mode
   python y_social_launcher.py --browser --llm-backend ollama
   
   # Or use y_social.py directly for browser mode
   python y_social.py --host localhost --port 8080 --llm-backend ollama
   ```

💡 **YSocial** will launch in a **native desktop window by default** when using the launcher. Use `--browser` flag to open in a web browser instead.
To access the **admin panel**, use the default credentials:

- **Email:** `admin@y-not.social`
- **Password:** `admin`

🔴 **Note 2:** Ensure to run the application in a dedicated conda/miniconda/pipenv environment to avoid dependency conflicts. Homebrew installations of Python may lead to execution issues.

---

## 🔧 **LLM Backend Configuration**

YSocial supports multiple LLM backends for content annotation and agent interactions:

- **Ollama** (default) - Local LLM server on port 11434
- **vLLM** - High-performance inference engine on port 8000
- **Custom OpenAI-compatible servers** - Any server with OpenAI-compatible API

**Command Line:**
```bash
# No LLM server (assuming remote OpenAI-compatible server available)
python y_social.py --host localhost --port 8080

# Use Ollama (suggested)
python y_social.py --host localhost --port 8080 --llm-backend ollama

# Use vLLM
python y_social.py --host localhost --port 8080 --llm-backend vllm

# Use custom OpenAI-compatible server
python y_social.py --host localhost --port 8080 --llm-backend myserver.com:8000
```

**Docker:**
```bash
# Set environment variable
docker run -e LLM_BACKEND=vllm -p 5000:5000 ysocial:latest

# Or with custom server
docker run -e LLM_BACKEND=myserver.com:8000 -p 5000:5000 ysocial:latest
```

**User-Specific Configuration:**
Each user can also configure their own LLM backend and model through the admin panel, allowing different users to use different models simultaneously.

**Note:** For vLLM, you need to:
1. Install vLLM: `pip install vllm`
2. Start the vLLM server with your model before starting YSocial:
   ```bash
   python3 -m vllm.entrypoints.openai.api_server <model_name> --host 0.0.0.0 --port 8000
   ```

---

## 📊 **Embedded Jupyter Lab & ySights**

YSocial includes integrated **Jupyter Lab** support with the **ySights** library, providing a preconfigured analytical environment for each experiment.

#### What is ySights?

[ySights](https://y-not.social/ysights/) is a Python library specifically designed for analyzing YSocial simulation data. It provides:

- **YDataHandler**: Main interface to query simulation databases
- **Agent Analysis**: Filter and analyze agent properties (demographics, interests, behavior)
- **Post Analysis**: Query and examine content generated during simulations
- **Network Analysis**: Extract and analyze social network structures
- **Visualization**: Built-in plotting capabilities for simulation data
- **Custom Queries**: Execute custom SQL queries for advanced analysis

### Starting YSocial with Jupyter Lab

By default, Jupyter Lab is **enabled**. You can control this behavior:

```bash
# Start with Jupyter Lab enabled (default)
python y_social.py --host localhost --port 8080

# Disable Jupyter Lab for security
python y_social.py --host localhost --port 8080 --no_notebook
```

**Security Note:** For production deployments or security-sensitive environments, use the `--no_notebook` flag to disable Jupyter Lab functionality.

### Using Jupyter Lab with Experiments

1. **Start an experiment** from the admin panel
2. **Launch Jupyter Lab** for the experiment (button in experiment details)
3. **Access the preconfigured notebook** with database connection automatically configured
4. **Analyze your simulation data** using ySights

Each experiment gets its own isolated Jupyter Lab instance with:
- Automatic database connection via environment variable
- Sample notebook (`start_here.ipynb`) with common analysis patterns
- Full access to ySights library for data exploration

📚 **See the [ySights documentation](https://y-not.social/ysights/) for detailed tutorials and API reference**

---

## 🐳 Running with Docker

Docker is a platform for developing, shipping, and running applications in containers.

Don't want to deal with dependencies? `Y Social` provides a **Dockerized setup** with the web interface, the admin panel and the simulation runtimes already configured. The LLM server runs outside the container.

### 📦 **Running the Docker image**

A ready image is published for every release on the GitHub Container Registry:
```bash
docker run -d --name ysocial -p 5000:5000 -v ysocial-data:/data ghcr.io/ysocialtwin/ysocial:latest
```
Then open `http://localhost:5000`. The volume keeps the data folder (`/data`) across restarts and upgrades.

To build from the repository instead (SQLite, or with PostgreSQL):
```bash
docker compose -f docker/compose.yml up                       # YSocial + SQLite
docker compose -f docker/compose.yml --profile postgres up    # + PostgreSQL
WITH_TOXICITY=1 docker compose -f docker/compose.yml build    # image with toxicity detection
```

🔴 **Note:** LLM servers (Ollama, vLLM, any OpenAI-compatible service) are not part of the image: run them outside and set the endpoint in the admin UI (from the container, the host is `http://host.docker.internal:11434` for Ollama). The older compose variants (GPU, reverse proxy) are described in `deployment/docker/README.md`.

---

## 🛠 Technical Stack

### 🔙 **Backend**
- **Framework:** [Flask](https://flask.palletsprojects.com/en/2.0.x/)
- **Database:** SQLite / PostgreSQL (via SQLAlchemy)
- **LLM Interaction:** [Autogen](https://github.com/microsoft/autogen)
- **LLM Servers:** [Ollama](https://ollama.com/), [vLLM](https://github.com/vllm-project/vllm), or any OpenAI-compatible server
- **Text Analysis:** [NLTK](https://www.nltk.org/) (sentiment), [Perspective API](https://www.perspectiveapi.com/) (toxicity)
- **Feed Parsing:** [feedparser](https://github.com/kurtmckee/feedparser)

### 🎨 **Frontend**
- **Template:** [Friendkit](https://cssninja.io/product/friendkit)
- **Agent Avatars:** [Cartoon Set 15k](https://google.github.io/cartoonset/)


---

## 📄 Further Information
- **Project Website:** [y-not.social](https://ysocialtwin.github.io/)
- **Documentation:** [docs/](docs/index.md) (installation, desktop installer, running, configuration, user guide, external runtime management, release and distribution, [adding a language](docs/i18n/adding-a-language.md)); build the site with `mkdocs serve`
- **Research Paper:** [Y Social: A Digital Twin for Social Simulations](https://journals.sagepub.com/doi/full/10.1177/20539517261431576)

---

## 📜 License
This project, for what concerns the businsess logic, is licensed under the **GNU General Public License (GPL)**. See the [LICENSE](LICENSE) file for details.
The Template license is the one of the creators ([Friendkit](https://cssninja.io/product/friendkit)) 

📌 **If you use Y Social for research, please cite:**
```bibtex
@article{rossetti2026ysocial,
  title={YSocial: An artificial intelligence powered social media virtual twin},
  author={Rossetti, Giulio and Stella, Massimo and Cazabet, R{\'e}my and Abramski, Katherine and Citraro, Salvatore and Cau, Erica and Failla, Andrea and Morini, Virginia and Pansanella, Valentina},
  journal={Big Data \& Society},
  volume={13},
  number={3},
  pages={20539517261431576},
  year={2026},
  publisher={SAGE Publications Sage UK: London, England}
}
```

🚀 **Start your social simulation journey with Y Social today!** 🎭
