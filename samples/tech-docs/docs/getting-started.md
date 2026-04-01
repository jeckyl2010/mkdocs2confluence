# Getting Started

This guide walks you through installing the CLI and making your first API call.

## Prerequisites

- Python 3.12 or later
- A valid API token (see [Configuration](guide/configuration.md))

## Installation

```bash
pip install tech-docs-cli
```

Verify the installation:

```bash
tech --version
# tech 1.0.0
```

## Your first request

```python
import tech

client = tech.Client(token="YOUR_TOKEN")
result = client.ping()
print(result)  # {"status": "ok"}
```

!!! tip "Use environment variables"
    Store your token in `TECH_TOKEN` to avoid passing it explicitly:

    ```bash
    export TECH_TOKEN=your-token-here
    ```

## Next steps

- Read the [Installation guide](guide/installation.md) for advanced setup options.
- See the [API reference](reference/api.md) for a full list of endpoints.
