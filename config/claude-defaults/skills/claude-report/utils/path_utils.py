"""Cross-platform path utilities."""
import os
import sys
from pathlib import Path

def get_home() -> Path:
    """Get user home directory cross-platform."""
    return Path(os.environ.get('HOME') or os.environ.get('USERPROFILE') or Path.home())

def get_claude_dir() -> Path:
    """Get ~/.claude directory."""
    return get_home() / '.claude'

def get_project_claude_dir() -> Path:
    """Get .claude directory in current project."""
    return Path.cwd() / '.claude'

def normalize_path(p: str) -> Path:
    """Normalize path string to Path object, expanding ~ and env vars."""
    if not p:
        return None
    expanded = os.path.expanduser(os.path.expandvars(p))
    # Normalize to Path which handles separators automatically
    return Path(expanded)

def is_subpath(child: Path, parent: Path) -> bool:
    """Check if child is under parent directory."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False

def get_relative_display(p: Path) -> str:
    """Get path relative to home for display."""
    home = get_home()
    try:
        rel = p.resolve().relative_to(home)
        return '~/' + rel.as_posix()
    except ValueError:
        return str(p)
