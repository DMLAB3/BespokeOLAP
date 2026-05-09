# Hot Patching
## User
"the paper uses hot patching. how this is impleemted in the code"

## Assistant Summary
In this repo, hot patching is implemented at two layers:

1. Agent-side hot patching of source files during optimization
- The agent is wired with an apply patch tool in main.py.
- Diffs are normalized and dispatched via tools/litellm_apply_patch.py.
- File mutations are applied in tools/workspace_editor.py using apply_diff for create/update.
- Edits are restricted to the configured workspace root.

2. Runtime hot-reload of shared libraries without restarting the host process
- The pipeline in misc/fasttest/db.cpp runs loader and builder with OnChange, and query with Always.
- Reload checks are done in misc/fasttest/utils/pipeline.hpp via plugin.needs_reload().
- Plugin build-ids are compared in misc/fasttest/utils/plugin.hpp.
- Reloading uses dlopen/dlsym and copies libraries to fresh .reload paths to avoid loader caching issues.

End-to-end flow:
- LLM patches code -> compile emits updated .so files -> long-lived DB process receives run command -> changed plugins reload on next run -> validation and optimization continue.
