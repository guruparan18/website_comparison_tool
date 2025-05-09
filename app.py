from flask import Flask, render_template, request, redirect, url_for, session # Added session
import os
import datetime
import threading
import crawler # Assuming crawler.py is in the same directory
import comparator # Assuming comparator.py is in the same directory

SCREENSHOT_DIRECTORY_NAME = 'screenshots'

app = Flask(__name__,
            static_folder=SCREENSHOT_DIRECTORY_NAME,  # Tell Flask to use 'screenshots' as the static folder
            static_url_path='/static') 

app.config['UPLOAD_FOLDER'] = SCREENSHOT_DIRECTORY_NAME
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# IMPORTANT: Set a secret key for session management!
# Replace 'your secret key' with a strong, random string.
app.secret_key = 'your_very_secret_random_string_here'

# --- Global state (Consider alternatives for multi-user or production) ---
comparison_results = []
crawl_status = {"running": False, "message": ""}
# ---

def normalize_url_for_matching(url): # This function seems unused in app.py, ensure it's in comparator or crawler if needed there
    url = url.replace(".html", "")
    url = url.replace("_", "-")
    return url

@app.route('/', methods=['GET', 'POST'])
def index():
    global comparison_results, crawl_status
    form_url1 = session.get('last_url1', '')
    form_url2 = session.get('last_url2', '')

    if request.method == 'POST':
        url1_from_form = request.form.get('url1')
        url2_from_form = request.form.get('url2')
        session['last_url1'] = url1_from_form
        session['last_url2'] = url2_from_form
        form_url1 = url1_from_form
        form_url2 = url2_from_form

        if not form_url1 or not form_url2:
            return render_template('index.html', error="Please provide both URLs.", results=comparison_results, crawl_status=crawl_status, form_url1=form_url1, form_url2=form_url2)
        if crawl_status["running"]:
            return render_template('index.html', error="A crawl is already in progress.", results=comparison_results, crawl_status=crawl_status, form_url1=form_url1, form_url2=form_url2)
        
        comparison_results = []
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        repo_path = app.config['UPLOAD_FOLDER']
        site1_domain = crawler.get_domain(form_url1)
        site2_domain = crawler.get_domain(form_url2)
        site1_name = site1_domain.replace('.', '_') if site1_domain else "website1"
        site2_name = site2_domain.replace('.', '_') if site2_domain else "website2"
        path1 = os.path.join(repo_path, site1_name, timestamp)
        path2 = os.path.join(repo_path, site2_name, timestamp)
        os.makedirs(path1, exist_ok=True)
        os.makedirs(path2, exist_ok=True)

        crawl_status["running"] = True
        crawl_status["message"] = "Crawling and comparison in progress..."
        thread = threading.Thread(target=run_comparison_workflow, args=(form_url1, form_url2, path1, path2))
        thread.start()
        return redirect(url_for('index'))
    return render_template('index.html', results=comparison_results, crawl_status=crawl_status, form_url1=form_url1, form_url2=form_url2)

def run_comparison_workflow(url1, url2, path1, path2):
    global comparison_results, crawl_status
    try:
        print(f"Starting crawl for Website 1: {url1}")
        pages1 = crawler.crawl_website(url1, path1)
        print(f"Found {len(pages1)} pages for Website 1.")
        print(f"Starting crawl for Website 2: {url2}")
        pages2 = crawler.crawl_website(url2, path2)
        print(f"Found {len(pages2)} pages for Website 2.")
        print("Comparing pages...")
        comparison_results = comparator.compare_pages(pages1, pages2, url1, url2)
        crawl_status["message"] = "Crawling and comparison finished!"
    except Exception as e:
        print(f"Error during workflow: {e}")
        crawl_status["message"] = f"Error: {e}"
    finally:
        crawl_status["running"] = False

if __name__ == '__main__':
    app.run(debug=True)
