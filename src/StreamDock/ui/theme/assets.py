"""
Small glyphs, rendered in whatever colour the active palette calls for.

Qt stylesheets can only point ``image:`` at a file, and a grey chevron baked
into an asset is wrong on half the themes, so the handful of glyphs the
stylesheet needs are written out per colour and cached on disk.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Every glyph is a 16x16 stroke drawing so one colour parameter covers it.
_GLYPHS: Dict[str, str] = {
    'chevron-down':
        '<path d="M4 6.5 L8 10.5 L12 6.5" fill="none" stroke="{color}" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    'chevron-up':
        '<path d="M4 9.5 L8 5.5 L12 9.5" fill="none" stroke="{color}" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    'chevron-right':
        '<path d="M6.5 4 L10.5 8 L6.5 12" fill="none" stroke="{color}" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    'check':
        '<path d="M3.5 8.5 L6.5 11.5 L12.5 4.5" fill="none" stroke="{color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    'dot':
        '<circle cx="8" cy="8" r="3.5" fill="{color}"/>',
    'dash':
        '<path d="M4 8 L12 8" fill="none" stroke="{color}" stroke-width="2" '
        'stroke-linecap="round"/>',
    'menu':
        '<g fill="none" stroke="{color}" stroke-width="1.8" '
        'stroke-linecap="round"><path d="M3 4.5h10"/><path d="M3 8h10"/>'
        '<path d="M3 11.5h10"/></g>',
}

_TEMPLATE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
             'width="16" height="16">{body}</svg>')

_written: Dict[str, str] = {}
_private_dir: Optional[Path] = None


def glyph_path(name: str, color: str) -> str:
    """
    A file path to one glyph drawn in one colour.

    Args:
        name: A key of the bundled glyph set
        color: Stroke or fill colour, as ``#rrggbb``

    Returns:
        A POSIX path usable in a stylesheet ``url()``, or '' when the glyph
        could not be written - a missing arrow must never stop the window
        from opening

    Raises:
        KeyError: No such glyph
    """
    body = _GLYPHS[name]
    key = f"{name}-{color.lstrip('#').lower()}"
    cached = _written.get(key)
    if cached and os.path.exists(cached):
        return cached

    directory = _cache_dir()
    path = directory / f"{key}.svg"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Rewritten every session: a truncated file from a previous crash
        # would otherwise be cached for good. Written beside and renamed over
        # it, so a reader never sees half a file and a planted symlink is
        # replaced rather than written through.
        fd, temporary = tempfile.mkstemp(dir=directory, prefix=f".{key}-", suffix=".svg")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(_TEMPLATE.format(body=body.format(color=color)))
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
    except OSError as e:
        logger.warning("Could not write theme glyph %s: %s", key, e)
        return ''

    resolved = path.as_posix()
    _written[key] = resolved
    return resolved


def _cache_dir() -> Path:
    """
    Where rendered glyphs live.

    Returns:
        A writable directory. The fallback is private to this user: a fixed
        name under /tmp could be created first by anyone else.
    """
    global _private_dir  # pylint: disable=global-statement
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(Path.home(), '.cache')
    try:
        candidate = Path(base)
        if candidate.is_dir() or not candidate.exists():
            return candidate / 'streamdock' / 'theme'
    except OSError:  # pragma: no cover - an unreadable home is exotic
        pass
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if runtime and os.path.isdir(runtime):
        return Path(runtime) / 'streamdock-theme'
    if _private_dir is None:
        _private_dir = Path(tempfile.mkdtemp(prefix='streamdock-theme-'))
    return _private_dir
