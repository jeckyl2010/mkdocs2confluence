"""Nav-driven publish pipeline compatibility facade.

The pipeline has two phases:

1. plan — walk the nav tree, compile each page, and decide whether to
   create, update, or skip it in Confluence.
2. execute — carry out the plan, creating/updating pages and uploading
   attachments in nav order so parent pages always exist before their children.
"""

from mkdocs_to_confluence.publisher.executor import (
    _execute_folder_action,
    _execute_page_action,
    _post_process_action,
    _prune_orphans,
    _upload_assets,
    _wire_children,
    execute_publish,
)
from mkdocs_to_confluence.publisher.models import PageAction, PublishReport
from mkdocs_to_confluence.publisher.planner import (
    _extract_ready_flag,
    _find_section_index,
    _plan_nodes,
    _xhtml_hash,
    compile_page,
    plan_publish,
)

__all__ = [
    "PageAction",
    "PublishReport",
    "compile_page",
    "plan_publish",
    "execute_publish",
    "_extract_ready_flag",
    "_xhtml_hash",
    "_find_section_index",
    "_plan_nodes",
    "_upload_assets",
    "_execute_folder_action",
    "_execute_page_action",
    "_wire_children",
    "_post_process_action",
    "_prune_orphans",
]
