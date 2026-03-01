# Smart Universal Image Extractor

A **production-ready GUI application** to extract and download all images from any website — including JavaScript-rendered content, CSS backgrounds, and API/CDN images. Supports **concurrent crawling**, **async downloads**, **category-based folder organisation**, and a **live progress bar**.

---

## Features

- **Dual-mode crawling** — fast `aiohttp` fetch for static pages, Playwright fallback for JS-rendered pages.
- Automatically detects and downloads images from:
  - `<img>` tags (`src`, `srcset`, `data-src`, `data-original`, `data-lazy`)
  - CSS `background-image` styles
  - Network responses (API/CDN images captured in real time)
- **SSL verification disabled** by default — works on sites with self-signed or misconfigured certificates.
- Blocks unnecessary resources during crawl (CSS, JS, fonts, media) for faster page loads.
- Skips redundant URL variants — filters out WooCommerce/shop filter params (`?yith_wcan`, `?add-to-cart`, `?orderby`, etc.) and irrelevant paths (`/cart`, `/checkout`, `/wp-admin`, etc.).
- Async downloads with **live progress bar** and download counter.
- Automatically splits downloads into **category subfolders** based on URL path (e.g., `/shop/`, `/wp-content/`).
- Polished dark-themed **Tkinter GUI** with colour-coded log output.
- Fully cross-platform (macOS, Windows, Linux) with Python 3.12+.

---

## Screenshots

*(Optional: Add screenshots here of the GUI, progress bar, and logs.)*

---

## Requirements

- **Python 3.12+**
- Python packages:

```bash
pip install aiohttp beautifulsoup4 playwright
playwright install chromium
```

---

## Installation

1. Clone this repository:

```bash
git clone <repository-url>
cd <repository-folder>
```

2. Create a virtual environment (recommended):

```bash
python3.12 -m venv venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows
```

3. Install dependencies:

```bash
pip install aiohttp beautifulsoup4 playwright
playwright install chromium
```

---

## Usage

1. Run the application:

```bash
python web_image_extractor.py
```

2. Enter the target website URL.
3. Click **Folder** to choose where images will be saved (defaults to current directory).
4. Click **Start** to begin.
5. Watch the log for real-time crawl and download status:
   - `[fast]` — page fetched via aiohttp (no browser)
   - `[pw]` — page rendered via Playwright
   - `[err]` — page or download failed
   - Green lines — successfully saved images
6. Images are saved into subfolders automatically by URL category.

---

## Configuration

Key constants at the top of the script can be tuned to your needs:

| Constant | Default | Description |
|---|---|---|
| `MAX_CRAWL_WORKERS` | `15` | Concurrent page crawl workers |
| `MAX_DOWNLOAD_CONNECTIONS` | `100` | Concurrent image download connections |
| `PAGE_TIMEOUT_MS` | `45000` | Playwright page load timeout (ms) |
| `DOWNLOAD_RETRIES` | `2` | Retry attempts per image |
| `SKIP_QUERY_PARAMS` | see script | URL query params to skip (filters, sorting, etc.) |
| `SKIP_PATH_KEYWORDS` | see script | URL path segments to skip (cart, admin, etc.) |

---

## Packaging (Optional)

### macOS / Windows

```bash
pip install pyinstaller
pyinstaller --onefile --windowed web_image_extractor.py
```

Output will be in the `dist/` folder — a standalone `.app` on macOS or `.exe` on Windows.

---

## Notes

- The app uses **Playwright Chromium** by default. Other browsers can be installed via `playwright install firefox` or `playwright install webkit`.
- SSL verification is disabled to handle sites with self-signed or misconfigured certificates. This is safe for scraping purposes but do not use in security-sensitive contexts.
- For very large websites, consider adding a page limit to avoid crawling thousands of pages.

---

## License

MIT License  
(c) 2026 [Your Name or Organisation]

---

## Acknowledgements

- [Playwright](https://playwright.dev/python/) — headless browser automation
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) — HTML parsing
- [aiohttp](https://docs.aiohttp.org/) — asynchronous HTTP requests
