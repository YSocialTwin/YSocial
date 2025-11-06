#!/bin/bash
# Get LLM backend from environment variable (default to ollama)
LLM_BACKEND=${LLM_BACKEND:-ollama}

# Start the appropriate LLM backend in the background
if [ "$LLM_BACKEND" = "vllm" ]; then
    echo "Starting vLLM server..."
    # Note: vLLM server needs to be started separately with appropriate model
    # This is just a placeholder - actual command would be:
    # vllm serve <model_name> --host 0.0.0.0 --port 8000 &
    echo "vLLM backend selected. Please ensure vLLM server is running on port 8000."
else
    echo "Starting Ollama server..."
    OLLAMA_HOST=0.0.0.0:11434 ollama serve &
fi

# Start Flask app in the foreground with the specified backend
exec python /app/y_social.py --host 0.0.0.0 --port 5000 --llm-backend $LLM_BACKEND
