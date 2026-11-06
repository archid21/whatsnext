"""Small shared helpers: the current UTC time, parsing a stored UTC time and writing a file in one step."""

import datetime
import os
import re
import shutil
import tempfile

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z$")


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse_date(text):
    """A stored UTC time (`2026-10-27T14:05Z`, seconds optional) as a datetime, or None when it is not valid."""
    if not text or not DATE_RE.match(text):
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ" if text.count(":") == 2 else "%Y-%m-%dT%H:%MZ"
    try:
        return datetime.datetime.strptime(text, fmt)
    except ValueError:
        return None


def write_atomic(path, text, newline=""):
    """Write `text` to `path` through a temporary file in the same folder, then swap it in (`os.replace`).
    A write that fails (a full disk, a signal, a crash) leaves the old file whole and no temporary file behind.
    A symlink is followed, so the link stays. The old file's permissions are kept."""
    path = os.path.realpath(path)
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
