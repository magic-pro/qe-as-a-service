FROM python:3.12-slim

WORKDIR /app

# Install Claude Code CLI (Node 20 via NodeSource for current LTS)
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get purge -y --auto-remove curl gnupg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY webhooks/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY webhooks/ ./webhooks/
COPY .claude/agents/ ./.claude/agents/
COPY .claude/commands/ ./.claude/commands/
COPY .claude/settings.json ./.claude/settings.json
COPY artifacts/ ./artifacts/
COPY target-repos/ ./target-repos/
COPY CLAUDE.md .

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "webhooks.receiver:app"]
