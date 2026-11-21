#!/usr/bin/env python3
"""
Open a rendered dashboard in headless Chromium and check what only a browser can see:
every itables table initialises, every Altair chart on every page and tab is drawn with a
non-zero size, and the page raises no JavaScript errors.

    pip install playwright && python -m playwright install --with-deps chromium-headless-shell
    python scripts/check_browser.py dashboard/index.html [--screenshots DIR]

Serves the page over http (file:// blocks Quarto's module scripts). Exit 1 on any problem.
"""
import argparse
import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

CHARTS_JS = """() => [...document.querySelectorAll('div[id^="vega-"]')].filter(d => d.offsetParent !== null)
  .map(d => { const c = d.querySelector('canvas, svg'); if (!c) return 0;
              const r = c.getBoundingClientRect(); return Math.min(r.width, r.height); })"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--screenshots", help="directory to save one screenshot per page")
    args = ap.parse_args()
    page_file = Path(args.html).resolve()

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(page_file.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/{page_file.name}"

    problems, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url)
        pg.wait_for_timeout(4000)

        n_tables = pg.locator("table").count()
        ok_tables = pg.locator("table.dataTable").count()
        stuck = pg.evaluate("() => [...document.querySelectorAll('table')]"
                            ".filter(t => t.textContent.includes('Loading ITables')).length")
        print(f"tables: {ok_tables} initialised, {stuck} stuck on 'Loading ITables' ({n_tables} <table> total)")
        if stuck:
            problems.append(f"{stuck} itables table(s) never initialised")

        nav = pg.locator(".navbar .navbar-nav a.nav-link")       # dashboard pages (top bar)
        names = [n.strip() for n in nav.all_inner_texts() if n.strip()]
        for i, name in enumerate(dict.fromkeys(names)):
            pg.locator("a.nav-link", has_text=name).first.click()
            pg.wait_for_timeout(1200)
            # visit every tab inside this page too
            tabs = pg.locator(".tab-pane.active .nav-tabs a.nav-link:visible, "
                              ".dashboard-page.active .nav-tabs a.nav-link:visible")
            tab_names = [t.strip() for t in tabs.all_inner_texts() if t.strip()] or [None]
            for tab in tab_names:
                if tab:
                    pg.locator(".nav-tabs a.nav-link:visible", has_text=tab).first.click()
                    pg.wait_for_timeout(800)
                sizes = pg.evaluate(CHARTS_JS)
                where = f"{name}{' / ' + tab if tab else ''}"
                print(f"  {where}: {len(sizes)} chart(s) {[round(s) for s in sizes]}")
                bad = [s for s in sizes if s < 50]
                if bad:
                    problems.append(f"{where}: {len(bad)} chart(s) not drawn (size < 50 px)")
            if args.screenshots:
                Path(args.screenshots).mkdir(parents=True, exist_ok=True)
                pg.screenshot(path=str(Path(args.screenshots) / f"{i}-{name.replace(' ', '_')}.png"))
        browser.close()
    server.shutdown()

    for e, n in {e: errors.count(e) for e in errors}.items():
        problems.append(f"JavaScript error ({n}x): {e[:200]}")
    if problems:
        print("\nFAILED:\n- " + "\n- ".join(problems))
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
