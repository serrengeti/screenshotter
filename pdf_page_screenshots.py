"""
Capture each PDF page as a PNG using Chromium/Chrome with pdf.js (canvas = page only).

Chrome's built-in PDF viewer does not expose reliable automation for cropped page shots;
this script opens the PDF in Chrome via a local viewer that renders one page per canvas.

Requires network on first run (pdf.js is loaded from CDN). Install: pip install playwright
then: playwright install chromium   (or: playwright install chrome)
"""

from __future__ import annotations

import argparse
import shutil
import socket
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

try:
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError as e:
    if e.name != "playwright":
        raise
    print(
        "Playwright is not installed for this Python.\n\n"
        "In the same environment (e.g. your conda base), run:\n"
        "  python -m pip install playwright\n"
        "  python -m playwright install chromium\n\n"
        "Or double-click: install_playwright.bat (in the screenshoter folder).",
        file=sys.stderr,
    )
    sys.exit(1)


def resolve_pdf_arg(value: str) -> Path:
    """Accept normal paths or file:/// URLs (e.g. from browser address bar)."""
    v = value.strip()
    if v.lower().startswith("file:"):
        parsed = urlparse(v)
        path = unquote(parsed.path)
        # Windows: file:///C:/... gives path "/C:/..."
        if path.startswith("/") and len(path) >= 3 and path[2] == ":":
            path = path[1:]
        return Path(path)
    return Path(v).expanduser()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start_local_server(root: Path, port: int) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _launch_browser(playwright, headless: bool):
    try:
        return playwright.chromium.launch(channel="chrome", headless=headless)
    except Exception:
        return playwright.chromium.launch(headless=headless)


def run(
    pdf_path: Path,
    start_page: int,
    end_page: int,
    output_dir: Path,
    scale: float,
    headless: bool,
) -> None:
    pdf_path = pdf_path.resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")

    script_dir = Path(__file__).resolve().parent
    viewer_src = script_dir / "viewer.html"
    if not viewer_src.is_file():
        raise SystemExit(f"Missing viewer.html next to script: {viewer_src}")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    port = _free_port()
    tmp = Path(tempfile.mkdtemp(prefix="pdfshots_"))
    try:
        shutil.copy2(pdf_path, tmp / "document.pdf")
        shutil.copy2(viewer_src, tmp / "viewer.html")

        httpd = _start_local_server(tmp, port)
        base = f"http://127.0.0.1:{port}"
        file_param = quote("document.pdf", safe="")

        with sync_playwright() as p:
            browser = _launch_browser(p, headless=headless)
            context = browser.new_context(
                viewport={"width": 2400, "height": 3200},
                device_scale_factor=1,
            )
            page = context.new_page()

            for n in range(start_page, end_page + 1):
                url = (
                    f"{base}/viewer.html?file={file_param}&page={n}&scale={scale}"
                )
                page.goto(url, wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_selector(
                    'body[data-ready="1"], body[data-error]',
                    timeout=120_000,
                )
                err = page.locator("body").get_attribute("data-error")
                if err:
                    raise RuntimeError(
                        f"Page {n} failed to render: {err}"
                    )
                page.wait_for_timeout(150)
                page.locator("#the-canvas").screenshot(
                    path=str(output_dir / f"page_{n:04d}.png"),
                    type="png",
                )

            browser.close()
            httpd.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Save PNG screenshots of PDF pages (page content only) via Chrome/Chromium.",
    )
    parser.add_argument(
        "pdf",
        type=resolve_pdf_arg,
        help="Path to the PDF file (or file:/// URL)",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        metavar="N",
        help="First page (1-based, default: 1)",
    )
    parser.add_argument(
        "--end-page",
        type=int,
        required=True,
        metavar="N",
        help="Last page (inclusive, 1-based)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("screenshots"),
        help="Folder for PNG files (default: ./screenshots)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=2.0,
        help="Render scale for sharpness (default: 2.0)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show browser window (default is headless)",
    )
    args = parser.parse_args()

    if args.end_page < args.start_page:
        print("--end-page must be >= --start-page", file=sys.stderr)
        sys.exit(2)

    run(
        args.pdf,
        args.start_page,
        args.end_page,
        args.output_dir,
        args.scale,
        headless=not args.headed,
    )


if __name__ == "__main__":
    main()
