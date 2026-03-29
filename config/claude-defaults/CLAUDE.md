## User Preferences

- **Never stop at "what's next?"**: Don't present next steps and wait — implement them. The user rarely needs to provide input. When a stop hook asks what else can be done, DO it, don't list it. Only ask when you truly cannot proceed (missing credentials, ambiguous customer data, destructive actions).
- **Don't ask, just do**: When faced with obvious choices (which instance to use, which approach to take), pick the best one and go. The user does not want to be consulted on implementation details. Only ask when truly ambiguous with real consequences.
- **Be direct**: Skip preambles, get to the point, show results.
- **Review generated output before declaring done**: When generating PDFs, reports, documents, or any visual output, always open and visually verify the result. Check that text is contained within table cells, columns don't overflow, content doesn't overlap, and the layout is clean. Fix any issues before telling the user it's done.

## Environment

- **Projects directory**: All projects are in `/workspace`

## MCP Servers

- **Only mcp-manager in .mcp.json**: NEVER add any MCP server directly to a project's `.mcp.json` except `mcp-manager`. All other MCP servers (blueprint, v1-lite, etc.) are managed through mcp-manager. It handles registration, lifecycle, and tool exposure.

## Git / GitHub

- **Anonymous publishing**: The `grobomo` GitHub account is anonymous. NEVER include real names, email addresses, employer names, or any personally identifying information in commits, READMEs, code comments, or any files pushed to grobomo repos.
- **Global git default is tmemu** (safe default). Grobomo projects override locally in `.git/config`. Do NOT change the global config.
- **Every project with a `.git` must have local git config** (`user.name` + `user.email`) matching its `.github/publish.json` account.

### Two GitHub Accounts

Every project in ProjectsCL1 MUST use the correct GitHub account. **Never guess — check `.github/publish.json` first.**

| Account | Org | Visibility | Use For |
|---------|-----|------------|---------|
| `grobomo` | grobomo | **Public** | Generic tools, API wrappers, utilities, plugins. Shareable with colleagues who lack internal GitHub access. Must contain ZERO customer data, internal infra details, subscription IDs, or PII. |
| `${TMEMU_ACCOUNT}` | ${TMEMU_ACCOUNT} | **Private** | Customer lab environments, deployments with real Azure/AWS configs, anything with customer PII, internal infrastructure, or company-specific workflows. |

**Decision rule:** If a colleague without internal GitHub could safely use the project as-is (no secrets, no customer references, no internal infra), it's **grobomo**. If it touches customer environments, real cloud subscriptions, or contains PII, it's **tmemu**.

### Per-Project Config: `.github/publish.json`

Every project with a git repo MUST have `.github/publish.json`:

```json
{
  "github_account": "grobomo",
  "visibility": "public",
  "reason": "Generic API wrapper, no internal/customer data"
}
```

**Before ANY push, read `.github/publish.json`** to confirm the correct account. If the file doesn't exist, create it and ask the user which account to use.

### Push Workflow (MANDATORY before every `git push`)

Every push must follow ALL steps. No shortcuts.

```bash
# 1. Read the project's account config
cat .github/publish.json   # → tells you grobomo or tmemu

# 2. Verify .github/workflows/secret-scan.yml exists
#    If missing, copy from any other project and customize (e.g. add customer name patterns)

# 3. Run the secret scan LOCALLY before pushing (catch issues before CI does)
bash -c "$(cat .github/workflows/secret-scan.yml | grep -A999 'run: |' | head -80)"
#    Or manually check: grep -rn for subscription IDs, storage keys, SAS tokens, customer names

# 4. Switch gh CLI to the correct account (BOTH accounts are already authenticated in keyring)
gh auth switch --user ${TMEMU_ACCOUNT}   # for tmemu projects
gh auth switch --user grobomo               # for grobomo projects

# 5. Push
git push origin main

# 6. Switch back to default after push
gh auth switch --user ${TMEMU_ACCOUNT}   # switch back if you used grobomo
```

**NEVER ask the user to log in or authenticate.** Both accounts are already saved in the keyring. The only thing needed is `gh auth switch` to set the active account before pushing. If a push hangs, it means the wrong account is active — kill the process and switch.

### GitHub Actions CI (every project)

Every project with a `.git` MUST have `.github/workflows/secret-scan.yml`. It runs on every push/PR to main. **Read the yml file for the full list of checks** — do not duplicate the list here. Customer-specific projects may add extra patterns (e.g. customer name grep).


## mcpm Rules (auto-added by mcp-manager)

- Only mcpm goes in .mcp.json - never add direct MCP server entries
- To reload mcpm: `/mcp` -> select mcp-manager -> Reconnect (never restart Claude Code)
- All servers configured in servers.yaml, listed in .mcp.json servers array
