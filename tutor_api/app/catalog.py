"""What the ZAKI device offers: learning topics, games, and how to recognise a topic in a question.

Add a topic or game here when you add it to the device. Anything the device sends that is
not listed still works: it is shown with a tidied-up name and the subject "General".
"""
import re

# key -> (label shown to parents, subject, keywords that point to this topic in a child's question)
TOPICS: dict[str, tuple[str, str, list[str]]] = {
    "prime_numbers": ("Prime Numbers", "Maths", ["prime"]),
    "hcf": ("HCF", "Maths", ["hcf", "gcf", "highest common factor", "greatest common factor",
                              "greatest common divisor"]),
    "lcm": ("LCM", "Maths", ["lcm", "lowest common multiple", "least common multiple"]),
    "factors": ("Factors", "Maths", ["factor", "factorise", "factorize"]),
    "fractions": ("Fractions", "Maths", ["fraction", "numerator", "denominator"]),
    "decimals": ("Decimals", "Maths", ["decimal"]),
    "percentages": ("Percentages", "Maths", ["percent", "percentage", "%"]),
    "integers": ("Integers", "Maths", ["integer", "negative number", "positive and negative"]),
    "exponents": ("Exponents", "Maths", ["exponent", "indices", "index", "power of", "squared",
                                         "cubed", "raised to"]),
    "perimeter": ("Perimeter", "Maths", ["perimeter"]),
    "area": ("Area", "Maths", ["area"]),
    "volume": ("Volume", "Maths", ["volume"]),
    "mean": ("Mean", "Maths", ["average", "the mean", "mean of"]),
    "median": ("Median", "Maths", ["median"]),
    "mode": ("Mode", "Maths", ["the mode", "mode of"]),
    "range": ("Range", "Maths", ["the range", "range of"]),
    "triangles": ("Triangles", "Maths", ["triangle", "isosceles", "equilateral", "scalene"]),
    "quadrilaterals": ("Quadrilaterals", "Maths", ["quadrilateral", "parallelogram", "rhombus",
                                                   "trapezium", "kite"]),
    "parallel_lines": ("Parallel Lines", "Maths", ["parallel", "alternate angle",
                                                   "corresponding angle", "co-interior"]),
    "pythagoras": ("Pythagoras", "Maths", ["pythagoras", "pythagorean", "hypotenuse"]),
}

GAMES: dict[str, str] = {
    "chess": "Chess",
    "memory_match": "Memory Match",
    "tic_tac_toe": "Tic Tac Toe",
    "zaki_racing": "ZAKI Racing",
    "hangman": "Hangman",
    "music_studio": "Music Studio",
}


def slug(text: str) -> str:
    """'Prime Numbers' -> 'prime_numbers', 'ZAKI Racing' -> 'zaki_racing'."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def label(key: str) -> str:
    if key in TOPICS:
        return TOPICS[key][0]
    if key in GAMES:
        return GAMES[key]
    return key.replace("_", " ").title()


def subject_for(topic: str, given: str | None = None) -> str:
    """Subject the device named, else the catalog's, else 'General'."""
    if given and given.strip():
        return given.strip().title()
    return TOPICS[topic][1] if topic in TOPICS else "General"


# Match whole words only ('arrange' must not match 'range'); a trailing s/es is allowed.
_PATTERNS = [
    (topic, kw, re.compile(rf"(?<![a-z]){re.escape(kw)}(?:s|es)?(?![a-z])"))
    for topic, (_, _, kws) in TOPICS.items() for kw in kws
]


def tag_question(text: str) -> str | None:
    """Best-guess topic for a question, or None. This is keyword matching, so it is a hint, not
    a judgement: the most specific (longest) keyword wins, e.g. 'highest common factor' -> HCF, not Factors."""
    lowered = text.lower()
    best: tuple[str, int] | None = None
    for topic, kw, pattern in _PATTERNS:
        if pattern.search(lowered) and (best is None or len(kw) > best[1]):
            best = (topic, len(kw))
    return best[0] if best else None
