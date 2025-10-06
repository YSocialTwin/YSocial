# LLM Backend Usage Examples

This document provides practical examples for using YSocial with different LLM backends.

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

### Docker Compose with vLLM
```yaml
# docker-compose.yml
services:
  ysocial:
    image: ysocial:latest
    environment:
      - LLM_BACKEND=vllm
    ports:
      - "5000:5000"
```

Start:
```bash
docker-compose up
```

### Docker Run with Environment Variable
```bash
# With Ollama
docker run -e LLM_BACKEND=ollama -p 5000:5000 ysocial:latest

# With vLLM
docker run -e LLM_BACKEND=vllm -p 5000:5000 ysocial:latest
```

## Multi-Container Setup

### YSocial + vLLM with Docker Compose
```yaml
version: '3.8'
services:
  vllm:
    image: vllm/vllm-openai:latest
    command: --model meta-llama/Llama-3.1-8B-Instruct --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    
  ysocial:
    image: ysocial:latest
    depends_on:
      - vllm
    environment:
      - LLM_BACKEND=vllm
    ports:
      - "5000:5000"
```

## Verifying Your Configuration

### Check if Ollama is Running
```bash
curl http://127.0.0.1:11434/api/version
```

Expected response:
```json
{"version":"0.x.x"}
```

### Check if vLLM is Running
```bash
curl http://127.0.0.1:8000/health
```

Expected response:
```json
{"status":"ok"}
```

### Test the OpenAI-compatible Endpoint

For Ollama:
```bash
curl http://127.0.0.1:11434/v1/models
```

For vLLM:
```bash
curl http://127.0.0.1:8000/v1/models
```

## Troubleshooting

### Issue: Backend not responding
**Solution:** Verify the backend server is running:
- Ollama: `ps aux | grep ollama`
- vLLM: `ps aux | grep vllm`

### Issue: Wrong base URL
**Solution:** Check the `LLM_BACKEND` environment variable:
```bash
echo $LLM_BACKEND
```

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
- Cons: Requires more setup, manual model management

## Getting Help

If you encounter issues:
1. Check the logs for error messages
2. Verify backend server is accessible
3. Ensure models are properly loaded
4. Consult the main README.md for installation instructions
