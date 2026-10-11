"""
Beat Drop — YouTube Music for your AI, over MCP.

Search, artists, moods and public playlists work with NO login.
Your own library (playlists, likes, home feed) needs your YouTube Music session,
which lives in ONE local file on your computer and never leaves it.

  Public reads : ytmusic_search, ytmusic_get_artist, ytmusic_get_mood_playlists,
                 ytmusic_get_playlist (public playlists), ytmusic_play
  Your library : ytmusic_status, ytmusic_get_playlists, ytmusic_get_liked_songs,
                 ytmusic_get_home, ytmusic_create_playlist, ytmusic_add_to_playlist,
                 ytmusic_remove_from_playlist, ytmusic_like_song, ytmusic_delete_playlist

The session file is set up by login.mjs (sign in once) or set_cookie.py (paste). See README.md.
"""

import hashlib
import json
import math
import os
import re
import stat
import time
import webbrowser
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

AUTH_FILE = Path(os.environ.get("BEAT_DROP_AUTH", Path.home() / ".beat-drop" / "auth.json"))

mcp = FastMCP("beat-drop")

# IDs only ever travel as these shapes. Anything else is refused before it reaches a URL or the API.
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
BROWSE_ID = re.compile(r"^[A-Za-z0-9_-]{2,80}$")


def _err(action: str, e: Exception) -> str:
    """Errors name the failure, never the payload: library errors can carry whole account responses."""
    msg = str(e).splitlines()[0] if str(e) else ""
    if len(msg) > 160:
        msg = msg[:160] + " ...[truncated]"
    return f"Error {action}: {type(e).__name__}{': ' + msg if msg else ''}"


def _auth_file_open_to_others() -> bool:
    """True when the session file is readable by other users (POSIX only; Windows uses ACLs)."""
    if os.name != "posix" or not AUTH_FILE.exists():
        return False
    return bool(AUTH_FILE.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))


def get_ytmusic():
    """A client signed in with YOUR session, or None when there is no usable session file."""
    try:
        from ytmusicapi import YTMusic
        if not AUTH_FILE.exists():
            return None
        auth_data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        # Browser sessions need an 'authorization' header (SAPISIDHASH) built from the SAPISID
        # cookie. Build it fresh on every call, so the file only ever has to hold the cookie.
        if isinstance(auth_data, dict) and "cookie" in auth_data:
            sapisid = next((p.strip().split("=", 1)[1] for p in auth_data["cookie"].split(";")
                            if p.strip().startswith("SAPISID=")), None)
            if sapisid:
                origin = auth_data.get("origin", "https://music.youtube.com")
                ts = str(math.floor(time.time()))
                digest = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
                auth_data["authorization"] = f"SAPISIDHASH {ts}_{digest}"
        return YTMusic(auth=auth_data)
    except Exception:
        return None


def get_reader():
    """A client for PUBLIC reads (search, artists, moods, public playlists). No login involved."""
    from ytmusicapi import YTMusic
    return YTMusic()


NOT_SIGNED_IN = "Not signed in. Run `node login.mjs` (or set_cookie.py) to connect your YouTube Music session."


@mcp.tool()
def ytmusic_status() -> str:
    """Check whether YouTube Music is actually signed in.

    Probes a real authenticated endpoint: a session file that exists can still hold an
    expired session, and a client that constructs is not proof of a login.
    """
    return session_state()


def session_state() -> str:
    """The truth about the session, starting with SIGNED IN or SIGNED OUT. Shared by the
    status tool and set_cookie.py, so both judge a login the same way."""
    if not AUTH_FILE.exists():
        return f"SIGNED OUT - no session file at {AUTH_FILE}. Run node login.mjs."
    warning = (" WARNING: the session file is readable by other users on this machine; "
               f"run: chmod 600 {AUTH_FILE}") if _auth_file_open_to_others() else ""

    yt = get_ytmusic()
    if yt is None:
        return f"SIGNED OUT - the session file at {AUTH_FILE} could not be used (malformed or no cookie).{warning}"

    account_err = None
    try:
        info = yt.get_account_info()
    except Exception as e:
        # A signed-out caller gets the anonymous account menu, so the library raises an error
        # carrying that whole payload. Only the error type is useful.
        info, account_err = None, type(e).__name__

    if isinstance(info, dict) and info.get("accountName"):
        return f"SIGNED IN as {info['accountName']}.{warning}"

    try:
        playlists = yt.get_library_playlists(limit=1)
    except Exception as e:
        return (f"SIGNED OUT - the session has expired ({account_err or 'no account name'}; "
                f"library: {type(e).__name__}). Run node login.mjs --refresh.{warning}")
    if playlists:
        return f"SIGNED IN (library reachable; the account endpoint gave no name).{warning}"
    # An empty library is what YouTube serves a caller with no session. It is also what a truly
    # empty account looks like, so this reports SIGNED OUT: a false "signed out" costs one
    # re-connect, a false "signed in" hides a dead session.
    return (f"SIGNED OUT - the library came back empty, which is what YouTube serves a caller with "
            f"no session. Run node login.mjs --refresh.{warning}")


@mcp.tool()
def ytmusic_search(query: str, filter: Optional[str] = None, limit: int = 10) -> str:
    """
    Search YouTube Music for songs, albums, artists, or playlists. No login needed.

    Args:
        query: Search query (song name, artist, etc.)
        filter: Optional filter - "songs", "albums", "artists", "playlists", or None for all
        limit: Max results to return (default 10, max 50)
    """
    limit = max(1, min(int(limit), 50))
    try:
        results = get_reader().search(query, filter=filter, limit=limit)
        if not results:
            return f"No results found for '{query}'"

        output = []
        for i, item in enumerate(results[:limit], 1):
            kind = item.get("resultType", "unknown")
            title = item.get("title", item.get("name", "Unknown"))
            artists = ", ".join(a["name"] for a in item.get("artists", []) or [])
            if kind == "song":
                output.append(f"{i}. [SONG] {title} - {artists} ({item.get('duration', '')}) | ID: {item.get('videoId', '')}")
            elif kind == "video":
                output.append(f"{i}. [VIDEO] {title} - {artists} | ID: {item.get('videoId', '')}")
            elif kind == "album":
                output.append(f"{i}. [ALBUM] {title} - {artists} | ID: {item.get('browseId', '')}")
            elif kind == "artist":
                output.append(f"{i}. [ARTIST] {item.get('artist', title)} | ID: {item.get('browseId', '')}")
            elif kind == "playlist":
                output.append(f"{i}. [PLAYLIST] {title} | ID: {item.get('browseId', '')}")
            else:
                output.append(f"{i}. [{kind.upper()}] {title}")
        return f"Search results for '{query}':\n" + "\n".join(output)
    except Exception as e:
        return _err("searching", e)


@mcp.tool()
def ytmusic_play(video_id: str) -> str:
    """
    Play a song by opening it in your browser.

    Args:
        video_id: The 11-character video ID from search results
    """
    if not VIDEO_ID.match(video_id or ""):
        return f"Refused: '{video_id}' is not a YouTube video ID (11 letters, digits, - or _)."
    url = f"https://music.youtube.com/watch?v={video_id}"
    try:
        webbrowser.open(url)
        return f"Opening: {url}"
    except Exception as e:
        return _err("opening the browser", e)


@mcp.tool()
def ytmusic_get_playlists() -> str:
    """Get your playlists."""
    yt = get_ytmusic()
    if yt is None:
        return NOT_SIGNED_IN
    try:
        playlists = yt.get_library_playlists(limit=50)
        if not playlists:
            return "No playlists found."
        return "Your playlists:\n" + "\n".join(
            f"{i}. {pl.get('title', 'Unknown')} ({pl.get('count', '?')} tracks) | ID: {pl.get('playlistId', '')}"
            for i, pl in enumerate(playlists, 1))
    except Exception as e:
        return _err("getting playlists", e)


@mcp.tool()
def ytmusic_create_playlist(title: str, description: str = "", privacy: str = "PRIVATE") -> str:
    """
    Create a new playlist in your library.

    Args:
        title: Playlist name
        description: Optional description
        privacy: "PRIVATE", "PUBLIC", or "UNLISTED" (default PRIVATE)
    """
    if privacy not in ("PRIVATE", "PUBLIC", "UNLISTED"):
        return "Refused: privacy must be PRIVATE, PUBLIC, or UNLISTED."
    yt = get_ytmusic()
    if yt is None:
        return NOT_SIGNED_IN
    try:
        playlist_id = yt.create_playlist(title, description, privacy_status=privacy)
        return f"Created playlist '{title}' ({privacy}) | ID: {playlist_id}"
    except Exception as e:
        return _err("creating the playlist", e)


@mcp.tool()
def ytmusic_add_to_playlist(playlist_id: str, video_ids: list[str]) -> str:
    """
    Add songs to one of your playlists.

    Args:
        playlist_id: The playlist ID to add to
        video_ids: List of video IDs to add (from search results)
    """
    bad = [v for v in video_ids if not VIDEO_ID.match(v or "")]
    if not BROWSE_ID.match(playlist_id or "") or bad:
        return f"Refused: not a valid playlist ID or video ID(s): {bad or playlist_id}"
    yt = get_ytmusic()
    if yt is None:
        return NOT_SIGNED_IN
    try:
        result = yt.add_playlist_items(playlist_id, video_ids)
        if isinstance(result, dict) and (result.get("status") == "STATUS_SUCCEEDED" or result.get("playlistEditResults")):
            return f"Added {len(video_ids)} song(s) to the playlist."
        return "YouTube Music did not confirm the add. Check the playlist."
    except Exception as e:
        return _err("adding to the playlist", e)


@mcp.tool()
def ytmusic_get_playlist(playlist_id: str, limit: int = 50) -> str:
    """
    Get the tracks in a playlist (yours, or any public one).

    Args:
        playlist_id: The playlist ID
        limit: Max tracks to return (default 50, max 200)
    """
    if not BROWSE_ID.match(playlist_id or ""):
        return f"Refused: '{playlist_id}' is not a playlist ID."
    limit = max(1, min(int(limit), 200))
    yt = get_ytmusic() or get_reader()
    try:
        playlist = yt.get_playlist(playlist_id, limit=limit)
        title, tracks = playlist.get("title", "Unknown"), playlist.get("tracks", [])
        if not tracks:
            return f"Playlist '{title}' is empty."
        total = playlist.get("trackCount") or len(tracks)
        tracks = tracks[:limit]
        lines = [f"Playlist: {title} ({total} tracks, {len(tracks)} shown)"]
        for i, t in enumerate(tracks[:limit], 1):
            artists = ", ".join(a["name"] for a in t.get("artists", []) or [])
            lines.append(f"{i}. {t.get('title', 'Unknown')} - {artists} | ID: {t.get('videoId', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _err("getting the playlist", e)


@mcp.tool()
def ytmusic_remove_from_playlist(playlist_id: str, video_ids: list[str]) -> str:
    """
    Remove songs from one of your playlists.

    Args:
        playlist_id: The playlist ID
        video_ids: List of video IDs to remove
    """
    if not BROWSE_ID.match(playlist_id or ""):
        return f"Refused: '{playlist_id}' is not a playlist ID."
    yt = get_ytmusic()
    if yt is None:
        return NOT_SIGNED_IN
    try:
        # Removal needs each track's setVideoId, which only the playlist itself knows.
        tracks = yt.get_playlist(playlist_id).get("tracks", [])
        to_remove = [{"videoId": t.get("videoId"), "setVideoId": t.get("setVideoId")}
                     for t in tracks if t.get("videoId") in video_ids]
        if not to_remove:
            return "No matching tracks found in the playlist."
        yt.remove_playlist_items(playlist_id, to_remove)
        return f"Removed {len(to_remove)} song(s) from the playlist."
    except Exception as e:
        return _err("removing from the playlist", e)


@mcp.tool()
def ytmusic_delete_playlist(playlist_id: str, confirm_title: str) -> str:
    """
    Delete one of your playlists. Permanent.

    Args:
        playlist_id: The playlist ID to delete
        confirm_title: The playlist's exact title, as a safety check. The delete only
                       happens when it matches, so a stray ID can't wipe the wrong playlist.
    """
    if not BROWSE_ID.match(playlist_id or ""):
        return f"Refused: '{playlist_id}' is not a playlist ID."
    yt = get_ytmusic()
    if yt is None:
        return NOT_SIGNED_IN
    try:
        actual = yt.get_playlist(playlist_id, limit=1).get("title", "")
        if actual != confirm_title:
            return f"Refused: that playlist is titled '{actual}', not '{confirm_title}'. Nothing was deleted."
        yt.delete_playlist(playlist_id)
        return f"Deleted playlist '{actual}'."
    except Exception as e:
        return _err("deleting the playlist", e)


@mcp.tool()
def ytmusic_get_liked_songs(limit: int = 50) -> str:
    """
    Get your liked songs.

    Args:
        limit: Max songs to return (default 50, max 200)
    """
    yt = get_ytmusic()
    if yt is None:
        return NOT_SIGNED_IN
    limit = max(1, min(int(limit), 200))
    try:
        tracks = yt.get_liked_songs(limit=limit).get("tracks", [])[:limit]
        if not tracks:
            return "No liked songs found."
        lines = [f"Liked songs ({len(tracks)} shown):"]
        for i, t in enumerate(tracks[:limit], 1):
            artists = ", ".join(a["name"] for a in t.get("artists", []) or [])
            lines.append(f"{i}. {t.get('title', 'Unknown')} - {artists} | ID: {t.get('videoId', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _err("getting liked songs", e)


@mcp.tool()
def ytmusic_like_song(video_id: str) -> str:
    """
    Like a song (adds it to your Liked songs).

    Args:
        video_id: The video ID to like
    """
    if not VIDEO_ID.match(video_id or ""):
        return f"Refused: '{video_id}' is not a YouTube video ID."
    yt = get_ytmusic()
    if yt is None:
        return NOT_SIGNED_IN
    try:
        yt.rate_song(video_id, "LIKE")
        return f"Liked: {video_id}"
    except Exception as e:
        return _err("liking the song", e)


@mcp.tool()
def ytmusic_get_home() -> str:
    """Get your personalised home recommendations."""
    yt = get_ytmusic()
    if yt is None:
        return NOT_SIGNED_IN
    try:
        lines = ["Home recommendations:"]
        for section in yt.get_home(limit=6):
            lines.append(f"\n## {section.get('title', 'Section')}")
            for item in section.get("contents", [])[:5]:
                lines.append(f"  - {item.get('title', 'Unknown')} ({item.get('resultType', '')})")
        return "\n".join(lines)
    except Exception as e:
        return _err("getting home", e)


@mcp.tool()
def ytmusic_get_mood_playlists() -> str:
    """Get mood and genre categories for discovery. No login needed."""
    try:
        moods = get_reader().get_mood_categories()
        lines = ["Mood & genre categories:"]
        for section, items in (moods.items() if isinstance(moods, dict) else []):
            lines.append(f"\n## {section}")
            lines.extend(f"  - {it.get('title', 'Unknown')}" for it in (items or [])[:12] if isinstance(it, dict))
        return "\n".join(lines)
    except Exception as e:
        return _err("getting moods", e)


@mcp.tool()
def ytmusic_get_artist(artist_id: str) -> str:
    """
    Get an artist's top songs and albums. No login needed.

    Args:
        artist_id: The artist's browse ID from search
    """
    if not BROWSE_ID.match(artist_id or ""):
        return f"Refused: '{artist_id}' is not an artist ID."
    try:
        artist = get_reader().get_artist(artist_id)
        lines = [f"Artist: {artist.get('name', 'Unknown')}"]
        songs = (artist.get("songs") or {}).get("results") or []
        if songs:
            lines.append("\nTop songs:")
            lines.extend(f"  - {s.get('title', 'Unknown')} | ID: {s.get('videoId', '')}" for s in songs[:5])
        albums = (artist.get("albums") or {}).get("results") or []
        if albums:
            lines.append("\nAlbums:")
            lines.extend(f"  - {a.get('title', 'Unknown')} ({a.get('year', '')})" for a in albums[:5])
        return "\n".join(lines)
    except Exception as e:
        return _err("getting the artist", e)


if __name__ == "__main__":
    mcp.run()
