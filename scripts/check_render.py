#!/usr/bin/env python3
"""
Sanity-check a rendered dashboard: print every value box and any 'no data' placeholders,
and fail if a Python error was rendered into the page.

    python scripts/check_render.py dashboard/index.html            # report
    python scripts/check_render.py dashboard/index.html --strict   # also fail on placeholders / missing values
"""
import html
import re
import sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
strict = "--strict" in sys.argv
s = open(args[0] if args else "dashboard/index.html", encoding="utf-8").read()
boxes = 0
missing_values = []
for m in re.finditer(r'value-box-title">(.*?)</p>.*?value-box-value">\s*(.*?)\s*</p>', s, re.S):
    title = html.unescape(re.sub("<[^>]+>", "", m.group(1))).strip()
    value = html.unescape(re.sub("<[^>]+>", "", m.group(2))).strip()
    print(f"{title:45} {value}")
    boxes += 1
    if value in ("", "–"):
        missing_values.append(title)
missing = sorted(set(re.findall(r"No [A-Za-z ]+ data yet", s)))
if missing:
    print("\nPlaceholders:", ", ".join(missing))
if boxes == 0:
    sys.exit("\nERROR: no value boxes found - did the page render?")
if strict and (missing or missing_values):
    sys.exit(f"\nERROR (--strict): placeholders {missing} / empty value boxes {missing_values}")
if re.search(r"Traceback \(most recent call last\)|<span class=\"ansi", s):
    sys.exit("\nERROR: a Python traceback was rendered into the page")
