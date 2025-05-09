from flask import Flask, render_template, request, redirect, url_for
import os
import datetime
import threading # To run crawling in the background

# Import your custom modules for crawling, screenshots, comparison
import crawler # Assuming you create a crawler.py
import comparator # Assuming you create a comparator.py

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'screenshots' # Base folder for screenshots
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Global state (consider a more robust solution for larger apps) ---
comparison_results = []
crawl_status = {"running": False, "message": ""}
# ---

def normalize_url_for_matching(url):
    # Remove .html
    url = url.replace(".html", "")
    # Replace _ with - (and vice-versa, ensure canonical form)
    # For simplicity, let's decide one canonical form, e.g., always use '-'
    url = url.replace("_", "-")
    return url

@app.route('/', methods=['GET', 'POST'])
def index():
    global comparison_results, crawl_status
    if request.method == 'POST':
        url1 = request.form.get('url1')
        url2 = request.form.get('url2')

        if not url1 or not url2:
            return render_template('index.html', error="Please provide both URLs.", results=comparison_results, crawl_status=crawl_status)

        if crawl_status["running"]:
            return render_template('index.html', error="A crawl is already in progress.", results=comparison_results, crawl_status=crawl_status)

        # --- Reset previous results ---
        comparison_results = []
        # ---

        # Create unique directories for this run
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        repo_path = os.path.join(app.config['UPLOAD_FOLDER']) # 'screenshots'
        # Sanitize website names for directory creation
        site1_name = crawler.get_domain(url1).replace('.', '_')
        site2_name = crawler.get_domain(url2).replace('.', '_')

        path1 = os.path.join(repo_path, site1_name, timestamp)
        path2 = os.path.join(repo_path, site2_name, timestamp)
        os.makedirs(path1, exist_ok=True)
        os.makedirs(path2, exist_ok=True)

        # --- Start crawling and comparison in a new thread to avoid blocking the UI ---
        crawl_status["running"] = True
        crawl_status["message"] = "Crawling and comparison in progress..."
        thread = threading.Thread(target=run_comparison_workflow, args=(url1, url2, path1, path2))
        thread.start()
        # ---

        return redirect(url_for('index')) # Redirect to show progress/results

    return render_template('index.html', results=comparison_results, crawl_status=crawl_status)

def run_comparison_workflow(url1, url2, path1, path2):
    global comparison_results, crawl_status
    try:
        print(f"Starting crawl for Website 1: {url1}")
        pages1 = crawler.crawl_website(url1, path1) # Returns a dict: {normalized_url: {path: '...', title: '...'}}
        print(f"Found {len(pages1)} pages for Website 1.")

        print(f"Starting crawl for Website 2: {url2}")
        pages2 = crawler.crawl_website(url2, path2) # Returns a dict
        print(f"Found {len(pages2)} pages for Website 2.")

        print("Comparing pages...")
        comparison_results = comparator.compare_pages(pages1, pages2, url1, url2) # Updates the global results
        crawl_status["message"] = "Crawling and comparison finished!"
    except Exception as e:
        print(f"Error during workflow: {e}")
        crawl_status["message"] = f"Error: {e}"
    finally:
        crawl_status["running"] = False


if __name__ == '__main__':
    app.run(debug=True)
