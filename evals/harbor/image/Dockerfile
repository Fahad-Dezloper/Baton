# Evaluation image: FalkorDB server + Claude Code + baton + the pristine "shop" fixture.
# Build from the repository root:
#   docker build -t baton-eval:latest -f evals/harbor/image/Dockerfile .
FROM falkordb/falkordb:v4.22.1

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git curl ca-certificates procps bash \
 && rm -rf /var/lib/apt/lists/*

# Claude Code (official installer), exposed on PATH for every user.
RUN curl -fsSL https://downloads.claude.ai/claude-code-releases/bootstrap.sh | bash \
 && ln -sf /root/.local/bin/claude /usr/local/bin/claude \
 && claude --version

# baton: library, MCP server and the host plugin.
COPY src /opt/baton/src
COPY plugin /opt/baton/plugin
RUN python3 -m venv /opt/baton/.venv \
 && /opt/baton/.venv/bin/pip install --no-cache-dir falkordb "mcp>=2,<3" \
 && chmod +x /opt/baton/plugin/bin/*

# The shared codebase every trial starts from, and the scorer.
COPY evals/clash/fixture /app/project
COPY evals/clash/check.py /opt/clash/check.py
RUN cd /app/project \
 && git init -q \
 && git add -A \
 && git -c user.name=eval -c user.email=eval@localhost commit -qm "pristine fixture"

ENV BATON_PYTHON=/opt/baton/.venv/bin/python \
    PYTHONPATH=/opt/baton/src \
    PYTHONDONTWRITEBYTECODE=1

# Idle container: the evaluation harness drives it with exec.
ENTRYPOINT []
CMD ["sleep", "infinity"]
WORKDIR /app/project
