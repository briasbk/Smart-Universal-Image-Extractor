import os
import re
import asyncio
import threading
import random
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────
VALID_EXTENSIONS       = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif", ".bmp", ".tiff"}
BLOCKED_RESOURCE_TYPES = {"font", "media", "stylesheet", "script", "other"}
MAX_CRAWL_WORKERS      = 15
MAX_DOWNLOAD_CONNECTIONS = 100
GUI_UPDATE_INTERVAL    = 5       # update progress bar every N downloads
SCROLL_TIMES           = 1
PAGE_TIMEOUT_MS        = 45_000  # increased for slow sites
DOWNLOAD_RETRIES       = 2
DOWNLOAD_RETRY_DELAY   = 0.5

# Query params that produce filtered/duplicate page variants — skip them
SKIP_QUERY_PARAMS = {
    "yith_wcan", "filters", "filter", "orderby",
    "min_price", "max_price", "product_tag",
    "pa_color", "pa_size", "paged", "ajax", "add-to-cart",
}

# Path segments not worth crawling
SKIP_PATH_KEYWORDS = {
    "/cart", "/checkout", "/my-account", "/wp-login",
    "/wp-admin", "/feed", "/xmlrpc", "/.well-known",
}


# ─────────────────────────────────────────────
#  App
# ─────────────────────────────────────────────
class FullWebsiteImageExtractor:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Full Website Image Extractor")
        self.root.geometry("900x680")

        self._build_ui()

        # Internal state
        self.output_folder: str      = os.getcwd()
        self.image_urls: set[str]    = set()
        self.visited_pages: set[str] = set()
        self.domain: str             = ""
        self.total_images: int       = 0
        self.downloaded_images: int  = 0
        self._lock                   = threading.Lock()

    # ─────────────────────────────────────────
    #  UI
    # ─────────────────────────────────────────
    def _build_ui(self):
        BG        = "#1a1a2e"
        SURFACE   = "#16213e"
        ACCENT    = "#0f3460"
        HIGHLIGHT = "#e94560"
        TEXT      = "#eaeaea"
        MUTED     = "#8892b0"

        self.root.configure(bg=BG)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=SURFACE, background=HIGHLIGHT,
                        bordercolor=ACCENT, lightcolor=HIGHLIGHT, darkcolor=HIGHLIGHT)

        # Header
        header = tk.Frame(self.root, bg=ACCENT, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="Website Image Extractor",
                 font=("Courier New", 16, "bold"), bg=ACCENT, fg=HIGHLIGHT).pack()
        tk.Label(header, text="Crawl · Detect · Download",
                 font=("Courier New", 9), bg=ACCENT, fg=MUTED).pack()

        # URL row
        url_frame = tk.Frame(self.root, bg=BG, pady=8)
        url_frame.pack(fill=tk.X, padx=15)
        tk.Label(url_frame, text="URL:", bg=BG, fg=MUTED,
                 font=("Courier New", 10)).pack(side=tk.LEFT)
        self.url_entry = tk.Entry(url_frame, width=65, bg=SURFACE, fg=TEXT,
                                  insertbackground=TEXT, relief=tk.FLAT,
                                  font=("Courier New", 10), bd=6)
        self.url_entry.pack(side=tk.LEFT, padx=8)

        # Controls row
        ctrl = tk.Frame(self.root, bg=BG, pady=4)
        ctrl.pack(fill=tk.X, padx=15)

        self.folder_button = tk.Button(ctrl, text="Folder", command=self.select_folder,
                                       bg=ACCENT, fg=TEXT, relief=tk.FLAT,
                                       font=("Courier New", 9, "bold"), padx=8, pady=4,
                                       activebackground=HIGHLIGHT, activeforeground=TEXT,
                                       cursor="hand2")
        self.folder_button.pack(side=tk.LEFT, padx=(0, 6))

        self.folder_label = tk.Label(ctrl, text=os.getcwd(), bg=BG, fg=MUTED,
                                     font=("Courier New", 9), anchor="w")
        self.folder_label.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        self.start_button = tk.Button(ctrl, text="Start", command=self.start_extraction,
                                      bg=HIGHLIGHT, fg=TEXT, relief=tk.FLAT,
                                      font=("Courier New", 10, "bold"), padx=14, pady=4,
                                      activebackground="#c73652", activeforeground=TEXT,
                                      cursor="hand2")
        self.start_button.pack(side=tk.RIGHT)

        # Progress row
        prog = tk.Frame(self.root, bg=BG, pady=6)
        prog.pack(fill=tk.X, padx=15)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(prog, variable=self.progress_var,
                                             maximum=100, length=650, style="TProgressbar")
        self.progress_bar.pack(side=tk.LEFT)
        self.counter_label = tk.Label(prog, text="0 / 0", bg=BG, fg=MUTED,
                                      font=("Courier New", 9), width=12)
        self.counter_label.pack(side=tk.LEFT, padx=8)

        # Stats row
        stats = tk.Frame(self.root, bg=BG)
        stats.pack(fill=tk.X, padx=15)
        self.pages_label  = tk.Label(stats, text="Pages: 0",
                                     bg=BG, fg=MUTED, font=("Courier New", 9))
        self.images_label = tk.Label(stats, text="Images found: 0",
                                     bg=BG, fg=MUTED, font=("Courier New", 9))
        self.pages_label.pack(side=tk.LEFT, padx=(0, 20))
        self.images_label.pack(side=tk.LEFT)

        # Log area
        log_frame = tk.Frame(self.root, bg=BG, pady=6)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))
        self.log_area = scrolledtext.ScrolledText(log_frame, height=28,
                                                   bg=SURFACE, fg=TEXT,
                                                   font=("Courier New", 9),
                                                   insertbackground=TEXT,
                                                   relief=tk.FLAT, bd=0)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.tag_config("ok",   foreground="#64ffda")
        self.log_area.tag_config("err",  foreground="#ff6b6b")
        self.log_area.tag_config("info", foreground="#8892b0")
        self.log_area.tag_config("head", foreground="#e94560")

    # ─────────────────────────────────────────
    #  Logging
    # ─────────────────────────────────────────
    def log(self, message: str, tag: str = "info"):
        self.log_area.insert(tk.END, message + "\n", tag)
        self.log_area.see(tk.END)

    # ─────────────────────────────────────────
    #  Folder selection
    # ─────────────────────────────────────────
    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder = folder
            self.folder_label.config(text=folder)
            self.log(f"Download folder set to: {folder}")

    # ─────────────────────────────────────────
    #  Start
    # ─────────────────────────────────────────
    def start_extraction(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a website URL.")
            return

        # Reset state
        self.image_urls.clear()
        self.visited_pages.clear()
        self.downloaded_images = 0
        self.total_images      = 0
        self.log_area.delete("1.0", tk.END)

        self.start_button.config(state=tk.DISABLED)
        threading.Thread(target=lambda: asyncio.run(self.run_extraction(url)),
                         daemon=True).start()

    # ─────────────────────────────────────────
    #  Auto-scroll helper
    # ─────────────────────────────────────────
    async def auto_scroll(self, page, times: int = SCROLL_TIMES):
        for _ in range(times):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(random.randint(300, 600))

    # ─────────────────────────────────────────
    #  URL filtering
    # ─────────────────────────────────────────
    def _should_skip(self, url: str) -> bool:
        """Return True for URLs that are redundant or not worth crawling."""
        parsed = urlparse(url)

        # Skip known filter/pagination query params
        query = parsed.query.lower()
        if any(param in query for param in SKIP_QUERY_PARAMS):
            return True

        # Skip blacklisted path segments
        path = parsed.path.lower()
        if any(kw in path for kw in SKIP_PATH_KEYWORDS):
            return True

        return False

    # ─────────────────────────────────────────
    #  Extract images + internal links from HTML
    # ─────────────────────────────────────────
    def extract_from_html(self, html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        new_links: list[str] = []

        # img tags
        for img in soup.find_all("img"):
            for attr in ("src", "data-src", "data-original", "data-lazy"):
                src = img.get(attr)
                if src and not src.startswith("data:"):
                    self._add_image(urljoin(base_url, src))
            srcset = img.get("srcset")
            if srcset:
                for part in srcset.split(","):
                    self._add_image(urljoin(base_url, part.strip().split()[0]))

        # CSS background-image
        for tag in soup.find_all(style=True):
            for m in re.findall(r'url\(["\']?(.*?)["\']?\)', tag["style"]):
                if m and not m.startswith("data:"):
                    self._add_image(urljoin(base_url, m))

        # Internal links — strip fragments before dedup
        for a in soup.find_all("a", href=True):
            full   = urljoin(base_url, a["href"])
            parsed = urlparse(full)
            clean  = parsed._replace(fragment="").geturl()
            if parsed.netloc == self.domain and clean not in self.visited_pages:
                new_links.append(clean)

        return new_links

    def _add_image(self, url: str):
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if ext in VALID_EXTENSIONS or not ext:
            self.image_urls.add(url)

    # ─────────────────────────────────────────
    #  Fast fetch via aiohttp (no JS)
    # ─────────────────────────────────────────
    async def _fast_fetch(self, session: aiohttp.ClientSession, url: str) -> str | None:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ct = resp.headers.get("content-type", "")
                if resp.status == 200 and "html" in ct:
                    return await resp.text(errors="replace")
        except Exception:
            pass
        return None

    # ─────────────────────────────────────────
    #  Crawl single page
    # ─────────────────────────────────────────
    async def crawl_page(self, context, url: str, queue: asyncio.Queue,
                         session: aiohttp.ClientSession, semaphore: asyncio.Semaphore):
        async with semaphore:
            if url in self.visited_pages:
                return
            self.visited_pages.add(url)
            self.root.after(0, lambda: self.pages_label.config(
                text=f"Pages: {len(self.visited_pages)}"))

            # Fast path: plain HTTP, no browser
            html = await self._fast_fetch(session, url)
            if html:
                new_links = self.extract_from_html(html, url)
                self._enqueue_links(new_links, queue)
                self.root.after(0, lambda: self.images_label.config(
                    text=f"Images found: {len(self.image_urls)}"))
                self.log(f"[fast] {url}", "info")
                return

            # Playwright fallback for JS-rendered pages
            page = await context.new_page()
            try:
                # Block heavy resources
                await page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in BLOCKED_RESOURCE_TYPES
                    else route.continue_()
                )

                # Navigate — on timeout still extract partial content rather than discarding
                try:
                    await page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                except Exception:
                    # Give it 5 more seconds, then proceed with whatever loaded
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=5_000)
                    except Exception:
                        pass

                await self.auto_scroll(page)
                html = await page.content()
                new_links = self.extract_from_html(html, url)
                self._enqueue_links(new_links, queue)
                self.root.after(0, lambda: self.images_label.config(
                    text=f"Images found: {len(self.image_urls)}"))
                self.log(f"[pw]   {url}", "info")

            except Exception as e:
                # Only show first line — Playwright errors include long call logs
                short_err = str(e).split("\n")[0]
                self.log(f"[err]  {url} -> {short_err}", "err")
            finally:
                await page.close()
                await asyncio.sleep(random.uniform(0.05, 0.2))

    def _enqueue_links(self, links: list[str], queue: asyncio.Queue):
        for link in links:
            if link not in self.visited_pages and not self._should_skip(link):
                queue.put_nowait(link)

    # ─────────────────────────────────────────
    #  Crawl entire website
    # ─────────────────────────────────────────
    async def crawl_website(self, start_url: str):
        self.domain = urlparse(start_url).netloc
        queue: asyncio.Queue[str] = asyncio.Queue()
        queue.put_nowait(start_url)
        semaphore = asyncio.Semaphore(MAX_CRAWL_WORKERS)

        connector = aiohttp.TCPConnector(limit=MAX_DOWNLOAD_CONNECTIONS, ssl=False)
        async with aiohttp.ClientSession(
            connector=connector,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ImageBot/1.0)"}
        ) as session:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()

                # Capture images loaded via network responses
                async def handle_response(response):
                    ct = response.headers.get("content-type", "")
                    if "image" in ct:
                        self._add_image(response.url)

                context.on("response", handle_response)

                # Live worker pool — no idle gaps between crawl waves
                active: set[asyncio.Task] = set()

                while not queue.empty() or active:
                    while not queue.empty() and len(active) < MAX_CRAWL_WORKERS * 2:
                        url = await queue.get()
                        if url not in self.visited_pages:
                            task = asyncio.create_task(
                                self.crawl_page(context, url, queue, session, semaphore)
                            )
                            active.add(task)
                            task.add_done_callback(active.discard)

                    if active:
                        await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                    else:
                        await asyncio.sleep(0.05)

                await browser.close()

    # ─────────────────────────────────────────
    #  Download single image
    # ─────────────────────────────────────────
    async def download_image(self, session: aiohttp.ClientSession, img_url: str, idx: int):
        for attempt in range(DOWNLOAD_RETRIES):
            try:
                async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        self.log(f"  [skip] HTTP {resp.status}: {img_url}", "err")
                        return
                    data = await resp.read()

                if not data:
                    self.log(f"  [skip] Empty response: {img_url}", "err")
                    return

                category = self._categorize(img_url)
                folder   = os.path.join(self.output_folder, category)
                os.makedirs(folder, exist_ok=True)

                raw_name = os.path.basename(urlparse(img_url).path) or f"image_{idx}"
                filename = re.sub(r'[<>:"/\\|?*]', "_", raw_name)
                # Ensure a file extension exists
                if not os.path.splitext(filename)[1]:
                    filename += ".jpg"
                filepath = os.path.join(folder, filename)

                # Avoid overwriting existing files
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(filepath):
                    filepath = os.path.join(folder, f"{base}_{counter}{ext}")
                    counter += 1

                with open(filepath, "wb") as f:
                    f.write(data)

                with self._lock:
                    self.downloaded_images += 1
                    dl = self.downloaded_images

                # Update GUI on every download
                pct = dl / self.total_images * 100 if self.total_images else 0
                self.root.after(0, lambda p=pct, d=dl: (
                    self.progress_var.set(p),
                    self.counter_label.config(text=f"{d} / {self.total_images}")
                ))

                self.log(f"  {category}/{filename}", "ok")
                return

            except Exception as e:
                self.log(f"  [retry {attempt+1}] {img_url} -> {e}", "err")
                await asyncio.sleep(DOWNLOAD_RETRY_DELAY)

        self.log(f"  [failed] {img_url}", "err")

    def _categorize(self, img_url: str) -> str:
        parts = urlparse(img_url).path.strip("/").split("/")
        return parts[0] if parts and parts[0] else "uncategorized"

    # ─────────────────────────────────────────
    #  Download all images
    # ─────────────────────────────────────────
    async def download_all_images(self):
        self.total_images      = len(self.image_urls)
        self.downloaded_images = 0
        self.log(f"\n-- Downloading {self.total_images} images --", "head")
        self.root.after(0, lambda: (
            self.progress_var.set(0),
            self.counter_label.config(text=f"0 / {self.total_images}")
        ))

        connector = aiohttp.TCPConnector(limit=MAX_DOWNLOAD_CONNECTIONS, ssl=False)
        async with aiohttp.ClientSession(
            connector=connector,
            headers={"User-Agent": "Mozilla/5.0"}
        ) as session:
            tasks = [
                self.download_image(session, url, i)
                for i, url in enumerate(self.image_urls)
            ]
            await asyncio.gather(*tasks)

        self.log("\n-- All downloads complete --", "head")

    # ─────────────────────────────────────────
    #  Orchestrator
    # ─────────────────────────────────────────
    async def run_extraction(self, start_url: str):
        self.log(f"Starting crawl: {start_url}", "head")
        try:
            await self.crawl_website(start_url)
            self.log(
                f"\nFound {len(self.image_urls)} unique images "
                f"across {len(self.visited_pages)} pages.",
                "head"
            )
            await self.download_all_images()
        except Exception as e:
            self.log(f"Fatal error: {e}", "err")
        finally:
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = FullWebsiteImageExtractor(root)
    root.mainloop()
