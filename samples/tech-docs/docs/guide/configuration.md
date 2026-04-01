# Configuration

Tech Docs is configured through a `tech.yml` file in your project root,
or via environment variables.

## Configuration file

```yaml
# tech.yml
api:
  base_url: https://api.example.com
  timeout: 30

auth:
  token: ${TECH_TOKEN}   # resolved from environment at runtime

logging:
  level: INFO
  format: json
```

## Environment variables

All configuration keys can be set via environment variables using the
`TECH_` prefix and `__` as the separator for nested keys:

| Variable             | Default                      | Description              |
|----------------------|------------------------------|--------------------------|
| `TECH_TOKEN`         | *(required)*                 | API authentication token |
| `TECH_API_BASE_URL`  | `https://api.example.com`    | Base URL for the API     |
| `TECH_API_TIMEOUT`   | `30`                         | Request timeout (seconds)|
| `TECH_LOGGING_LEVEL` | `INFO`                       | Log level                |

## Precedence

Configuration is resolved in this order (highest wins):

1. Environment variables
2. `tech.yml` in the current directory
3. `~/.config/tech/tech.yml` (user-level defaults)
4. Built-in defaults

!!! note "Sensitive values"
    Never commit tokens or secrets to `tech.yml`. Use environment variables
    or a secrets manager instead.

## Validating your configuration

```bash
tech config validate
```

=== "Success output"

    ```
    ✓ Configuration is valid
    ✓ API reachable at https://api.example.com
    ✓ Token accepted
    ```

=== "Failure output"

    ```
    ✗ TECH_TOKEN is not set
    ```
