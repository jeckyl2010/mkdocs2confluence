# Code Blocks

MkDocs Material supports richly annotated fenced code blocks.

## Basic fenced block

```python
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

## With title

```python title="greet.py"
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

## With line numbers

```python linenums="1"
def greet(name: str) -> str:
    return f"Hello, {name}!"

print(greet("world"))
```

## With line highlights

```python linenums="1" hl_lines="2 3"
def greet(name: str) -> str:
    greeting = f"Hello, {name}!"
    return greeting
```

## With title and line numbers

```python title="greet.py" linenums="1"
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

## Shell

```bash
pip install tech-docs-cli
tech --version
```

## JSON

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

## Inline code

Use `pip install` to install packages. The `--upgrade` flag fetches the latest version.

## No language

```
plain text block
no syntax highlighting
```
