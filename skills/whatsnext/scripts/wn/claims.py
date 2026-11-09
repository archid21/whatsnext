"""Soft checkout claims (ADR-0002).

One JSON file per claimed plan item, in `<git common dir>/whatsnext/claims/<ID>.json`,
so every worktree of one clone sees them at once. They are never committed.
Outside git the folder is `<root>/.whatsnext/claims/`. Inside git that folder is also the
fallback when the git folder cannot be written (Codex's sandbox protects `.git`): a write
that fails there is repeated in `<root>/.whatsnext/claims/`, which holds its own `.gitignore`
so the claims never show up as changes. Reads look in both; the git folder wins.

A claim is a lock on one machine (P-53). A new claim file is created with
O_CREAT|O_EXCL, so of two `plan start` calls at once only one creates it. Every change
to an existing claim (update, touch, release) runs under a short per-item lock file
(`<ID>.lock`, also O_EXCL, removed when older than LOCK_STALE seconds), and update and
touch rewrite the file only while it still holds the same token, so a Stop hook can
never bring back a claim that `plan put-back` or `plan done` released.
"""

import datetime
import json
import os
import re
import contextlib
import stat
import time
import uuid

from . import status as gwstatus
from .util import now_utc, parse_date

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
LOCK_STALE = 10.0  # seconds after which a leftover lock file is removed
LOCK_WAIT = 5.0  # seconds to wait for another process's lock
STALE_RE = re.compile(r"^([1-9][0-9]*)([mh])$")


# ---- time ------------------------------------------------------------------


def stamp(now=None):
    return (now or now_utc()).strftime(TIME_FORMAT)


def to_dt(text):
    """A stored UTC time as an aware datetime, or None."""
    value = parse_date(text) if isinstance(text, str) else None
    return value.replace(tzinfo=datetime.timezone.utc) if value else None


def stale_delta(text):
    """`plan.staleAfter` ("4h", "30m") as a timedelta; 4 hours when it cannot be read."""
    m = STALE_RE.match(text or "")
    if not m:
        return datetime.timedelta(hours=4)
    n = int(m.group(1))
    return datetime.timedelta(hours=n) if m.group(2) == "h" else datetime.timedelta(minutes=n)


def short_time(dt, now=None):
    """14:05Z for today, the full time for another day."""
    now = now or now_utc()
    if dt.date() == now.date():
        return dt.strftime("%H:%MZ")
    return dt.strftime("%Y-%m-%dT%H:%MZ")


# ---- where claims live -----------------------------------------------------


def fallback_dir(root):
    return os.path.join(root, ".whatsnext", "claims")


def claims_dir(root):
    code, out = gwstatus.git(root, "rev-parse", "--git-common-dir")
    if code == 0 and out.strip():
        return os.path.join(os.path.abspath(os.path.join(root, out.strip())), "whatsnext", "claims")
    return fallback_dir(root)


def claim_path(root, item_id):
    """Where the claim is, or where a new one goes (the git folder first)."""
    primary = os.path.join(claims_dir(root), item_id + ".json")
    other = os.path.join(fallback_dir(root), item_id + ".json")
    if not os.path.exists(primary) and os.path.exists(other):
        return other
    return primary


def _put(root, item_id, writer, path, data):
    """`writer(path, data)`; when the git folder refuses, the same write in the fallback folder."""
    try:
        return writer(path, data)
    except FileExistsError:
        raise
    except OSError:
        fallback = os.path.join(fallback_dir(root), item_id + ".json")
        if os.path.abspath(path) == os.path.abspath(fallback):
            raise
        folder = os.path.dirname(fallback)
        os.makedirs(folder, exist_ok=True)
        ignore = os.path.join(folder, ".gitignore")
        if not os.path.exists(ignore):
            with open(ignore, "w", encoding="utf-8") as f:
                f.write("*\n")
        return writer(fallback, data)


def worktree_root(root):
    return os.path.realpath(root)


# ---- read and write --------------------------------------------------------


def read(root, item_id):
    """The claim as a dict, or None when missing or unreadable."""
    try:
        with open(claim_path(root, item_id), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("id") == item_id else None


MAX_CLAIM_BYTES = 65536
ITEM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def sibling_roots(root):
    """The other worktrees of this repository, from `git worktree list --porcelain` (this one left out)."""
    code, out = gwstatus.git(root, "worktree", "list", "--porcelain")
    if code != 0:
        return []
    mine = worktree_root(root)
    found = []
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = os.path.realpath(line[len("worktree "):].strip())
            if path != mine and os.path.isdir(path):
                found.append(path)
    return found


SIBLING_FIELDS = ("agent", "session", "branch", "worktree", "since", "updated", "asked_at", "token")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def safe_text(value, limit=80):
    """`value` as short plain text: control characters (escape sequences, new lines) removed, clipped."""
    return CONTROL_RE.sub("", str(value))[:limit]


def read_sibling_file(path):
    """One sibling claim as a dict of plain, short strings, or None. The file is opened without following a link and
    judged by the open descriptor (a plain file, not over MAX_CLAIM_BYTES), so nothing can change between the
    check and the read. Only the known claim fields are kept."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CLAIM_BYTES:
            return None
        with os.fdopen(fd, "rb", closefd=False) as f:
            raw = f.read(MAX_CLAIM_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    if len(raw) > MAX_CLAIM_BYTES:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
        return None
    clean = {"id": data["id"]}
    for key in SIBLING_FIELDS:
        if data.get(key) is not None:
            clean[key] = safe_text(data[key])
    return clean


def read_siblings(root):
    """Claims in the `.whatsnext/claims/` folder of each other worktree (P-10), read only. A Codex sandbox cannot write
    the git folder, so its claim lands in its own worktree. Only plain files of a sane size and name are read, and a
    claim whose `id` is not its file name is ignored. Each claim gets `sibling_worktree`."""
    out = {}
    for sibling in sibling_roots(root):
        folder = os.path.join(sibling, ".whatsnext", "claims")
        if os.path.islink(folder) or os.path.islink(os.path.join(sibling, ".whatsnext")):
            continue
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            path = os.path.join(folder, name)
            item_id = name[:-5]
            if not name.endswith(".json") or not ITEM_ID_RE.match(item_id):
                continue
            data = read_sibling_file(path)
            if data is not None and data.get("id") == item_id and item_id not in out:
                out[item_id] = dict(data, id=item_id, sibling_worktree=safe_text(sibling))
    return out


def read_all(root, siblings=False):
    """Every claim this worktree and the git folder hold. With `siblings`, also those other worktrees keep in their own
    `.whatsnext/claims/` folder (a claim here wins over one there)."""
    out = dict(read_siblings(root)) if siblings else {}
    for folder in (fallback_dir(root), claims_dir(root)):  # the git folder is read last, so it wins
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            if name.endswith(".json"):
                found = read(root, name[:-5])
                if found:
                    out[found["id"]] = found
    return out


def _write_replace(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%s.tmp" % (path, uuid.uuid4().hex[:8])
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _write_new(path, data):
    """Create the file with O_CREAT|O_EXCL. False when someone else created it first."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    except FileExistsError:
        return False
    try:
        os.write(fd, body)
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


@contextlib.contextmanager
def _locked(root, item_id):
    """Hold `<ID>.lock` (O_EXCL) in the claims folder while a claim changes. Best effort when no folder can be written."""
    held = None
    deadline = time.time() + LOCK_WAIT
    for folder in (claims_dir(root), fallback_dir(root)):
        path = os.path.join(folder, item_id + ".lock")
        while held is None:
            try:
                os.makedirs(folder, exist_ok=True)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                os.write(fd, str(os.getpid()).encode("ascii"))
                os.close(fd)
                held = path
            except FileExistsError:
                try:
                    if time.time() - os.stat(path).st_mtime > LOCK_STALE:
                        os.remove(path)
                        continue
                except OSError:
                    continue
                if time.time() > deadline:
                    break
                time.sleep(0.02)
            except OSError:
                break  # this folder cannot be written: try the fallback
        if held:
            break
    try:
        yield
    finally:
        if held:
            try:
                os.remove(held)
            except OSError:
                pass


def is_ours(claim, agent, root):
    """Same agent in the same worktree: a re-run, not a takeover."""
    return bool(claim) and claim.get("agent") == agent and claim.get("worktree") == worktree_root(root)


def claim(root, item_id, agent, session=None, branch=None, takeover=False):
    """Claim an item. Returns (claim, None) when it is ours, or (None, other claim) when not.

    An existing claim by someone else is replaced only with `takeover`.
    """
    with _locked(root, item_id):
        return _claim(root, item_id, agent, session, branch, takeover)


def _claim(root, item_id, agent, session, branch, takeover):
    path = claim_path(root, item_id)
    existing = read(root, item_id)
    now = stamp()
    mine = {"id": item_id, "agent": agent, "session": session, "branch": branch,
            "worktree": worktree_root(root), "since": now, "updated": now,
            "token": uuid.uuid4().hex, "asked_at": None}
    if existing is None and not takeover:
        rival = read_siblings(root).get(item_id)  # P-12: a claim another worktree keeps in its own folder
        if rival:
            return None, rival
    if existing is None:
        if os.path.exists(path):  # unreadable file: treat as a claim of unknown owner
            if not takeover:
                return None, {"id": item_id, "agent": "unknown", "since": None, "updated": None}
            _put(root, item_id, _write_replace, path, mine)
        elif not _put(root, item_id, _write_new, path, mine):
            return None, read(root, item_id) or {"id": item_id, "agent": "unknown"}
    elif is_ours(existing, agent, root):
        mine["since"] = existing.get("since") or now
        mine["session"] = session or existing.get("session")
        _put(root, item_id, _write_replace, path, mine)
    elif takeover:
        _put(root, item_id, _write_replace, path, mine)
    else:
        return None, existing
    check = read(root, item_id)  # read it back: only the last writer keeps it
    if check and check.get("token") == mine["token"]:
        rival = None if (existing is not None or takeover) else read_siblings(root).get(item_id)
        if rival and rival.get("token") != mine["token"] and \
                (str(rival.get("since") or ""), str(rival.get("token") or "")) < (str(mine["since"]), mine["token"]):
            _drop_mine(root, item_id, mine["token"])  # both wrote at once: the earlier claim wins, on both sides
            return None, rival
        return check, None
    return None, check or {"id": item_id, "agent": "unknown"}


def _drop_mine(root, item_id, token):
    """Remove this claim from both folders, but only a file that still holds `token`."""
    for folder in (claims_dir(root), fallback_dir(root)):
        path = os.path.join(folder, item_id + ".json")
        try:
            with open(path, encoding="utf-8") as f:
                if json.load(f).get("token") != token:
                    continue
            os.remove(path)
        except (OSError, ValueError, AttributeError):
            pass


def update(root, item_id, **fields):
    """Change fields of an existing claim. Returns it, or None when there is none.

    Under the item lock, and only while the file still holds the token read first:
    a claim released in the meantime stays released.
    """
    with _locked(root, item_id):
        data = read(root, item_id)
        if data is None:
            return None
        token = data.get("token")
        data.update(fields)
        now = read(root, item_id)
        if now is None or now.get("token") != token:
            return None
        _put(root, item_id, _write_replace, claim_path(root, item_id), data)
        return data


def touch(root, item_id):
    """Refresh `updated` and clear `asked_at`. Does nothing when there is no claim."""
    return update(root, item_id, updated=stamp(), asked_at=None)


def mark_asked(root, item_id):
    return update(root, item_id, asked_at=stamp())


def release(root, item_id):
    """Remove the claim from both folders. True when one was removed."""
    removed = False
    with _locked(root, item_id):
        for folder in (claims_dir(root), fallback_dir(root)):
            try:
                os.remove(os.path.join(folder, item_id + ".json"))
                removed = True
            except OSError:
                pass
    return removed


# ---- stale -----------------------------------------------------------------


def idle_since(claim_data, task_updated):
    """The later of the claim's `updated` and the progress file's Updated, as a datetime (or None)."""
    times = [t for t in (to_dt(claim_data.get("updated")), to_dt(task_updated)) if t]
    return max(times) if times else None


def is_stale(claim_data, task_updated, stale_after, now=None):
    idle = idle_since(claim_data, task_updated)
    return bool(idle) and (now or now_utc()) - idle > stale_delta(stale_after)


def stale_in_worktree(root, effective, now=None):
    """Stale claims held from this worktree: [(claim, idle_since datetime)], oldest first."""
    now = now or now_utc()
    stale_after = effective.get("plan.staleAfter")
    folder = gwstatus.status_folder(root, effective)
    mine = worktree_root(root)
    out = []
    for item_id, data in read_all(root).items():
        if data.get("worktree") != mine:
            continue
        updated = _status_updated(root, folder, item_id)
        if is_stale(data, updated, stale_after, now):
            out.append((data, idle_since(data, updated)))
    return sorted(out, key=lambda pair: (pair[1], pair[0]["id"]))


def _status_updated(root, folder, item_id):
    path = gwstatus.task_path(folder, item_id)
    if not os.path.isfile(path):
        return None
    try:
        return gwstatus.Task(root, path).field("updated")
    except OSError:
        return None


def stale_line(claim_data, idle, stale_after, now=None):
    return "%s has been idle since %s (over %s). Ask the user: mark it done, keep working on it, or put it back?" % (
        claim_data["id"], short_time(idle, now), stale_after)
