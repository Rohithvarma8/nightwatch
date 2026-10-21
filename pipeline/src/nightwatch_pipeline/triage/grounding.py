"""Grounding check: the model may only narrate facts that are in the source signal text.

Deterministic and conservative: every number, time word (weekday, month, relative day), and
place-like capitalized phrase in the output must appear in the source text, else reject.
"""

import re
from dataclasses import dataclass

_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "hundred": "100",
}  # fmt: skip
_TIME_WORDS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "today", "tonight", "tomorrow", "yesterday",
    "midnight", "noon",
}  # fmt: skip
# Capitalized words that are not place names (and may appear without being in the source).
_NOT_PLACES = {
    "I", "National", "Weather", "Service", "NWS", "AM", "PM", "PDT", "PST", "Red", "Flag",
    "Warning", "Watch", "Advisory", "Statement", "Wind", "High", "Fire", "Heat", "Air",
    "Quality", "Alert", "Freeze", "Frost", "Beach", "Hazards", "Excessive", "Extreme",
}  # fmt: skip
# Generic geographic nouns that can be shared across a coordination: the source's "Los Angeles
# and Ventura Counties" grounds "Los Angeles Counties" if "Los Angeles" and "counties" both appear.
_GEO_NOUNS = {
    "county", "counties", "valley", "valleys", "coast", "coasts", "mountains", "beaches",
    "area", "areas", "region",
}  # fmt: skip
# A trailing period ends a run ("…Ventura Counties. Winds…" is two runs), except after an
# abbreviation ("U.S. Forest Service") or a place title ("Mt. Pinos"), which stay one name.
_ABBREVIATION = r"(?:[A-Z]\.){2,}|(?:Mt|St|Ft|Pt)\."
_CAPITALIZED_WORD = rf"(?:{_ABBREVIATION}|[A-Z][a-zA-Z'-]*(?:\.[a-zA-Z'-]+)*)"
_CAPITALIZED_RUN = re.compile(rf"{_CAPITALIZED_WORD}(?:\s+{_CAPITALIZED_WORD})*")
_SENTENCE_START = re.compile(r"(?:^|[.!?:;]\s+|\n)$")


# Replay strict mode: replayed alerts keep their original prose ("through Saturday") while their
# timestamps are shifted, so replay summaries may not state any timing at all.
_REPLAY_TIME_WORDS = _TIME_WORDS | {"morning", "afternoon", "evening", "overnight", "weekend"}
_CLOCK = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)(?![a-z])|\b\d{1,2}:\d{2}\b", re.I
)
_NUMERIC_DATE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b")
_URL = re.compile(r"https?://|www\.|\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.I)


def has_url(text: str) -> bool:
    """URLs or bare domains ("readyforwildfire.org"). Spoken text must never contain them."""
    return bool(_URL.search(text))


# Month names that are also everyday words ("winds may cause…", "march toward").
_AMBIGUOUS_MONTHS = {"may", "march"}
_MONTH_AS_DATE = re.compile(
    r"\b(?:May|March)\s+\d|\d\s+(?:May|March)\b|(?<=[a-z,]\s)(?:May|March)\b"
)


def _time_words(text: str, vocabulary: set[str]) -> set[str]:
    """Time words in `text`; "may"/"march" only when used as a month (next to a number, or
    capitalized mid-sentence), not as the verb."""
    words = set(re.findall(r"[a-z]+", text.lower())) & vocabulary
    ambiguous = words & _AMBIGUOUS_MONTHS
    if ambiguous and not _MONTH_AS_DATE.search(text):
        words -= ambiguous
    return words


def _timing_violations(text: str) -> list[str]:
    found = [f"replay timing {w!r}" for w in sorted(_time_words(text, _REPLAY_TIME_WORDS))]
    found += [f"replay clock time {m.group(0).rstrip('.')!r}" for m in _CLOCK.finditer(text)]
    found += [f"replay date {m.group(0)!r}" for m in _NUMERIC_DATE.finditer(text)]
    return found


@dataclass(frozen=True)
class GroundingResult:
    passed: bool
    violations: list[str]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def _numbers_in(text: str) -> set[str]:
    found = {n.replace(",", "") for n in _NUMBER.findall(text)}
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in _NUMBER_WORDS:
            found.add(_NUMBER_WORDS[word])
    return found


def _source_numbers(source: str) -> set[str]:
    nums = _numbers_in(source)
    # "8:00PM" in the source grounds "8 PM" in the output.
    nums |= {n.split(":")[0] for n in nums if ":" in n}
    nums |= {n.split(".")[0] for n in nums if "." in n}
    return nums


def _place_candidates(text: str) -> list[tuple[str, ...]]:
    """Capitalized runs that could be names, minus event words, time words, and articles.

    Each candidate lists acceptable spellings: at a sentence start the first word may just be
    a capitalized ordinary word ("Gusty Santa Ana winds"), so the run without it also counts.
    """
    out: list[tuple[str, ...]] = []
    for m in _CAPITALIZED_RUN.finditer(text):
        run = m.group(0).split()
        at_start = bool(_SENTENCE_START.search(text[: m.start()]))
        if len(run) == 1 and at_start:
            continue  # ordinary sentence-initial word ("Keep", "Strong")
        words = [
            w.strip("'")  # keep abbreviation periods: "U.S. Forest" must match the source
            for w in run
            if w.strip(".'-") not in _NOT_PLACES
            and w.lower().strip(".'") not in _TIME_WORDS | {"the", "a", "an"}
        ]
        if words:
            options = [" ".join(words)]
            if at_start and len(words) > 1:
                options.append(" ".join(words[1:]))
            out.append(tuple(options))
    return out


def _grounded_name(name: str, source: str, source_words: set[str]) -> bool:
    if _norm(name) in source:
        return True
    *core, last = name.split()
    return (
        bool(core)
        and last.lower() in _GEO_NOUNS
        and last.lower() in source_words
        and (_norm(" ".join(core)) in source)
    )


def check(output_texts: list[str], source_text: str, *, strict: bool = False) -> GroundingResult:
    """`strict` (replays): additionally reject any weekday, month, date, relative-day word, or
    clock time, even if it appears in the source."""
    source = _norm(source_text)
    source_nums = _source_numbers(source_text)
    source_words = set(re.findall(r"[a-z]+", source))
    violations: list[str] = []
    for text in output_texts:
        for n in sorted(_numbers_in(text)):
            if n not in source_nums:
                violations.append(f"number {n!r} not in source")
        for word in sorted(_time_words(text, _TIME_WORDS)):
            if word not in source_words:
                violations.append(f"time word {word!r} not in source")
        for options in _place_candidates(text):
            if not any(_grounded_name(o, source, source_words) for o in options):
                violations.append(f"name {options[0]!r} not in source")
        if strict:
            violations += _timing_violations(text)
    return GroundingResult(passed=not violations, violations=violations)
