# Privacy

Do not publish private business data, customer content, credentials, personal local paths, private logs, internal metrics, or domain-specific strategy.

Before contributing from a private project:

- scan for blocked names and local paths
- scan for secret-like patterns
- avoid raw `context/`, `projects/`, `logs/`, `wiki/`, `sources/`, `outputs/`, and `state/` exports unless they are sanitized examples
- prefer generic docs, schemas, tools, and skills over raw business artifacts
