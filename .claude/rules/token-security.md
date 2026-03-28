# Token Security

- NEVER print tokens via `gh auth token`, grep .env, or inline in SSH commands.
- Store all tokens in AWS Secrets Manager, not .env files.
- Graph API access tokens expire in 1 hour. Always use refresh token flow.
- Workers need grobomo's GitHub token (not tmemu) for pushing to grobomo repos.
