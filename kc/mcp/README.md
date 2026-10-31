# KC Picasa MCP server

Lets an AI assistant search and read your photo index. It reads `index.db`
read-only, so it works even when KC Picasa is closed. It needs only Python 3.12
(no extra packages) and the repo checkout.

Add it to Claude Code (replace the placeholder path):

```
claude mcp add kc-picasa -- python /path/to/kc-picasa/kc/mcp/kc_picasa_mcp.py
```

Data folder: `--data-dir <dir>`, else env `KC_PICASA_DATA`, else `%LOCALAPPDATA%\PicasaPy`.

Tools: `search_photos`, `photos_on_date`, `on_this_day`, `list_folders`,
`list_albums`, `list_people`, `photo_stats`, `get_photo`. When the app is
running with its local API, `run_action(action, paths)` is listed too.
