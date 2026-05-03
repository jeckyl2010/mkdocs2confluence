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
