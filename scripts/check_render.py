#!/usr/bin/env python3
"""
Sanity-check a rendered dashboard: print every value box and any 'no data' placeholders,
and fail if a Python error was rendered into the page.

    python scripts/check_render.py dashboard/index.html
"""
import html
import re
import sys

s = open(sys.argv[1] if len(sys.argv) > 1 else "dashboard/index.html", encoding="utf-8").read()
for m in re.finditer(r'value-box-title">(.*?)</p>.*?value-box-value">\s*(.*?)\s*</p>', s, re.S):
    title = html.unescape(re.sub("<[^>]+>", "", m.group(1))).strip()
    print(f"{title:45} {html.unescape(re.sub('<[^>]+>', '', m.group(2))).strip()}")
missing = sorted(set(re.findall(r"No [A-Za-z ]+ data yet", s)))
if missing:
    print("\nPlaceholders:", ", ".join(missing))
if re.search(r"Traceback \(most recent call last\)|<span class=\"ansi", s):
    sys.exit("\nERROR: a Python traceback was rendered into the page")
