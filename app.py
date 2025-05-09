from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
)
import os
import datetime
import threading
import json # For saving/loading crawled_data.json
import crawler
import comparator

SCREENSHOT_DIRECTORY_NAME = "screenshots"

app = Flask(
    __name__,
    static_folder=SCREENSHOT_DIRECTORY_NAME,
    static_url_path="/static",
)

app.config["UPLOAD_FOLDER"] = SCREENSHOT_DIRECTORY_NAME
# Ensure the base screenshots directory exists (crawler also creates subdirs)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

app.secret_key = "your_very_secret_random_string_here" # Ensure this is a strong, unique key

comparison_results = []
crawl_status = {"running": False, "message": ""}

# --- Helper Functions for Managing Crawled Data ---
def save_crawled_data(data_to_save, directory_path, filename="crawled_data.json"):
    if not data_to_save:
        print(f"Warning: No data provided to save for {directory_path}")
        return
    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)
    filepath = os.path.join(directory_path, filename)
    try:
        with open(filepath, 'w') as f:
            json.dump(data_to_save, f, indent=4)
        print(f"Crawled data saved successfully to {filepath}")
    except Exception as e:
        print(f"ERROR: Could not save crawled data to {filepath}: {e}")

def load_crawled_data(full_directory_path, filename="crawled_data.json"):
    filepath = os.path.join(full_directory_path, filename)
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        print(f"Crawled data loaded successfully from {filepath}")
        return data
    except FileNotFoundError:
        print(f"ERROR: Crawled data file not found at {filepath}. Cannot load.")
    except json.JSONDecodeError:
        print(f"ERROR: Crawled data file at {filepath} is corrupted or not valid JSON.")
    except Exception as e:
        print(f"ERROR: Could not load crawled data from {filepath}: {e}")
    return None

def list_available_crawls_grouped(base_screenshot_dir):
    grouped_crawls = {}
    if not os.path.exists(base_screenshot_dir):
        print(f"Warning: Base screenshot directory '{base_screenshot_dir}' not found.")
        return grouped_crawls
    
    for site_name_folder in os.listdir(base_screenshot_dir):
        abs_site_path = os.path.join(base_screenshot_dir, site_name_folder)
        if os.path.isdir(abs_site_path):
            timestamps = []
            for timestamp_folder in os.listdir(abs_site_path):
                abs_timestamp_path = os.path.join(abs_site_path, timestamp_folder)
                if os.path.isdir(abs_timestamp_path) and \
                   os.path.exists(os.path.join(abs_timestamp_path, "crawled_data.json")):
                    timestamps.append(timestamp_folder)
            if timestamps:
                grouped_crawls[site_name_folder] = sorted(timestamps, reverse=True) # Newest first
    return grouped_crawls

# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def index():
    global comparison_results, crawl_status # Using global for simplicity
    
    # For GET: retrieve last used values from session to pre-fill form
    form_url1 = session.get("last_url1", "")
    form_url2 = session.get("last_url2", "")
    selected_existing_crawl1 = session.get('last_existing_crawl_url1', '')
    selected_existing_crawl2 = session.get('last_existing_crawl_url2', '')

    if request.method == "POST":
        form_url1 = request.form.get("url1")
        form_url2 = request.form.get("url2")
        session["last_url1"] = form_url1
        session["last_url2"] = form_url2

        selected_existing_crawl1 = request.form.get('existing_crawl_url1', '')
        selected_existing_crawl2 = request.form.get('existing_crawl_url2', '')
        session['last_existing_crawl_url1'] = selected_existing_crawl1
        session['last_existing_crawl_url2'] = selected_existing_crawl2

        available_crawls_for_template = list_available_crawls_grouped(app.config['UPLOAD_FOLDER'])

        if not form_url1 or not form_url2:
            return render_template("index.html", error="Please provide both URLs.",
                                   results=comparison_results, crawl_status=crawl_status,
                                   form_url1=form_url1, form_url2=form_url2,
                                   selected_existing_crawl1=selected_existing_crawl1,
                                   selected_existing_crawl2=selected_existing_crawl2,
                                   available_crawls=available_crawls_for_template)
        if crawl_status["running"]:
            return render_template("index.html", error="A crawl is already in progress.",
                                   results=comparison_results, crawl_status=crawl_status,
                                   form_url1=form_url1, form_url2=form_url2,
                                   selected_existing_crawl1=selected_existing_crawl1,
                                   selected_existing_crawl2=selected_existing_crawl2,
                                   available_crawls=available_crawls_for_template)

        comparison_results = [] # Reset results for new comparison
        new_run_timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        # Determine site names for directory creation (if crawling new)
        s1_domain = crawler.get_domain(form_url1)
        s1_name_sanitized = s1_domain.replace('.', '_') if s1_domain else "website1_default"
        s2_domain = crawler.get_domain(form_url2)
        s2_name_sanitized = s2_domain.replace('.', '_') if s2_domain else "website2_default"

        site1_info = {'site_name_sanitized': s1_name_sanitized}
        if selected_existing_crawl1: # A specific folder path like 'site_name_folder/timestamp'
            site1_info['action'] = 'load'
            site1_info['path'] = selected_existing_crawl1 
        else: # "Crawl Fresh" was selected
            site1_info['action'] = 'crawl'
            # New path will be constructed in run_comparison_workflow using site_name_sanitized and new_run_timestamp

        site2_info = {'site_name_sanitized': s2_name_sanitized}
        if selected_existing_crawl2:
            site2_info['action'] = 'load'
            site2_info['path'] = selected_existing_crawl2
        else:
            site2_info['action'] = 'crawl'
        
        crawl_status["running"] = True
        crawl_status["message"] = "Processing... preparing to crawl or load data."
        
        thread = threading.Thread(target=run_comparison_workflow,
                                  args=(form_url1, site1_info,
                                        form_url2, site2_info,
                                        new_run_timestamp)) # Pass timestamp for new crawls
        thread.start()
        return redirect(url_for("index"))

    # For GET request (initial load or after redirect)
    available_crawls = list_available_crawls_grouped(app.config['UPLOAD_FOLDER'])
    return render_template(
        "index.html",
        results=comparison_results,
        crawl_status=crawl_status,
        form_url1=form_url1,
        form_url2=form_url2,
        selected_existing_crawl1=selected_existing_crawl1,
        selected_existing_crawl2=selected_existing_crawl2,
        available_crawls=available_crawls
    )

def run_comparison_workflow(url1, site1_info, url2, site2_info, new_run_timestamp):
    global comparison_results, crawl_status # Using global for simplicity
    pages1_data = None
    pages2_data = None
    
    try:
        # --- Website 1 Processing ---
        if site1_info['action'] == 'crawl':
            # Construct path for the new crawl based on its sanitized name and the new timestamp
            site1_output_dir = os.path.join(app.config['UPLOAD_FOLDER'], site1_info['site_name_sanitized'], new_run_timestamp)
            os.makedirs(site1_output_dir, exist_ok=True)
            print(f"Starting FRESH CRAWL for Website 1 (Legacy): {url1} -> saving to {site1_output_dir}")
            pages1_data = crawler.crawl_website(url1, site1_output_dir, is_modern_site=False) # output_dir_base is where it saves images
            if pages1_data:
                save_crawled_data(pages1_data, site1_output_dir) # Save metadata in the same folder
            else:
                print(f"Warning: No pages_data returned from crawling {url1}")
        elif site1_info['action'] == 'load':
            # site1_info['path'] is 'site_name_folder/timestamp_folder'
            full_load_path = os.path.join(app.config['UPLOAD_FOLDER'], site1_info['path'])
            print(f"LOADING existing data for Website 1 (Legacy) from: {full_load_path}")
            pages1_data = load_crawled_data(full_load_path)
        
        if not pages1_data:
            raise Exception(f"Failed to get data for Website 1 ({url1}).")
        print(f"Data acquired for Website 1: {len(pages1_data)} pages found.")

        # --- Website 2 Processing ---
        if site2_info['action'] == 'crawl':
            site2_output_dir = os.path.join(app.config['UPLOAD_FOLDER'], site2_info['site_name_sanitized'], new_run_timestamp)
            os.makedirs(site2_output_dir, exist_ok=True)
            print(f"Starting FRESH CRAWL for Website 2 (Modern): {url2} -> saving to {site2_output_dir}")
            pages2_data = crawler.crawl_website(url2, site2_output_dir, is_modern_site=True)
            if pages2_data:
                save_crawled_data(pages2_data, site2_output_dir)
            else:
                print(f"Warning: No pages_data returned from crawling {url2}")
        elif site2_info['action'] == 'load':
            full_load_path = os.path.join(app.config['UPLOAD_FOLDER'], site2_info['path'])
            print(f"LOADING existing data for Website 2 (Modern) from: {full_load_path}")
            pages2_data = load_crawled_data(full_load_path)

        if not pages2_data:
            raise Exception(f"Failed to get data for Website 2 ({url2}).")
        print(f"Data acquired for Website 2: {len(pages2_data)} pages found.")

        # --- Comparison ---
        print("Comparing pages...")
        comparison_results = comparator.compare_pages(pages1_data, pages2_data, url1, url2)
        crawl_status["message"] = "Comparison finished successfully!"

    except Exception as e:
        print(f"ERROR during comparison workflow: {e}")
        crawl_status["message"] = f"Workflow Error: {str(e)}" # Display the error message
    finally:
        crawl_status["running"] = False


if __name__ == "__main__":
    app.run(debug=True)
