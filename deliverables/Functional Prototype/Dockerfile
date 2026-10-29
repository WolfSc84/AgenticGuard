FROM python:3.12-slim

WORKDIR /app

# Create non-root user per enterprise container security standards
RUN groupadd -r agenticguard && useradd -r -g agenticguard agenticguard

COPY agentic_guard/ ./agentic_guard/
COPY demo_walkthrough.py ./
COPY AGENTS.md ./

RUN chown -R agenticguard:agenticguard /app
USER agenticguard

EXPOSE 8000

CMD ["python3", "-m", "agentic_guard.server"]

