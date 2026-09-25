import re

PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:"
    r"(?P<prefix>(?:\b(?:US\$|USD|EUR|GBP|ZAR)\b|R(?=\s*[+\-\u2013\u2014]?\s*\d)|[\$€£])\s*)"
    r")?"
    r"(?P<sign>[+\-\u2013\u2014])?\s*"
    r"(?P<num>\d{1,3}(?:[ \u00a0]\d{3}(?!\d))+(?:[.,]\d+)?|\d{1,3}(?:,\d{3}(?!\d))+(?:\.\d+)?|\d+[.,]\d+|\d+)"
    r"(?P<suffix>%(?:\s*points?)?|\s*(?:billion|milli?on|cents?|c\b|bn\b|m\b|thousand|k\b))?",
    re.IGNORECASE
)

for tc in ["Revenue R235,6 billion, up 4,3%; up 6,8%", "Cash generated ... R16,6 billion", "R2 562 million", "Q3 2025", "$13.7 million"]:
    print(f"\n{tc}:")
    for m in PATTERN.finditer(tc):
        print(" ", m.group(0), "-> prefix:", m.group('prefix'), "num:", m.group('num'), "suffix:", m.group('suffix'))
