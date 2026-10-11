# Beat Drop — YouTube Music for your AI

Let your AI search YouTube Music, pull up artists and moods, put on a song, and manage your playlists, over MCP (Claude Desktop, Claude Code, or any MCP app).

**Most of it needs no login at all.** Searching, artists, moods and public playlists work out of the box. Connecting your own account is optional, and only needed for your library: your playlists, liked songs and home feed.

## What it can do

| Tool | Login? | What it does |
|---|---|---|
| `ytmusic_search` | no | Songs, albums, artists, playlists |
| `ytmusic_get_artist` | no | An artist's top songs and albums |
| `ytmusic_get_mood_playlists` | no | Mood and genre categories |
| `ytmusic_get_playlist` | no* | Tracks in a playlist (*yours need login) |
| `ytmusic_play` | no | Opens a song in your browser |
| `ytmusic_status` | yes | Checks that your account is really connected |
| `ytmusic_get_playlists` | yes | Your playlists |
| `ytmusic_get_liked_songs` | yes | Your liked songs |
| `ytmusic_get_home` | yes | Your personalised home feed |
| `ytmusic_create_playlist` | yes | Make a playlist (private by default) |
| `ytmusic_add_to_playlist` | yes | Add songs |
| `ytmusic_remove_from_playlist` | yes | Remove songs |
| `ytmusic_like_song` | yes | Like a song |
| `ytmusic_delete_playlist` | yes | Delete a playlist. Your AI must give the playlist's exact title too, so a wrong ID can't delete the wrong one |

## Install

You need **Python 3.10 or newer**.

```bash
pip install -r requirements.txt
```

Then add it to your app.

**Claude Code:**
```bash
claude mcp add beat-drop -- python /full/path/to/beat_drop.py
```

**Claude Desktop** (Settings → Developer → Edit Config), inside `"mcpServers"`:
```json
"beat-drop": {
  "command": "python",
  "args": ["/full/path/to/beat_drop.py"]
}
```

Restart the app. Try: *"Search YouTube Music for Daylight by Taylor Swift and play it."*

## Connect your account (optional)

YouTube Music has no official API, so your AI uses your browser session, the same way your browser does. That session is a **cookie**.

> 🔒 **Treat this cookie like a password.** Anyone who has it can act as you on YouTube. Never paste it into a chat (including with your AI), an issue, a screenshot, or a commit.

### The easy way: sign in once (Chrome or Edge, Node 22+)

```bash
node login.mjs
```

A Chrome or Edge window opens with a separate, empty profile used only by Beat Drop. **Sign in to YouTube Music in it, with your own hands.** That's all: the window closes by itself and your session is saved. Nothing is automated while you sign in, and your password never touches the script.

When your session expires (every few months), refresh it without a window:

```bash
node login.mjs --refresh
```

If that says **NOT SIGNED IN**, run `node login.mjs` again and sign in once more.

> While the window is open, the browser listens on a private local port (`127.0.0.1` only) so the script can read the session. The port closes with the window. The Beat Drop profile lives in `~/.beat-drop/browser-profile`; your everyday browser and its logins are never touched.

### The manual way: paste the cookie

Use this if you don't have Chrome, Edge, or Node.

1. Open https://music.youtube.com and sign in.
2. Open DevTools (**F12**) → **Network** tab.
3. Click **Library** on the page, then click a request named **browse** in the Network list.
4. Under **Request Headers**, find **cookie**, right-click its value → **Copy value**.
5. Run:
   ```bash
   python set_cookie.py
   ```
   Paste when asked. The prompt is hidden, so you won't see it; just press Enter. It tells you when you're connected.
6. **Clear your clipboard** (copy any other text).

Then ask your AI to run `ytmusic_status`. It should say **SIGNED IN**.

### Where your session lives, and how to remove it

- It's stored in **one file**: `~/.beat-drop/auth.json` (set `BEAT_DROP_AUTH` to move it). On macOS/Linux it's created readable by you only (`600`), and the status tool warns you if that ever changes.
- One backup of the previous session is kept beside it (`auth.json.bak`), with the same protection. No pile of old copies.
- Beat Drop never prints, logs, or sends the cookie anywhere except to YouTube Music itself.
- **To disconnect:** delete the `~/.beat-drop` folder (it holds the session file and the Beat Drop browser profile).
- **To kill the session everywhere** (if you think the cookie leaked): sign out of YouTube in that browser, or go to your Google Account → Security → Your devices and sign that session out. The old cookie stops working immediately.

### When it stops working

Browser sessions expire every few months. When `ytmusic_status` says **SIGNED OUT**, run `node login.mjs --refresh` (or repeat the manual steps). The public tools keep working the whole time.

## Good to know

- This uses [ytmusicapi](https://github.com/sigma67/ytmusicapi), an unofficial library. YouTube can change things; if something breaks, update it: `pip install -U ytmusicapi`.
- Use your own account. Your AI acts with your permissions, so the playlist tools change your real library.
- `ytmusic_play` opens the song in your default browser on the computer running the server.
- Song titles, playlist names and descriptions are written by strangers and reach your AI as text. Treat them as content, never as instructions: if a title ever "asks" your AI to change your library, that's the title talking, not you. Writes need explicit IDs, deletes need the exact title, and new playlists are private by default, so the damage a hostile title can do is small, but keep an eye on what your AI changes.

## Troubleshooting

| Problem | Fix |
|---|---|
| Status says **SIGNED OUT** right after connecting | Copy the cookie again from a freshly loaded page (the `browse` request, not another one). |
| "That doesn't look like a YouTube Music cookie" | You copied the header name or a different header. Copy the **value** of `cookie`. |
| Search works but playlists don't | Your account isn't connected yet, or the session expired. Run `set_cookie.py`. |
| Errors after a YouTube update | `pip install -U ytmusicapi` |

## License

MIT
