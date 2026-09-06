FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agentguard/ agentguard/
COPY agentguard.yaml .
COPY tests/ tests/
CMD ["python", "-m", "agentguard.cli", "check"]
