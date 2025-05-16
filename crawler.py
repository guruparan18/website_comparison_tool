import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import (
    Service as ChromeService,
)  # For newer Selenium
from webdriver_manager.chrome import (
    ChromeDriverManager,
)  # Optional: for easy driver management
import time
import os
from PIL import Image

ELEMENT_SELECTORS_TO_HIDE_ON_NEW_SITE = None
# [
    # ".usa-accordion",  # Selector for the accordion
    # "#alertBanner",  # Selector for the alert banner (using ID is more specific)
    # "#app-footer",
    # "#top-navigation",
# ]

ELEMENT_SELECTORS_TO_HIDE_ON_LEGACY_SITE = None
# [
    # "#stacks_in_474_31"  # Use this if the ID is static and reliable
    # "#stacks_out_474_31"
    # ".stacks_in.com_elixir_stacks_foundryContainer_stack",
# ]

STOP_CRAWL_URLS_LEGACY = []
STOP_CRAWL_URLS_MODERN = []

EXTENSIONS_TO_IGNORE = [".pdf", ".mp4"]


# --- Helper to get domain ---
def get_domain(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return None


# --- URL Normalization for path matching ---
def normalize_path_segment(path_segment):
    s = path_segment.lower()
    if s.endswith(".html"):
        s = s[:-5]
    s = s.replace("_", "-")
    return s


def get_normalized_relative_path(base_url, url):
    parsed_url = urlparse(url)
    # Ensure we only process paths and ignore queries/fragments for normalization
    path_segments = [
        normalize_path_segment(seg)
        for seg in parsed_url.path.strip("/").split("/")
        if seg
    ]
    normalized_path = "/".join(path_segments)
    return normalized_path


TARGET_DESKTOP_WIDTH = 1920
TARGET_INITIAL_DESKTOP_HEIGHT = (
    1080  # A common default, also acts as a minimum screenshot height
)


# --- Selenium Screenshot Function ---
def take_fullpage_screenshot(
    driver,
    url,
    output_path,
    apply_element_hiding=False,
    selectors_list_to_hide=None,
):  # Changed parameter name for clarity
    """
    Navigates to a URL, optionally hides specified elements, and takes a full-page screenshot.
    """
    try:
        driver.get(url)
        time.sleep(3)  # Wait for initial page load

        # Conditionally hide elements if this is the modern site and selectors are provided
        if (
            apply_element_hiding
            and selectors_list_to_hide
            and isinstance(selectors_list_to_hide, list)
        ):
            print(f"[{url}] Attempting to hide specified elements...")
            any_element_actioned = False
            for selector in selectors_list_to_hide:  # Use the passed list
                if not selector.strip():
                    continue
                try:
                    js_hide_elements = f"""
                        let els = document.querySelectorAll('{selector}');
                        let hiddenCount = 0;
                        if (els.length > 0) {{
                            els.forEach(function(el) {{
                                el.style.display = 'none';
                                hiddenCount++;
                            }});
                        }}
                        return hiddenCount;
                    """
                    num_hidden = driver.execute_script(js_hide_elements)
                    if num_hidden > 0:
                        print(
                            f"    - Hidden {num_hidden} element(s) for selector '{selector}'."
                        )
                        any_element_actioned = True
                    else:
                        print(f"    - No elements found for selector '{selector}'.")
                except Exception as e:
                    print(
                        f"    - Error trying to hide elements for selector '{selector}': {e}"
                    )

            if any_element_actioned:
                time.sleep(0.5)
                print(f"[{url}] Element hiding process completed.")
        elif apply_element_hiding and selectors_list_to_hide:
            print(
                f"[{url}] Warning: selectors_list_to_hide was provided but is not a list. Type: {type(selectors_list_to_hide)}"
            )

        # Reset window to a known state before measuring the new page's content.
        # print(f"[{url}] Resetting window to: {TARGET_DESKTOP_WIDTH}x{TARGET_INITIAL_DESKTOP_HEIGHT}") # Already verbose
        driver.set_window_size(TARGET_DESKTOP_WIDTH, TARGET_INITIAL_DESKTOP_HEIGHT)
        time.sleep(0.5)

        js_get_page_dimensions = """
            return {
                width: Math.max(
                    document.body.scrollWidth, document.documentElement.scrollWidth,
                    document.body.offsetWidth, document.documentElement.offsetWidth,
                    document.body.clientWidth, document.documentElement.clientWidth
                ),
                height: Math.max(
                    document.body.scrollHeight, document.documentElement.scrollHeight,
                    document.body.offsetHeight, document.documentElement.offsetHeight,
                    document.body.clientHeight, document.documentElement.clientHeight
                )
            };
        """
        dimensions = driver.execute_script(js_get_page_dimensions)
        page_content_height = dimensions["height"]
        screenshot_width = TARGET_DESKTOP_WIDTH
        screenshot_height = max(page_content_height, TARGET_INITIAL_DESKTOP_HEIGHT)

        # print(f"[{url}] Page content height: {page_content_height}px. Final screenshot size: {screenshot_width}x{screenshot_height}") # Already verbose
        driver.set_window_size(screenshot_width, screenshot_height)
        time.sleep(1.5)

        driver.save_screenshot(output_path)
        print(f"[{url}] Screenshot saved: {output_path}")
        page_title = driver.title
        return page_title

    except Exception as e:
        print(f"[{url}] General error in take_fullpage_screenshot: {e}")
        try:
            driver.set_window_size(TARGET_DESKTOP_WIDTH, TARGET_INITIAL_DESKTOP_HEIGHT)
        except Exception as reset_e:
            print(f"[{url}] Could not reset window size after error: {reset_e}")
        return None


# --- Main Crawl Function ---
def crawl_website(start_url, output_dir_base, is_modern_site=False):
    # ... (domain_name, to_visit, visited, pages_data, chrome_options, driver init as before) ...
    domain_name = get_domain(start_url)
    if not domain_name:  # ... (handle invalid start URL)
        return {}
    # ... (Initialize chrome_options, driver etc.)
    to_visit = {start_url}
    visited = set()
    pages_data = {}

    chrome_options = Options()  # Re-initialize or ensure it's correctly scoped
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(
        f"window-size={TARGET_DESKTOP_WIDTH},{TARGET_INITIAL_DESKTOP_HEIGHT}"
    )
    try:
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=chrome_options,
        )
    except Exception as e:
        print(f"Failed to initialize WebDriver: {e}.")
        return {}

    count = 0
    while to_visit:
        current_url = to_visit.pop()
        # ... (URL parsing, extension skipping, visited check as before) ...
        parsed_current_url = urlparse(current_url)
        current_url_path_lower = parsed_current_url.path.lower()
        if any(current_url_path_lower.endswith(ext) for ext in EXTENSIONS_TO_IGNORE):
            visited.add(current_url)
            continue
        if current_url in visited:
            continue

        visited.add(current_url)
        print(f"Visiting: {current_url} (Is Modern Site: {is_modern_site})")

        try:
            # ... (screenshot filename generation) ...
            relative_url_path = parsed_current_url.path.strip("/")
            if not relative_url_path:
                filename_base = "index"
            else:
                filename_base = relative_url_path.replace("/", "_").replace(".", "_")
            screenshot_filename = f"page_{count}_{filename_base}.png"
            full_screenshot_path = os.path.join(output_dir_base, screenshot_filename)

            # Determine which selectors to use based on the site type
            current_stop_list = (
                STOP_CRAWL_URLS_MODERN if is_modern_site else STOP_CRAWL_URLS_LEGACY
            )
            selectors_for_current_site = None
            if is_modern_site:
                selectors_for_current_site = ELEMENT_SELECTORS_TO_HIDE_ON_NEW_SITE
            else:  # It's the legacy site
                selectors_for_current_site = ELEMENT_SELECTORS_TO_HIDE_ON_LEGACY_SITE

            should_apply_hiding = bool(
                selectors_for_current_site
            )  # True if list is not empty/None

            page_title = take_fullpage_screenshot(
                driver,
                current_url,
                full_screenshot_path,
                apply_element_hiding=should_apply_hiding,
                selectors_list_to_hide=selectors_for_current_site,
            )
            count += 1

            # ... (pages_data population and link finding logic as before) ...
            if page_title is not None:
                normalized_path = get_normalized_relative_path(start_url, current_url)
                pages_data[normalized_path] = {
                    "img_path": full_screenshot_path,
                    "title": page_title,
                    "full_url": current_url,
                }
            try:
                page_content_response = requests.get(current_url, timeout=10)
                page_content_response.raise_for_status()
                if (
                    "text/html"
                    not in page_content_response.headers.get("Content-Type", "").lower()
                ):
                    continue
                soup = BeautifulSoup(page_content_response.content, "html.parser")
            except requests.RequestException as e:
                print(
                    f"Could not fetch content for link extraction from {current_url}: {e}"
                )
                continue

            for link in soup.find_all("a", href=True):
                href = link["href"]
                # ... (URL processing for links as before) ...
                joined_url = urljoin(current_url, href)
                parsed_joined_url = urlparse(joined_url)
                clean_url_path_lower = parsed_joined_url.path.lower()
                clean_url_for_visit = parsed_joined_url._replace(
                    query="", fragment=""
                ).geturl()

                if any(
                    clean_url_path_lower.endswith(ext) for ext in EXTENSIONS_TO_IGNORE
                ):
                    continue
                if (
                    get_domain(clean_url_for_visit) == domain_name
                    and clean_url_for_visit not in visited
                ):
                    to_visit.add(clean_url_for_visit)
        except Exception as e:
            print(f"Error processing {current_url}: {e}")

    driver.quit()
    return pages_data
