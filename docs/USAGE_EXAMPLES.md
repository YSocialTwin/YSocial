# YSocial Usage Examples

This document provides practical examples for using YSocial with different configurations.

## Starting YSocial with Ollama (Default)

### Basic Usage
```bash
# Start with default settings (Ollama on localhost:8080)
python y_social.py

# Or explicitly specify Ollama
python y_social.py --llm-backend ollama
```

### With Custom Host and Port
```bash
python y_social.py --host 0.0.0.0 --port 5000 --llm-backend ollama
```

### With PostgreSQL Database
```bash
python y_social.py --db postgresql --llm-backend ollama
```

### Full Configuration
```bash
python y_social.py \
  --host 0.0.0.0 \
  --port 5000 \
  --db postgresql \
  --llm-backend ollama \
  --debug
```

## Starting YSocial with vLLM

### Prerequisites
1. Install vLLM:
   ```bash
   pip install vllm
   ```

2. Start vLLM server with your model:
   ```bash
   vllm serve meta-llama/Llama-3.1-8B-Instruct --host 0.0.0.0 --port 8000
   ```

### Basic Usage
```bash
# Start YSocial with vLLM backend
python y_social.py --llm-backend vllm
```

### With Custom Host and Port
```bash
python y_social.py --host 0.0.0.0 --port 5000 --llm-backend vllm
```

## Docker Usage

### Docker Compose with Ollama (Default)
```yaml
# docker-compose.yml
services:
  ysocial:
    image: ysocial:latest
    environment:
      - LLM_BACKEND=ollama  # Optional, ollama is default
    ports:
      - "5000:5000"
```

Start:
```bash
docker-compose up
```

## Troubleshooting

### Issue: Backend not responding
**Solution:** Verify the backend server is running:
- Ollama: `ps aux | grep ollama`
- vLLM: `ps aux | grep vllm`

### Issue: Models not found
**Solution:** 
- For Ollama: Pull models with `ollama pull <model_name>`
- For vLLM: Ensure model is specified when starting vLLM server

## Advanced Configuration

### Custom Port for Ollama
If running Ollama on a custom port, you'll need to modify the hardcoded URL in:
- `y_web/llm_annotations/content_annotation.py`
- `y_web/llm_annotations/image_annotator.py`

### Custom Port for vLLM
Similarly, if using a custom vLLM port (not 8000), modify the base URL in the same files.

## Performance Considerations

### Ollama
- Best for: Development, testing, small-scale deployments
- Pros: Easy setup, built-in model management
- Cons: May be slower than vLLM for production workloads

### vLLM
- Best for: Production, high-throughput scenarios
- Pros: Optimized inference, better performance
- Cons: Requires more setup, manual model management, single model at a time (no image captioning with minicpm-v) 

---

## Jupyter Lab Integration Examples

YSocial provides integrated Jupyter Lab support with the **[ySights](https://ysocialtwin.github.io/ysights/)** library for analyzing simulation data.

### Starting YSocial with Jupyter Lab

#### Enabled (Default)
```bash
# Jupyter Lab is enabled by default
python y_social.py --host localhost --port 8080
```

#### Disabled (Security Mode)
```bash
# Disable Jupyter Lab for security-sensitive environments
python y_social.py --host localhost --port 8080 --no_notebook
```

### Full Configuration Examples

#### Development Environment with Jupyter Lab
```bash
python y_social.py \
  --host 0.0.0.0 \
  --port 5000 \
  --db sqlite \
  --llm-backend ollama \
  --debug
# Jupyter Lab enabled by default
```

#### Production Environment without Jupyter Lab
```bash
python y_social.py \
  --host 0.0.0.0 \
  --port 8080 \
  --db postgresql \
  --llm-backend vllm \
  --no_notebook
# Jupyter Lab disabled for security
```

### Using Jupyter Lab with Experiments

1. **Start YSocial** with Jupyter Lab enabled (default or without `--no_notebook` flag)

2. **Create and start an experiment** from the admin panel at `http://localhost:8080/admin`

3. **Launch Jupyter Lab** for your experiment:
   - Navigate to experiment details page
   - Click "Launch Jupyter Lab" button
   - Jupyter Lab opens with preconfigured database connection

4. **Access the starter notebook**:
   - Open `start_here.ipynb` in the Jupyter Lab interface
   - Database connection is automatically configured via environment variable
   - Run cells to explore simulation data

### Using ySights Library

The **ySights** library is automatically available in Jupyter Lab instances. Here's a quick example:

```python
import os
from ysights import YDataHandler

# Database connection is automatically configured
db = os.getenv("DB")
ydh = YDataHandler(db)

# Get simulation time range
time_range = ydh.time_range()
print(f"Simulation runs from round {time_range['min_round']} to {time_range['max_round']}")

# Get all agents
agents = ydh.agents()
print(f"Total agents: {len(agents.get_agents())}")

# Get posts by a specific agent
agent_posts = ydh.posts_by_agent(agent_id=1)
print(f"Agent 1 created {len(agent_posts.get_posts())} posts")

# Analyze agent interests
interests = ydh.agent_interests(agent_id=1)
print(f"Agent 1's top interests: {list(interests.items())[:5]}")
```

### Security Considerations

**When to disable Jupyter Lab:**
- Production deployments on public servers
- Environments with sensitive data
- Multi-tenant installations
- Security compliance requirements

**When to enable Jupyter Lab:**
- Development and testing environments
- Research and data analysis workflows
- Controlled/isolated deployments
- Single-user installations

### Troubleshooting Jupyter Lab

#### Issue: Jupyter Lab button not appearing
**Solution:** Ensure YSocial was started without the `--no_notebook` flag

#### Issue: Cannot connect to Jupyter Lab
**Solution:** 
1. Check if Jupyter Lab process is running: View experiment details page
2. Verify port is not blocked by firewall
3. Check application logs for Jupyter startup errors

#### Issue: Database not accessible in notebook
**Solution:** 
1. Verify the `DB` environment variable is set (run `import os; print(os.getenv("DB"))`)
2. Check database file path or connection string
3. Ensure experiment is properly initialized

## Performance Optimization with Ray

YSocial includes optional Ray-based parallel processing to speed up simulations by processing agents concurrently during each hourly time slot.

**⚠️ Experimental Feature**: Ray parallelization may encounter serialization issues with complex agent objects. It automatically falls back to sequential processing if errors occur.

### Basic Usage (Ray Disabled by Default)

```bash
# Ray is disabled by default for compatibility
python y_social.py --host localhost --port 8080

# To enable Ray for parallel processing (experimental), use the --use-ray flag
python y_social.py --host localhost --port 8080 --use-ray

# The simulation will use all available CPU cores when Ray is enabled
```

### Enabling Ray with Environment Variable

If you prefer to use environment variables:

```bash
# Enable Ray via environment variable
export YSOCIAL_USE_RAY=true
python y_social.py --host localhost --port 8080
```

### Disabling Ray (Sequential Processing)

Ray is disabled by default, but if you've enabled it via environment variable and want to disable it:

```bash
# Option 1: Use command-line flag
python y_social.py --host localhost --port 8080 --no-ray

# Option 2: Use environment variable
export YSOCIAL_USE_RAY=false
python y_social.py --host localhost --port 8080
```

### Configuring CPU Usage

By default, Ray uses all available CPU cores. You can limit the number of cores used:

```bash
# Use only 4 CPU cores for Ray processing (Ray must be enabled)
export YSOCIAL_RAY_NUM_CPUS=4
python y_social.py --host localhost --port 8080 --use-ray

# Or inline
YSOCIAL_RAY_NUM_CPUS=4 python y_social.py --host localhost --port 8080 --use-ray
```

### When to Limit CPU Usage

Consider limiting CPU cores when:
- Running on shared infrastructure
- Running other CPU-intensive processes simultaneously
- Need to reserve resources for LLM backends
- Testing performance scaling

### Performance Benefits

Ray parallel processing provides significant speedups for:
- **Large simulations**: 100+ agents see the most benefit
- **Multi-core systems**: Speedup scales with available cores
- **LLM-based actions**: Concurrent API calls to LLM backends
- **Complex agent behaviors**: Agents with multiple actions per time slot

### Example Performance Scenarios

#### Scenario 1: Development (Limited Resources)
```bash
# Use 2 cores for development testing with Ray enabled
YSOCIAL_RAY_NUM_CPUS=2 python y_social.py \
  --host localhost \
  --port 8080 \
  --llm-backend ollama \
  --use-ray
```

#### Scenario 2: Production (Maximum Performance)
```bash
# Enable Ray to use all available cores
python y_social.py \
  --host 0.0.0.0 \
  --port 5000 \
  --db postgresql \
  --llm-backend vllm \
  --use-ray
# Ray automatically uses all CPU cores when enabled
```

#### Scenario 3: Debugging (Sequential Processing)
```bash
# Ray is disabled by default, so no special flag needed for sequential processing
python y_social.py \
  --host localhost \
  --port 8080 \
  --llm-backend ollama
# Sequential processing (Ray disabled)
```
```

### Troubleshooting Ray

#### Issue: Ray initialization fails
**Solution:** 
- Check if another Ray instance is running: `ray stop`
- Verify system resources are available
- Check logs for specific error messages
- Try disabling Ray with `--no-ray` flag

#### Issue: Ray serialization errors (NoneType, module import errors)
**This is a known limitation:** Agent objects with complex dependencies (database connections, file handles, lazy-loaded modules) may not serialize (convert to a format that can be sent between processes) properly across Ray workers.

**Solution:**
- The system automatically falls back to sequential processing
- Ray parallelization is experimental - sequential processing is the stable option
- If you need parallel processing, ensure agent objects are serializable (no database connections, file handles, etc.)

#### Issue: Slower performance with Ray enabled
**Possible causes:**
- Too many CPU cores allocated (overhead from parallelization)
- Small number of agents (parallelization overhead > benefit)
- Database contention from concurrent writes
- Serialization failures causing fallback to sequential mode

**Solution:**
- For small simulations (< 50 agents), use sequential mode (default)
- Limit CPU cores: `YSOCIAL_RAY_NUM_CPUS=4`
- Use faster database (PostgreSQL with tuning)
- Check logs for "falling back to sequential processing" messages

#### Issue: Memory usage is high with Ray
**Solution:**
- Limit CPU cores to reduce concurrent workers
- Monitor with: `ray status`
- Stop Ray between simulations: `ray stop`

## Getting Help

If you encounter issues:
1. Check the logs for error messages
2. Verify backend server is accessible
3. Ensure models are properly loaded
4. Consult the main README.md for installation instructions
5. For Ray issues, system automatically falls back to sequential processing which is stable
