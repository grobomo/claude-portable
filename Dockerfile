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

# Python packages
RUN python3 -m pip install --break-system-packages keyring keyrings.alt pyyaml

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

# Install Claude Code CLI
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Workspace, config, and persistent session dirs
RUN mkdir -p /workspace /home/claude/.claude /home/claude/.ssh /opt/mcp /data/sessions /data/exports && \
  chown -R claude:claude /workspace /home/claude /opt/mcp /data

# Copy scripts and config
COPY --chown=claude:claude scripts/ /opt/claude-portable/scripts/
COPY --chown=claude:claude config/ /opt/claude-portable/config/
RUN chmod +x /opt/claude-portable/scripts/*.sh

# Wire session tracking into user's bashrc
RUN echo 'source /opt/claude-portable/config/bashrc-session.sh' >> /home/claude/.bashrc

USER claude
WORKDIR /workspace

ENV CLAUDE_CONFIG_DIR=/home/claude/.claude
ENV HOME=/home/claude

ENTRYPOINT ["/opt/claude-portable/scripts/bootstrap.sh"]
CMD ["sleep", "infinity"]
