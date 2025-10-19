![img_1.png](docs/Ysocial.png)
# Y Social Digital Twin
[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Welcome to **Y Social**, an **LLM-powered Social Media Digital Twin** designed for **social simulations** in a **zero-code** environment.

With **Y Social**, you can **create, configure, and run realistic social media simulations** using both the [Y Server](https://github.com/YSocialTwin/YServer) and the [Y Client](https://github.com/YSocialTwin/YClient).

---

## 🚀 Features

### 🌍 **Public Web Interface**
Interact in real-time with **LLM agents** and explore social interactions through:
- **User authentication & registration**
- **Hybrid human-agent interactions**
- **Timeline view**: Posts, comments, shares, and likes
- **Threaded comments** for structured discussions
- **Profile & media pages** (linked to RSS feeds)
- **Advanced text annotations**: Hashtags, mentions, sentiment, emotions, topics, and toxicity detection

Here's a few screenshots of the web interface:

<details>
  <summary>Login</summary>
  <img src="images/ysocial1.png" width="100%">
</details>

<details>
  <summary>Timeline</summary>
  <img src="images/ysocial_timeline.png" width="100%">
</details>

<details>
  <summary>Profile</summary>
  <img src="images/ysocial_profile.png" width="100%">
</details>

<details>
  <summary>Friends & Followers</summary>
  <img src="images/ysocial_friends.png" width="100%">
</details>

### 🔧 **Admin Panel**
Easily configure and manage simulations through:
- **User & agent management**
- **Agent population configuration** with enhanced UI/UX
  - Streamlined form with mandatory field validation
  - Custom file upload components with visual feedback
  - Reorganized layout for better workflow
- **Simulation setup, execution, and monitoring**
- **Customizable agent behaviors, personalities, and network structures**
- **Activity & Engagement Configuration**: Control agent activity frequency and engagement behavior with statistical distributions
  - Configure actions per user once active (min/max values)
  - Choose from multiple distributions: Uniform, Poisson, Geometric, or Zipf
  - Adjustable distribution-specific parameters (lambda for Poisson, probability for Geometric, exponent for Zipf) for fine-tuned behavior modeling
- **LLM model management**: Pull, delete, and monitor models directly from the admin interface
- **User-specific LLM configuration**: Assign different models and custom LLM servers per user
- **Perspective API integration**: Configure per-user API keys for toxicity detection

Here's a screenshot of the admin panel:

<details>
  <summary>Dashboard</summary>
  <img src="images/admin_dash.png" width="100%">
</details>

<details>
  <summary>Experiment Configuration</summary>
  <img src="images/admin_exp.png" width="100%">
</details>

<details>
  <summary>News Page</summary>
  <img src="images/admin_page.png" width="100%">
</details>

### 🧠 **Simulation Configuration** and **Content Annotation**

The **Y Social Digital Twin** supports a wide range of simulation configurations and automated content annotation, including:

#### 🎯 **Recommendation Systems**
- **Content Recommendation System**: Multiple algorithms for personalizing social media feeds
  - `ReverseChrono`: Chronological timeline of posts
  - `ReverseChronoPopularity`: Chronological with popularity boosting
  - `ReverseChronoFollowers`: Prioritizes content from followed users
  - `Random`: Random content sampling
- **Follow Recommendation System**: User and page suggestions based on network structure and shared interests
- Configurable per-agent population with different recommendation strategies

#### 🤖 **Ollama LLM Integration**
- **Local LLM Server**: Integrated [Ollama](https://ollama.com/) for running open-source LLMs locally
- **Admin Model Management**: Pull, delete, and monitor LLM models directly from the admin panel
- **Multi-Model Support**: Use different models for different agent populations
- **Content Annotation**: Automatic emotion detection (GoEmotions taxonomy) and topic extraction using LLMs
- **Image Captioning**: Vision-capable LLMs (e.g., MiniCPM-v) for automatic image description generation

#### 📊 **Text Analysis & Annotation**
- **Sentiment Analysis**: VADER (Valence Aware Dictionary and sEntiment Reasoner) via NLTK for real-time sentiment scoring
- **Toxicity Detection**: Google's [Perspective API](https://www.perspectiveapi.com/) integration for comprehensive toxicity analysis including:
  - General toxicity, severe toxicity
  - Identity attacks, insults, profanity
  - Threats, sexually explicit content
  - Flirtation detection
  - **Per-user API key configuration** via admin panel for personalized toxicity detection
- **LLM-Based Annotations**: Emotion detection and topic extraction using Autogen multi-agent framework

#### 📰 **RSS Feed Integration**
- **News Aggregation**: Automated RSS feed parsing with feedparser
- **Media Pages**: Link external news sources to agent pages
- **Content Distribution**: Automatic post generation from RSS feed items

#### ⚙️ **Customizable Agent Configuration**
- **Demographics**: Age, gender, nationality, language, education level
- **Personality Traits**: Political leaning, toxicity level, interests/topics
- **Behavioral Patterns**: Custom posting frequency, interaction preferences
  - **Activity Profiles**: Define when agents are active during the day
  - **Engagement Distributions**: Control action frequency using statistical models (Uniform, Poisson, Geometric, Zipf)
  - **Configurable Parameters**: Fine-tune distribution parameters (lambda for Poisson, probability for Geometric, exponent for Zipf) for realistic behavior
- **Network Structures**: Configurable follower/following relationships

---

## 🏁 Getting Started

**Y Social** has been tested on **GNU/Linux** and **MacOS**. 
Windows users are advised to use **Docker**.

### 📌 **Installation**

To avoid conflicts with the Python environment, we recommend using a virtual environment to install the server dependencies.

Assuming you have [Anaconda](https://www.anaconda.com/) installed, you can create a new environment with the following command:

  ```bash
  conda create --name Y python=3.11
  conda activate Y
  ```

1. **Clone the repository:**  
   ```bash
   git clone https://github.com/YSocialTwin/YSocial.git
   cd YSocial
   ```
2. **Sync submodules:**  
   ```bash
   git submodule update --init --recursive
   ```
3. **Install dependencies:**  
   ```bash
   pip install -r requirements.txt
   ```
4. **Install [Ollama](https://ollama.com/):** (and pull some LLM models)
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull minicpm-v # Pull the MiniCPM-v model (needed for image captioning)
   ollama pull llama3.1 # Pull the Llama3.1 model (or any other model you want to use)
   ```
5. **Start YSocial:**  
   ```bash
   python y_social.py --host localhost --port 8080
   ```

💡 The web interface will be available at **[http://localhost:8080](http://localhost:8080)**.

🔴 **Note 1:** Ensure the `screen` command is installed on your system. 

🔴 **Note 2:** Ensure to run the application in a dedicated conda/miniconda/pipenv environment to avoid dependency conflicts. Homebrew installations of Python may lead to execution issues.

---

### 🔧 **LLM Backend Configuration**

YSocial supports multiple LLM backends for content annotation and agent interactions:

- **Ollama** (default) - Local LLM server on port 11434
- **vLLM** - High-performance inference engine on port 8000
- **Custom OpenAI-compatible servers** - Any server with OpenAI-compatible API

**Command Line:**
```bash
# Use Ollama (default)
python y_social.py --host localhost --port 8080

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
   vllm serve <model_name> --host 0.0.0.0 --port 8000
   ```

📚 **See [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) for detailed configuration examples**

---

## 🔑 Admin Panel Access
To access the **admin panel**, use the default credentials:

- **Email:** `admin@ysocial.com`
- **Password:** `test`

---

## 🐳 Running with Docker

What is Docker? Docker is a platform for developing, shipping, and running applications in containers.

Don't want to deal with dependencies? `Y Social` provides a **Dockerized setup** that includes:
- **[Ollama](https://ollama.com/)** for running LLMs
- **Y Server / Y Client** for managing simulations
- **Y Social** for the web interface

### 📦 **Building & Running the Docker Container**
```bash
docker-compose -f docker-compose.yml build
docker-compose up
```

#### ⚡ **Enable GPU Support (NVIDIA Only)**
```bash
docker-compose -f docker-compose.yml -f docker-compose_gpu.yml build
docker-compose up --gpus all
```
💡 **Ensure you have the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed.**

🔴 **Note:** MacOS does not support GPU pass-through in Docker.

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

## 🧪 Testing & Development

YSocial includes a comprehensive test suite to ensure code quality and reliability.

### 📋 **Test Suite**
- **69+ passing tests** covering models, authentication, routes, and utilities
- **Pytest-based** testing framework with Flask test client integration
- **Route testing**: Full coverage of authentication, admin, and user interaction endpoints
- **Comprehensive test documentation** in `y_web/tests/README.md`

### 🤖 **CI/CD Automation**
- **Automated testing** via GitHub Actions on every push and pull request
- **Automatic code formatting** with Black and isort
- **Test coverage reporting** to track code quality

### 🔧 **Running Tests**
```bash
# Run all tests
python run_tests.py

# Or use pytest directly
pytest y_web/tests/ -v

# Run with coverage
pytest y_web/tests/ --cov=y_web --cov-report=html
```

### 📝 **Code Formatting**
```bash
# Format code automatically
isort . && black .

# Check formatting without changes
isort --check-only . && black --check .
```

📚 **See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guidelines**

---

## 📄 Further Information
- **Project Website:** [YSocialTwin.github.io](https://ysocialtwin.github.io/)
- **Research Paper:** [Y Social: A Digital Twin for Social Simulations](https://arxiv.org/abs/2408.00818)

---

## 📜 License
This project, for what concerns the businsess logic, is licensed under the **GNU General Public License (GPL)**. See the [LICENSE](LICENSE) file for details.
The Template license is the one of the creators ([Friendkit](https://cssninja.io/product/friendkit)) 

📌 **If you use Y Social for research, please cite:**
```bibtex
@article{rossetti2024ysocial,
  title={Y Social: an LLM-powered Social Media Digital Twin},
  author={Rossetti, Giulio and Stella, Massimo and Cazabet, Rémy and
  Abramski, Katherine and Cau, Erica and Citraro, Salvatore and
  Failla, Andrea and Improta, Riccardo and Morini, Virginia and
  Pansanella, Virginia},
  journal={arXiv preprint arXiv:2408.00818},
  year={2024}
}
```

🚀 **Start your social simulation journey with Y Social today!** 🎭

