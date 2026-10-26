"""Machine-readable command inventory extracted from the DS8000-R guide.

Creator: Jeff Michaelis

Every SCPI syntax entry supplied in the November 2020 programming guide is
available through the embedded JSON file. The catalogue is descriptive; it
must not be mistaken for a live probe of the firmware or installed options.
"""
import fnmatch
import json
from importlib import resources
from .exceptions import ValidationError


def entries(pattern="*"):
    """Return syntax records; pattern matches SCPI paths or full syntaxes.

    Records contain `syntax`, `name`, `query`, `page`, `pdf_page`, and
    `description`. Each query/set variant is kept separately.
    """
    with resources.open_text("rigol_ds8000r", "command_catalog.json", encoding="utf-8") as fp:
        data = json.load(fp)
    return [e for e in data if fnmatch.fnmatchcase(e["syntax"].upper(), pattern.upper())
            or fnmatch.fnmatchcase(e["name"].upper(), pattern.upper())]


def find(command):
    """Look up an exact command by full manual path (case-insensitive)."""
    key = str(command).strip().rstrip("?").upper()
    result = [e for e in entries() if e["name"].upper() == key]
    if not result:
        raise ValidationError("Not in manual catalog: {!r}".format(command))
    return result


def examples():
    """Return the total number of catalogue entries (set+query forms)."""
    return len(entries())
