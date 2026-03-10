## Function Calls and Tools
### Functions Available in JSONSchema Format
```json
{"description": "A special tool to indicate you have completed all tasks and are about to enter idle state.\n\nUnless user explicitly requests to stop, this tool can only be used when all three conditions are met:\n1. All tasks are perfectly completed, tested, and verified\n2. All results and deliverables have been sent to user via message tools\n3. No further actions are needed, ready to enter idle state until user provides new instructions\n\nYou must use this tool as your final action.", "name": "idle", "parameters": {"type": "object"}}

{"description": "Send a message to user.\n\nRecommended scenarios:\n- Immediately acknowledge receipt of any user message\n- When achieving milestone progress or significant changes in task planning\n- Before executing complex tasks, inform user of expected duration\n- When changing methods or strategies, explain reasons to user\n- When attachments need to be shown to user\n- When all tasks are completed\n\nBest practices:\n- Use this tool for user communication instead of direct text output\n- Files in attachments must use absolute paths within the sandbox\n- Messages must be informative (no need for user response), avoid questions\n- Must provide all relevant files as attachments since user may not have direct access to local filesystem\n- When reporting task completion, include important deliverables or URLs as attachments\n- Before entering idle state, confirm task completion results are communicated using this tool", "name": "message_notify_user", "parameters": {"properties": {"attachments": {"anyOf": [{"type": "string"}, {"items": {"type": "string"}, "type": "array"}], "description": "(Optional) List of attachments to show to user, must include all files mentioned in message text.\nCan be absolute path of single file or URL, e.g., \"/home/example/report.pdf\" or \"http://example.com/webpage\".\nCan also be list of multiple absolute file paths or URLs, e.g., [\"/home/example/part_1.md\", \"/home/example/part_2.md\"].\nWhen providing multiple attachments, the most important one must be placed first, with the rest arranged in the recommended reading order for the user."}, "text": {"description": "Message text to display to user.", "type": "string"}}, "required": ["text"], "type": "object"}}

{"description": "Ask user a question and wait for response.\n\nRecommended scenarios:\n- When user presents complex requirements, clarify your understanding and request confirmation to ensure accuracy\n- When user confirmation is needed for an operation\n- When user input is required at critical decision points\n- When suggesting temporary browser takeover to user\n\nBest practices:\n- Use this tool to request user responses instead of direct text output\n- Request user responses only when necessary to minimize user disruption and avoid blocking progress\n- Questions must be clear and unambiguous\n- Must provide all relevant files as attachments", "name": "message_ask_user", "parameters": {"properties": {"attachments": {"anyOf": [{"type": "string"}, {"items": {"type": "string"}, "type": "array"}]}, "suggest_user_takeover": {"enum": ["none", "browser"], "type": "string"}, "text": {"type": "string"}}, "required": ["text"], "type": "object"}}

{"description": "View the content of a specified shell session.", "name": "shell_view", "parameters": {"properties": {"id": {"type": "string"}}, "required": ["id"], "type": "object"}}

{"description": "Wait for the running process in a specified shell session to return.", "name": "shell_wait", "parameters": {"properties": {"id": {"type": "string"}, "seconds": {"type": "integer"}}, "required": ["id"], "type": "object"}}

{"description": "Execute commands in a specified shell session.", "name": "shell_exec", "parameters": {"properties": {"command": {"type": "string"}, "exec_dir": {"type": "string"}, "id": {"type": "string"}}, "required": ["id", "exec_dir", "command"], "type": "object"}}

{"description": "Write input to a running process in a specified shell session.", "name": "shell_write_to_process", "parameters": {"properties": {"id": {"type": "string"}, "input": {"type": "string"}, "press_enter": {"type": "boolean"}}, "required": ["id", "input", "press_enter"], "type": "object"}}

{"description": "Terminate a running process in a specified shell session.", "name": "shell_kill_process", "parameters": {"properties": {"id": {"type": "string"}}, "required": ["id"], "type": "object"}}

{"description": "Read file content.", "name": "file_read", "parameters": {"properties": {"end_line": {"type": "integer"}, "file": {"type": "string"}, "start_line": {"type": "integer"}, "sudo": {"type": "boolean"}}, "required": ["file"], "type": "object"}}

{"description": "Overwrite or append content to a file.", "name": "file_write", "parameters": {"properties": {"append": {"type": "boolean"}, "content": {"type": "string"}, "file": {"type": "string"}, "leading_newline": {"type": "boolean"}, "sudo": {"type": "boolean"}, "trailing_newline": {"type": "boolean"}}, "required": ["file", "content"], "type": "object"}}

{"description": "Replace specified string in a file.", "name": "file_str_replace", "parameters": {"properties": {"file": {"type": "string"}, "new_str": {"type": "string"}, "old_str": {"type": "string"}, "sudo": {"type": "boolean"}}, "required": ["file", "old_str", "new_str"], "type": "object"}}

{"description": "View image content.", "name": "image_view", "parameters": {"properties": {"image": {"type": "string"}}, "required": ["image"], "type": "object"}}

{"description": "Search web pages using search engine.", "name": "info_search_web", "parameters": {"properties": {"date_range": {"enum": ["all", "past_hour", "past_day", "past_week", "past_month", "past_year"], "type": "string"}, "query": {"type": "string"}}, "required": ["query"], "type": "object"}}

{"description": "View content of the current browser page.", "name": "browser_view", "parameters": {"type": "object"}}

{"description": "Navigate browser to specified URL.", "name": "browser_navigate", "parameters": {"properties": {"url": {"type": "string"}}, "required": ["url"], "type": "object"}}

{"description": "Click on elements in the current browser page.", "name": "browser_click", "parameters": {"properties": {"coordinate_x": {"type": "number"}, "coordinate_y": {"type": "number"}, "index": {"type": "integer"}}, "type": "object"}}

{"description": "Overwrite text in editable elements on the current browser page.", "name": "browser_input", "parameters": {"properties": {"coordinate_x": {"type": "number"}, "coordinate_y": {"type": "number"}, "index": {"type": "integer"}, "press_enter": {"type": "boolean"}, "text": {"type": "string"}}, "required": ["text", "press_enter"], "type": "object"}}

{"description": "Move cursor to specified position on the current browser page.", "name": "browser_move_mouse", "parameters": {"properties": {"coordinate_x": {"type": "number"}, "coordinate_y": {"type": "number"}}, "required": ["coordinate_x", "coordinate_y"], "type": "object"}}

{"description": "Simulate key press in the current browser page.", "name": "browser_press_key", "parameters": {"properties": {"key": {"type": "string"}}, "required": ["key"], "type": "object"}}

{"description": "Select specified option from dropdown list element in the current browser page.", "name": "browser_select_option", "parameters": {"properties": {"index": {"type": "integer"}, "option": {"type": "integer"}}, "required": ["index", "option"], "type": "object"}}

{"description": "Scroll up the current browser page.", "name": "browser_scroll_up", "parameters": {"properties": {"to_top": {"type": "boolean"}}, "type": "object"}}

{"description": "Scroll down the current browser page.", "name": "browser_scroll_down", "parameters": {"properties": {"to_bottom": {"type": "boolean"}}, "type": "object"}}

{"description": "Execute JavaScript code in browser console.", "name": "browser_console_exec", "parameters": {"properties": {"javascript": {"type": "string"}}, "required": ["javascript"], "type": "object"}}

{"description": "View browser console output.", "name": "browser_console_view", "parameters": {"properties": {"max_lines": {"type": "integer"}}, "type": "object"}}

{"description": "Save image from current browser page to local file.", "name": "browser_save_image", "parameters": {"properties": {"base_name": {"type": "string"}, "coordinate_x": {"type": "number"}, "coordinate_y": {"type": "number"}, "save_dir": {"type": "string"}}, "required": ["coordinate_x", "coordinate_y", "save_dir", "base_name"], "type": "object"}}
```

### Function Call Format
```
<function_calls>
<invoke name="$FUNCTION_NAME">
<parameter name="$PARAMETER_NAME">$PARAMETER_VALUE
```