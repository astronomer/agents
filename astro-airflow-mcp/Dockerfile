# Dockerfile for Airflow MCP Server (Standalone Mode)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies
RUN uv pip install --system -e .

# Expose port for HTTP transport (optional)
EXPOSE 8000

# Set default environment variables
ENV AIRFLOW_API_URL=http://localhost:8080
ENV PYTHONUNBUFFERED=1

# Default command runs in stdio mode (for MCP clients)
CMD ["python", "-m", "astro_airflow_mcp"]

# To run with HTTP transport, override with:
# docker run -p 8000:8000 astro-airflow-mcp python -m astro_airflow_mcp --transport http --host 0.0.0.0 --port 8000
