---
applyTo: "src/mkdocs_to_confluence/publisher/**/*.py"
---

# Publisher API Rules

- Confluence REST API: prefer v2 (`/wiki/api/v2/`); fall back to v1 (`/wiki/rest/api/`) only if v2 lacks support
- Use `GET /spaces/{id}/pages?title=` to look up a page by title — `spaceId` is not a valid query param on `/pages`
- Kroki: use `POST /mermaid/png` with `Content-Type: text/plain` — never GET (URL length limits are easily exceeded and corporate proxies block Python urllib GET requests)
