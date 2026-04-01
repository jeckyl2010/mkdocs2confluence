# Admonitions

MkDocs Material supports several admonition types.

!!! note
    This is a plain note with no custom title.

!!! note "Custom title"
    This note has a custom title.

!!! tip "Pro tip"
    Use environment variables to avoid hardcoding secrets.

!!! warning "Be careful"
    Changing this setting requires a service restart.

!!! danger "Irreversible action"
    Deleting a workspace permanently removes all data.

!!! info "Did you know?"
    You can nest code blocks inside admonitions.

    ```python
    print("hello from inside an admonition")
    ```

??? note "Collapsible admonition"
    This content is hidden by default.

!!! success
    Operation completed successfully.

!!! failure
    The request could not be completed.

!!! bug "Known issue"
    This behaviour is tracked in [#123](https://github.com/example/repo/issues/123).

!!! abstract "Summary"
    A brief summary of the section below.

!!! quote "Attribution"
    > "Any sufficiently advanced technology is indistinguishable from magic."
    >
    > — Arthur C. Clarke
