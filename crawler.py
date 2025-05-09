import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService # For newer Selenium
from webdriver_manager.chrome import ChromeDriverManager # Optional: for easy driver management
import time
import os
from PIL import Image

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
    path_segments = [normalize_path_segment(seg) for seg in parsed_url.path.strip("/").split("/") if seg]
    normalized_path = "/".join(path_segments)
    return normalized_path


TARGET_DESKTOP_WIDTH = 1920
TARGET_INITIAL_DESKTOP_HEIGHT = 1080 # A common default, also acts as a minimum screenshot height
# --- Selenium Screenshot Function ---
def take_fullpage_screenshot(driver, url, output_path):
    try:
        driver.get(url)
        # Allow time for initial page load, JavaScript execution, and content rendering
        time.sleep(3) # Adjust this based on typical page load times

        # 1. Reset window to a defined "standard" size before measuring the new page.
        # This is crucial to ensure that the scrollHeight of a short page isn't
        # measured while the viewport is still artificially tall from a previous long page.
        print(f"[{url}] Resetting window to: {TARGET_DESKTOP_WIDTH}x{TARGET_INITIAL_DESKTOP_HEIGHT}")
        driver.set_window_size(TARGET_DESKTOP_WIDTH, TARGET_INITIAL_DESKTOP_HEIGHT)
        # Allow a brief moment for the browser to reflow after this reset
        time.sleep(0.5)

        # 2. Get the actual content dimensions of the *currently loaded page*.
        # Using Math.max with various properties for robustness.
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
        
        page_content_height = dimensions['height']
        # The screenshot width will be our target desktop width.
        # The page's actual content width (dimensions['width']) might be different (e.g. if page is not responsive or narrower by design)
        # but we force TARGET_DESKTOP_WIDTH for consistency in "desktop view" testing.
        screenshot_width = TARGET_DESKTOP_WIDTH
        
        # The screenshot height should be the page's full scroll height,
        # but not less than our defined initial/minimum height to avoid overly small/problematic screenshots.
        screenshot_height = max(page_content_height, TARGET_INITIAL_DESKTOP_HEIGHT)

        print(f"[{url}] Page content height: {page_content_height}px. Final screenshot size: {screenshot_width}x{screenshot_height}")

        # 3. Set window size to capture the full page content.
        driver.set_window_size(screenshot_width, screenshot_height)
        # IMPORTANT: Wait for the browser to re-render the page at the new (potentially very tall) size.
        # This duration might need adjustment for pages with complex layouts or heavy JavaScript.
        time.sleep(1.5) # Increased from 0.5 or 1 to give more reliable rendering time

        # 4. Save the screenshot.
        driver.save_screenshot(output_path)
        print(f"[{url}] Screenshot saved: {output_path}")

        page_title = driver.title
        
        # 5. Optional: Reset window size back to initial default after screenshot.
        # While the next call to this function will do its own reset, this can be
        # a good practice if the driver instance is used for other things between screenshot calls.
        # driver.set_window_size(TARGET_DESKTOP_WIDTH, TARGET_INITIAL_DESKTOP_HEIGHT)
        # time.sleep(0.1) # Brief pause

        return page_title

    except Exception as e:
        print(f"[{url}] Error taking screenshot: {e}")
        # Attempt to reset window size to a known default if an error occurs,
        # to minimize impact on subsequent screenshot attempts with the same driver instance.
        try:
            driver.set_window_size(TARGET_DESKTOP_WIDTH, TARGET_INITIAL_DESKTOP_HEIGHT)
        except Exception as reset_e:
            print(f"[{url}] Could not reset window size after error: {reset_e}")
        return None


# --- Main Crawl Function ---
def crawl_website(start_url, output_dir_base):
    """
    Crawls a website starting from start_url, takes screenshots,
    and stores them. Ignores URLs ending with .pdf.
    Returns a dictionary: {normalized_relative_path: {'path': 'screenshot_path.png', 'title': 'Page Title', 'full_url': '...'}}
    """
    domain_name = get_domain(start_url)
    if not domain_name:
        print(f"Invalid start URL: {start_url}")
        return {}

    to_visit = {start_url}
    visited = set()
    pages_data = {}

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"window-size={TARGET_DESKTOP_WIDTH},{TARGET_INITIAL_DESKTOP_HEIGHT}")

    try:
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
    except Exception as e:
        print(f"Failed to initialize WebDriver: {e}. Ensure ChromeDriver is installed and in PATH.")
        return {}

    count = 0
    while to_visit:
        current_url = to_visit.pop()

        # Check if URL ends with .pdf (case-insensitive) before processing
        parsed_current_url = urlparse(current_url)
        if parsed_current_url.path.lower().endswith(".pdf"):
            print(f"Skipping PDF URL: {current_url}")
            visited.add(current_url) # Add to visited to avoid re-adding from other pages
            continue

        if current_url in visited:
            continue

        visited.add(current_url)
        print(f"Visiting: {current_url}")

        try:
            relative_url_path = parsed_current_url.path.strip('/')
            if not relative_url_path:
                filename_base = "index"
            else:
                filename_base = relative_url_path.replace('/', '_').replace('.', '_')
            screenshot_filename = f"page_{count}_{filename_base}.png"
            full_screenshot_path = os.path.join(output_dir_base, screenshot_filename)

            page_title = take_fullpage_screenshot(driver, current_url, full_screenshot_path)
            count += 1

            if page_title is not None:
                normalized_path = get_normalized_relative_path(start_url, current_url)
                pages_data[normalized_path] = {
                    'img_path': full_screenshot_path,
                    'title': page_title,
                    'full_url': current_url
                }

            # --- Find internal links ---
            # Use requests for fetching HTML to find links, as Selenium is slower for this part
            # Ensure requests also skips PDFs if it tries to fetch their content type for some reason (though not strictly necessary here)
            try:
                # Perform a HEAD request first to check content type if needed,
                # or just rely on URL string for link discovery.
                # For now, we'll just fetch and parse.
                page_content_response = requests.get(current_url, timeout=10)
                page_content_response.raise_for_status()
                # Avoid parsing non-HTML content for links
                if 'text/html' not in page_content_response.headers.get('Content-Type', '').lower():
                    print(f"Skipping link extraction from non-HTML page: {current_url}")
                    continue
                soup = BeautifulSoup(page_content_response.content, 'html.parser')
            except requests.RequestException as e:
                print(f"Could not fetch content for link extraction from {current_url}: {e}")
                continue


            for link in soup.find_all('a', href=True):
                href = link['href']
                joined_url = urljoin(current_url, href)
                parsed_joined_url = urlparse(joined_url)

                # Remove fragment and query parameters for crawling and PDF check
                clean_url_path = parsed_joined_url.path
                clean_url_for_visit = parsed_joined_url._replace(query="", fragment="").geturl()

                # Check for PDF extension on discovered links
                if clean_url_path.lower().endswith(".pdf"):
                    print(f"Ignoring discovered PDF link: {joined_url}")
                    continue

                if get_domain(clean_url_for_visit) == domain_name and clean_url_for_visit not in visited:
                    to_visit.add(clean_url_for_visit)

        except Exception as e: # Catching general exceptions from screenshotting or parsing
            print(f"Error processing {current_url}: {e}")

    driver.quit()
    return pages_data
