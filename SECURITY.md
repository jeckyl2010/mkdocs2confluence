# Security Policy

## Supported Versions

Only the latest release receives security fixes.

| Version | Supported |
|---------|-----------|
| Latest  | ✅        |
| Older   | ❌        |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Use GitHub's private vulnerability reporting instead:

👉 [Report a vulnerability](https://github.com/jeckyl2010/mkdocs2confluence/security/advisories/new)

You can expect an acknowledgement within a few days and a fix or mitigation within a reasonable timeframe depending on severity.

## Scope

This tool runs locally and publishes Markdown content to Confluence. The main risk surface is:

- **Confluence credentials** — passed via environment variables or `mkdocs.yml`; never logged or stored by this tool
- **URL handling** — source links and edit URIs are validated using `urlparse` hostname matching, not substring checks
- **Dependency vulnerabilities** — monitored automatically via Dependabot and `pip-audit` in CI

### Kroki diagram rendering

When Mermaid or D2 diagrams are present, diagram source code is sent to a [Kroki](https://kroki.io) server for rendering to PNG.

**By default this uses the public `kroki.io` service** — meaning diagram content leaves your machine and is processed by a third-party server.

If your diagrams contain sensitive or proprietary information, configure a self-hosted Kroki instance in `mkdocs.yml`:

```yaml
extra:
  confluence:
    kroki_url: https://kroki.your-company.com
```

Self-hosting Kroki is straightforward via Docker: `docker run -p 8000:8000 yuzutech/kroki`.
