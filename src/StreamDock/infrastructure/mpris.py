"""
Media players over MPRIS, through ``busctl --json``.

busctl ships with systemd, so this needs no Python D-Bus binding. Every call
is a short subprocess; widgets make them from ``ctx.run_in_background``.

Several media keys poll at once, so what the bus said is shared for
``CACHE_TTL`` seconds: one ListNames and one GetAll per player serve them all.
"""

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

BUS_PREFIX = 'org.mpris.MediaPlayer2.'
OBJECT_PATH = '/org/mpris/MediaPlayer2'
PLAYER_INTERFACE = 'org.mpris.MediaPlayer2.Player'
PROPERTIES_INTERFACE = 'org.freedesktop.DBus.Properties'
TIMEOUT = 2
CACHE_TTL = 1.0
_RANK = {'playing': 0, 'paused': 1}


def _busctl(*args: str) -> Optional[Any]:
    """The ``data`` of busctl's JSON reply, or None if the call failed."""
    try:
        result = subprocess.run(['busctl', '--user', '--json=short', *args], capture_output=True, text=True,
                                timeout=TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)['data']
    except (ValueError, KeyError, TypeError):
        return None


def list_players() -> List[str]:
    names = _busctl('call', 'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'ListNames')
    if not names:
        return []
    return sorted(name for name in names[0] if name.startswith(BUS_PREFIX))


def _properties(player: str) -> Dict[str, Any]:
    """Every Player property in one call, variants unwrapped."""
    reply = _busctl('call', player, OBJECT_PATH, PROPERTIES_INTERFACE, 'GetAll', 's', PLAYER_INTERFACE)
    props = reply[0] if isinstance(reply, list) and reply else None
    return {name: _variant(value) for name, value in props.items()} if isinstance(props, dict) else {}


def _variant(value: Any) -> Any:
    """busctl writes a variant as {"type": ..., "data": ...}."""
    return value.get('data') if isinstance(value, dict) and 'data' in value else value


@dataclass
class PlayerStatus:
    player: Optional[str] = None
    status: str = 'none'  # playing, paused, stopped or none
    title: str = ''
    artists: List[str] = field(default_factory=list)
    album: str = ''
    art_url: str = ''

    @property
    def artist(self) -> str:
        return ', '.join(self.artists)


def parse_metadata(status: PlayerStatus, metadata: Any) -> PlayerStatus:
    metadata = metadata if isinstance(metadata, dict) else {}
    title = _variant(metadata.get('xesam:title'))
    artists = _variant(metadata.get('xesam:artist'))
    album = _variant(metadata.get('xesam:album'))
    art = _variant(metadata.get('mpris:artUrl'))
    status.title = title if isinstance(title, str) else ''
    status.artists = [a for a in artists if isinstance(a, str)] if isinstance(artists, list) else []
    status.album = album if isinstance(album, str) else ''
    status.art_url = art if isinstance(art, str) else ''
    return status


_cache_lock = threading.Lock()
_cache: Tuple[float, List[Tuple[str, Dict[str, Any]]]] = (float('-inf'), [])


def _snapshot() -> List[Tuple[str, Dict[str, Any]]]:
    """(player, properties) for every player, at most CACHE_TTL seconds old."""
    global _cache  # pylint: disable=global-statement
    # Held while asking the bus, so keys polling together wait for one answer
    # instead of each starting their own busctl calls.
    with _cache_lock:
        taken, players = _cache
        if time.monotonic() - taken < CACHE_TTL:
            return players
        players = [(player, _properties(player)) for player in list_players()]
        _cache = (time.monotonic(), players)
        return players


def invalidate() -> None:
    """Forget the shared snapshot, e.g. after pressing play, so the next look sees the change."""
    global _cache  # pylint: disable=global-statement
    with _cache_lock:
        _cache = (float('-inf'), [])


def current(player_filter: str = '', with_metadata: bool = True) -> PlayerStatus:
    """
    The player to show: one matching ``player_filter`` (a substring of its bus
    name, e.g. 'spotify'), preferring one that is playing, then paused.
    """
    candidates = []
    for player, props in _snapshot():
        if player_filter.lower() not in player.lower():
            continue
        raw = props.get('PlaybackStatus')
        candidates.append((PlayerStatus(player, raw.lower() if isinstance(raw, str) else 'stopped'), props))
    best = min(candidates, key=lambda candidate: _RANK.get(candidate[0].status, 2), default=None)
    if best is None:
        return PlayerStatus()
    status, props = best
    if with_metadata:
        parse_metadata(status, props.get('Metadata'))
    return status


def call(player: str, method: str) -> None:
    """Run a Player method such as PlayPause, Next or Previous."""
    _busctl('call', player, OBJECT_PATH, PLAYER_INTERFACE, method)
    invalidate()


PLAYER_OPTION_DESCRIPTION = 'Part of the player\'s name, e.g. spotify or firefox. Empty: whichever is playing.'
