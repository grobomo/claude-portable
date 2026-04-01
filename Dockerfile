FROM node:20-bookworm

ARG CLAUDE_CODE_VERSION=latest
ARG TZ=America/Los_Angeles
ENV TZ="$TZ"
ENV DEBIAN_FRONTEND=noninteractive

# System packages
RUN apt-get update && apt-get install -y --no-install-recommends \
  less git procps sudo fzf zsh man-db unzip gnupg2 jq nano vim \
  openssh-server rsync curl wget ca-certificates \
  python3 python3-pip python3-venv \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Google Chrome (for Blueprint MCP browser automation)
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
  | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
  > /etc/apt/sources.list.d/google-chrome.list && \
  apt-get update && apt-get install -y --no-install-recommends \
  google-chrome-stable xvfb x11vnc fonts-liberation libgbm1 libnss3 libatk-bridge2.0-0 \
  pcmanfm dbus-x11 \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Python packages
RUN python3 -m pip install --break-system-packages keyring keyrings.alt pyyaml anthropic bcrypt boto3

# Bitwarden Secrets Manager CLI
RUN ARCH=$(dpkg --print-architecture) && \
  if [ "$ARCH" = "amd64" ]; then BWS_ARCH="x86_64"; else BWS_ARCH="aarch64"; fi && \
  curl -sL "https://github.com/bitwarden/sdk-sm/releases/download/bws-v2.0.0/bws-${BWS_ARCH}-unknown-linux-gnu-2.0.0.zip" \
    -o /tmp/bws.zip && \
  unzip -q /tmp/bws.zip -d /usr/local/bin && chmod +x /usr/local/bin/bws && \
  rm /tmp/bws.zip

# AWS CLI v2
RUN ARCH=$(dpkg --print-architecture) && \
  if [ "$ARCH" = "amd64" ]; then \
    curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscli.zip; \
  else \
    curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscli.zip; \
  fi && \
  unzip -q /tmp/awscli.zip -d /tmp && /tmp/aws/install && rm -rf /tmp/aws /tmp/awscli.zip

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  > /etc/apt/sources.list.d/github-cli.list && \
  apt-get update && apt-get install -y gh && \
  apt-get clean && rm -rf /var/lib/apt/lists/*

# SSH server setup
RUN mkdir -p /var/run/sshd && \
  sed -i 's/#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config && \
  sed -i 's/#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && \
  echo "Port 22" >> /etc/ssh/sshd_config && \
  echo "PubkeyAuthentication yes" >> /etc/ssh/sshd_config

# Create claude user (non-root)
RUN useradd -m -s /bin/bash -G sudo claude && \
  echo "claude ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/claude

# uv (Python package manager) — used by dispatcher for spec-kit, general Python tooling
RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh

# Install Claude Code CLI
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# web-chat WebSocket dependency (ws is the only runtime dep)
RUN cd /tmp && npm init -y > /dev/null 2>&1 && npm install ws && \
  mkdir -p /opt/claude-portable/node_modules && \
  cp -r node_modules/ws /opt/claude-portable/node_modules/ && \
  rm -rf /tmp/package* /tmp/node_modules

# Workspace, config, and persistent session dirs
RUN mkdir -p /workspace /home/claude/.claude /home/claude/.ssh /opt/mcp /data/sessions /data/exports /data/chrome-profile && \
  chown -R claude:claude /workspace /home/claude /opt/mcp /data

# Copy scripts and config
COPY --chown=claude:claude scripts/ /opt/claude-portable/scripts/
COPY --chown=claude:claude config/ /opt/claude-portable/config/
# Use config/components.yaml if it exists (user override), otherwise root components.yaml
COPY --chown=claude:claude components.yaml /opt/claude-portable/components-default.yaml
RUN chmod +x /opt/claude-portable/scripts/*.sh

# Fix /opt/claude-portable ownership: node_modules was created as root above,
# but the container runs as claude. The claude user needs to own this directory
# so it can create subdirs (e.g. repos/ cache used by sync-config.sh) and
# run git pull on the scripts directory at startup.
RUN chown -R claude:claude /opt/claude-portable

# Wire session tracking into user's bashrc
RUN echo 'source /opt/claude-portable/config/bashrc-session.sh' >> /home/claude/.bashrc

USER claude
WORKDIR /workspace

ENV CLAUDE_CONFIG_DIR=/home/claude/.claude
ENV HOME=/home/claude

ENTRYPOINT ["/opt/claude-portable/scripts/bootstrap.sh"]
CMD ["sleep", "infinity"]
