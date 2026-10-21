"""Does a summary already say what an action says? Deterministic word overlap (pure, no I/O).

"Be extremely cautious with anything that can spark." covers "Use extreme caution with anything
that can spark a wildfire": content words are compared by their first 5 letters, so
cautious/caution and extremely/extreme match. Words of the incident title ("Red Flag Warning")
don't count: naming the hazard isn't saying what to do about it.
"""

import re

_STEM = 5
MIN_SHARED = 3
MIN_OVERLAP = 0.75
_STOPWORDS = frozenset(
    "a an the and or but of to in on at for from by with as is are be been being it its this that "
    "these those you your yours can could should would will may might must do does use keep stay "
    "any all if when while during than then so very just".split()
)


def _words(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t[:_STEM] for t in tokens if t not in _STOPWORDS and len(t) > 1}


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def covers(summary: str, action: str, title: str = "") -> bool:
    """True when one summary sentence has most (≥ 75%, ≥ 3) of the action's content words."""
    act = _words(action) - _words(title)
    if len(act) < MIN_SHARED:
        return False
    for sent in _sentences(summary):
        shared = act & _words(sent)
        if len(shared) >= MIN_SHARED and len(shared) / len(act) >= MIN_OVERLAP:
            return True
    return False
