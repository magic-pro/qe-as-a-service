FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git gh gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @github/copilot@1.0.114 @anthropic-ai/claude-code@2.1.296 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY agent_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY agent_service/ ./agent_service/
COPY .claude/agents/ ./.claude/agents/
COPY .claude/commands/ ./.claude/commands/
COPY .claude/settings.json ./.claude/settings.json
COPY .github/agents/ ./.github/agents/
COPY CLAUDE.md ./
COPY artifacts/ ./artifacts/
COPY docs/ ./docs/
COPY frameworks/ ./frameworks/
COPY okf/ ./okf/
COPY repo-templates/ ./repo-templates/
COPY target-repos/ ./target-repos/
COPY twin/ ./twin/
RUN mkdir -p knowledge/findings knowledge/signals && \
    useradd --create-home --uid 10001 qe && chown -R qe:qe /app && \
    install -d -o qe -g qe -m 700 /home/qe/agent-logs
USER qe
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn agent_service.app:app --host 0.0.0.0 --port ${PORT}"]
