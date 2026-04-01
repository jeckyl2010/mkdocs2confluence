# Installation

## System requirements

| Requirement | Minimum  | Recommended |
|-------------|----------|-------------|
| Python      | 3.12     | 3.13+       |
| Memory      | 512 MB   | 2 GB        |
| Disk        | 100 MB   | 1 GB        |

## Installing from PyPI

```bash
pip install tech-docs-cli
```

## Installing from source

Clone the repository and install in editable mode:

```bash
git clone https://github.com/example/tech-docs.git
cd tech-docs
pip install -e ".[dev]"
```

## Verifying the installation

```bash
tech --version
tech doctor
```

!!! warning "Virtual environments"
    Always install inside a virtual environment to avoid dependency conflicts:

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/macOS
    .venv\Scripts\activate     # Windows
    pip install tech-docs-cli
    ```

## Upgrading

```bash
pip install --upgrade tech-docs-cli
```

## Uninstalling

```bash
pip uninstall tech-docs-cli
```
