# AI Security Reference

Centralized reference for AI security configuration, guardrails, and access control.

## API Coverage: MINIMAL (5%)

| What exists | What is missing |
|-------------|-----------------|
| ai_security_apply_guardrails (evaluate only) | AI service access control policies |
| | AI application security policies |
| | AI usage monitoring rules |
| | Prompt injection detection config |
| | AI data leakage prevention |
| | AI model inventory |
| | Shadow AI detection settings |

**The single API evaluates guardrails but cannot configure them.**

## Console Navigation

```
V1 Console > AI Security (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| AI Security Overview | AI Security > Overview | Dashboard, AI usage summary |
| AI Service Access Control | AI Security > AI Service Access Control | Allow/block AI services |
| AI Application Security | AI Security > AI Application Security | Protect AI-powered apps |
| AI Usage Monitoring | AI Security > AI Usage Monitoring | Track AI service usage |

## Lab State (joeltest.org, 2026-03-02)

Not fully configured. AI Security is the newest V1 module.

## V1 API Operations

| Operation | Purpose | Type |
|-----------|---------|------|
| ai_security_apply_guardrails | Evaluate AI chat against guardrails | Evaluate (not config) |

### Guardrails API Example

```bash
# Evaluate a chat against AI guardrails
python .claude/skills/v1-api/executor.py ai_security_apply_guardrails \
  messages='[{"role":"user","content":"How do I hack a system?"}]'
```

This returns a guardrail evaluation (block/allow with reason) but does NOT:
- Create guardrail rules
- Modify guardrail settings
- List configured guardrails

## Browser Automation Required For

| Task | Console Path | Priority |
|------|-------------|----------|
| Configure AI service access policies | AI Service Access Control > Add Policy | P1 |
| Set up AI guardrail rules | AI Application Security > Guardrails | P1 |
| Configure AI usage monitoring | AI Usage Monitoring > Settings | P2 |
| View AI usage dashboard | AI Security > Overview | P3 |
| Set prompt injection detection rules | AI Application Security > Detection | P2 |
| Configure data leakage prevention | AI Application Security > DLP | P2 |

## Key Concepts

### AI Service Categories

| Category | Examples |
|----------|---------|
| Generative AI | ChatGPT, Claude, Gemini, Copilot |
| Code Assistants | GitHub Copilot, Cursor, Tabnine |
| Image Generation | DALL-E, Midjourney, Stable Diffusion |
| Enterprise AI | Salesforce Einstein, ServiceNow AI |
| Custom Models | Self-hosted LLMs, fine-tuned models |

### AI Security Controls

| Control | Purpose |
|---------|---------|
| Access Control | Allow/block access to AI services |
| Guardrails | Content filtering for AI inputs/outputs |
| Usage Monitoring | Track who uses which AI services |
| Data Leakage Prevention | Block sensitive data sent to AI |
| Shadow AI Detection | Find unapproved AI service usage |
| Prompt Injection Detection | Detect prompt injection attacks |

### Guardrail Types

| Type | Description |
|------|-------------|
| Topic Filter | Block specific topics (violence, illegal, etc.) |
| PII Filter | Block personal data in prompts |
| Code Filter | Block code exfiltration |
| Jailbreak Detection | Detect prompt injection attempts |
| Custom Rules | Organization-specific content policies |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| AI Security menu not visible | Check V1 license includes AI Security module |
| Guardrail API returns error | Verify API key has AI Security permissions |
| AI usage not tracked | Deploy ZTSA SAM for traffic visibility into AI services |
| Shadow AI not detected | Requires network visibility (ZTSA or proxy) |
| Guardrails too strict | Review and tune topic/PII filters via console |
