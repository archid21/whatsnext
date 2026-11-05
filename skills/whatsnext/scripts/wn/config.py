"""Layered configuration.

Layers, later wins: built-in defaults (read from config.schema.json), user,
project, project-local. Objects merge deeply; arrays and scalars replace.
"""

import json
import os
import re
import subprocess

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "schemas",
    "config.schema.json",
)

LAYER_NAMES = ("default", "user", "project", "local")
IGNORED_KEYS = ("$schema",)


class Entry(object):
    """One effective setting: its value, source layer and file (or None)."""

    def __init__(self, value, source, file):
        self.value = value
        self.source = source
        self.file = file


class Effective(object):
    """The merged settings plus any layer errors."""

    def __init__(self, root, entries, errors):
        self.root = root
        self.entries = entries  # dotted key -> Entry
        self.errors = errors  # list of message strings

    def get(self, key):
        return self.entries[key].value

    def source(self, key):
        entry = self.entries[key]
        return entry.source, entry.file

    def module_on(self, name):
        return bool(self.entries["modules." + name].value)


def load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def find_root(cwd=None):
    """Project root: git top-level of the cwd, else the cwd."""
    cwd = cwd or os.getcwd()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd


def user_config_path():
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(xdg, "whatsnext", "config.json")
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, ".config", "whatsnext", "config.json")


def display_path(path, root):
    """Project files relative to the root, user files as ~/..."""
    root_prefix = os.path.join(root, "")
    if path.startswith(root_prefix):
        return path[len(root_prefix):]
    home = os.environ.get("HOME") or os.path.expanduser("~")
    home_prefix = os.path.join(home, "")
    if path.startswith(home_prefix):
        return "~/" + path[len(home_prefix):]
    return path


def flatten(data, prefix=""):
    """Turn nested objects into {dotted.key: leaf}. Arrays are leaves."""
    out = {}
    for key, value in data.items():
        if not prefix and key in IGNORED_KEYS:
            continue
        name = prefix + key
        if isinstance(value, dict):
            out.update(flatten(value, name + "."))
        else:
            out[name] = value
    return out


def default_values(schema, prefix=""):
    """Collect every `default` in the schema as {dotted.key: value}."""
    out = {}
    for key, sub in schema.get("properties", {}).items():
        if not prefix and key in IGNORED_KEYS:
            continue
        name = prefix + key
        if "properties" in sub:
            out.update(default_values(sub, name + "."))
        elif "default" in sub:
            out[name] = sub["default"]
    return out


# --- validation -------------------------------------------------------------

TYPE_NAMES = {"object": "an object", "boolean": "a boolean", "integer": "an integer",
              "string": "a string", "array": "an array"}


def _is_type(value, name):
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    return True


def _got(value):
    return json.dumps(value)


def is_relative_path(value):
    """True for a non-empty path that stays inside the project root."""
    if not value or value.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", value):
        return False
    parts = [p for p in re.split(r"[/\\]", value) if p not in ("", ".")]
    return bool(parts) and ".." not in parts


_DROP = object()  # marker: this value is invalid and must not be kept


def validate(value, schema, path, errors):
    """Append (path, message) pairs for every way `value` breaks `schema`.

    Returns the part of `value` that is valid, or _DROP when none of it is.
    An object keeps its valid keys; an array with any bad item is dropped whole.
    """
    if "enum" in schema and value not in schema["enum"]:
        errors.append((path, "must be one of %s (got %s)" % (", ".join(str(v) for v in schema["enum"]), _got(value))))
        return _DROP
    kind = schema.get("type")
    if kind and not _is_type(value, kind):
        errors.append((path, "must be %s (got %s)" % (TYPE_NAMES.get(kind, kind), _got(value))))
        return _DROP
    if kind == "string":
        if schema.get("x-relativePath") and not is_relative_path(value):
            errors.append((path, "must be a relative path inside the project, with no leading / and no .. segment (got %s)" % _got(value)))
            return _DROP
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append((path, "must have at least %d characters (got %s)" % (schema["minLength"], _got(value))))
            return _DROP
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append((path, "must match pattern %s (got %s)" % (schema["pattern"], _got(value))))
            return _DROP
    elif kind == "integer":
        if "minimum" in schema and value < schema["minimum"]:
            errors.append((path, "must be at least %d (got %s)" % (schema["minimum"], _got(value))))
            return _DROP
        if "maximum" in schema and value > schema["maximum"]:
            errors.append((path, "must be at most %d (got %s)" % (schema["maximum"], _got(value))))
            return _DROP
    elif kind == "array" and "items" in schema:
        kept = [validate(item, schema["items"], "%s[%d]" % (path, i), errors) for i, item in enumerate(value)]
        if any(item is _DROP for item in kept):
            return _DROP
    elif kind == "object":
        props = schema.get("properties", {})
        out = {}
        for key, item in value.items():
            sub = (path + "." if path else "") + key
            if key in props:
                result = validate(item, props[key], sub, errors)
                if result is not _DROP:
                    out[key] = result
            elif schema.get("additionalProperties") is False:
                errors.append((sub, "unknown key"))
            else:
                out[key] = item
        return out
    return value


def read_layer(path, label, schema):
    """Read and validate one file. Returns (data or None, [error strings]).

    Only the invalid keys are dropped. A file that is not valid JSON, or whose
    top level is not an object, is dropped whole.
    """
    if not os.path.isfile(path):
        return None, []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        line = getattr(e, "lineno", None)
        where = " at line %d" % line if line else ""
        return None, ["%s: invalid JSON%s: %s" % (label, where, getattr(e, "msg", e))]
    except OSError as e:
        return None, ["%s: cannot read file: %s" % (label, e.strerror or e)]
    found = []
    data = validate(data, schema, "", found)
    errors = ["%s: %s: %s" % (label, p, m) if p else "%s: %s" % (label, m) for p, m in found]
    return (None if data is _DROP else data), errors


def layer_files(root):
    """(layer name, path) pairs in priority order, lowest first."""
    return [
        ("user", user_config_path()),
        ("project", os.path.join(root, ".whatsnext", "config.json")),
        ("local", os.path.join(root, ".whatsnext", "config.local.json")),
    ]


def load(root=None):
    """Merge all layers. Invalid keys are dropped and reported in errors."""
    root = root or find_root()
    schema = load_schema()
    entries = {k: Entry(v, "default", None) for k, v in default_values(schema).items()}
    errors = []
    for name, path in layer_files(root):
        label = display_path(path, root)
        data, errs = read_layer(path, label, schema)
        errors.extend(errs)
        if data is None:
            continue
        for key, value in flatten(data).items():
            entries[key] = Entry(value, name, label)
    return Effective(root, entries, errors)


# --- `config set --user` ------------------------------------------------------


def schema_node(schema, key):
    """The schema entry for a dotted key, or None. Only a setting (a leaf with a type or an enum) counts."""
    if key in IGNORED_KEYS:
        return None
    node = schema
    for part in key.split("."):
        props = node.get("properties") if isinstance(node, dict) else None
        if not isinstance(props, dict) or part not in props:
            return None
        node = props[part]
    return node if ("enum" in node or node.get("type") in ("boolean", "integer", "string")) else None


def parse_value(raw, node):
    """`raw` (text from the command line) as the value the schema entry wants: a boolean (true or false), an
    integer, or a string (also for an enum). Raises ValueError with a plain message."""
    if node.get("type") == "boolean":
        if raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        raise ValueError("must be true or false (got %s)" % _got(raw))
    if node.get("type") == "integer":
        if re.match(r"^-?[0-9]+$", raw):
            return int(raw)
        raise ValueError("must be an integer (got %s)" % _got(raw))
    return raw


def set_user(key, raw):
    """Write one setting into the user layer file (`user_config_path()`), after checking the key and the value
    against the schema. The file's other keys stay. Returns the path. Raises ValueError with a plain message
    (unknown key, bad value, or a user file that is not a JSON object, which is never overwritten)."""
    schema = load_schema()
    node = schema_node(schema, key)
    if node is None:
        raise ValueError("unknown setting %s. `whatsnext config show` lists the settings." % _got(key))
    value = parse_value(raw, node)
    problems = []
    if validate(value, node, key, problems) is _DROP:
        raise ValueError("%s %s" % (key, problems[0][1]))
    path = user_config_path()
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError) as e:
            raise ValueError("%s is not readable JSON, so it was not changed (%s)." % (display_path(path, os.getcwd()), e))
        if not isinstance(data, dict):
            raise ValueError("%s is not a JSON object, so it was not changed." % display_path(path, os.getcwd()))
    cursor = data
    parts = key.split(".")
    for part in parts[:-1]:
        if not isinstance(cursor.get(part), dict):
            cursor[part] = {}
        cursor = cursor[part]
    cursor[parts[-1]] = value
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path
