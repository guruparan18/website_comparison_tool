from skimage.metrics import structural_similarity as ssim
import cv2 # OpenCV
from PIL import Image
import numpy as np
import os

STATIC_FOLDER_FOR_FLASK = 'static' # This should be the name of your static folder in Flask

def normalize_url_for_matching(url_path_segment):
    # Remove .html (if present at the end of a segment or whole path)
    if url_path_segment.endswith(".html"):
        url_path_segment = url_path_segment[:-5]
    # Replace _ with -
    url_path_segment = url_path_segment.replace("_", "-")
    # Ensure consistency, e.g. remove trailing slashes if desired
    url_path_segment = url_path_segment.strip('/')
    return url_path_segment

def create_thumbnail(image_path, thumb_path, size=(50, 100)):
    try:
        img = Image.open(image_path)
        img.thumbnail(size)
        img.save(thumb_path)
        # Return path relative to static folder for web display
        return os.path.join(os.path.basename(os.path.dirname(thumb_path)), os.path.basename(thumb_path))
    except Exception as e:
        print(f"Error creating thumbnail for {image_path}: {e}")
        return None

def compare_images_ssim(image_path1, image_path2):
    try:
        img1 = cv2.imread(image_path1)
        img2 = cv2.imread(image_path2)

        if img1 is None or img2 is None:
            print(f"Could not read one or both images: {image_path1}, {image_path2}")
            return None

        # Convert images to grayscale for SSIM
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

        # Resize images to the same dimensions for comparison if they are different
        # It's generally better if screenshots are taken at the same resolution
        # but if not, resizing is necessary. Choose the smaller dimensions or a fixed one.
        h1, w1 = gray1.shape
        h2, w2 = gray2.shape

        if h1 != h2 or w1 != w2:
            print(f"Warning: Image dimensions differ. Resizing {image_path2} to match {image_path1} for comparison.")
            # Option 1: Resize img2 to img1's dimensions
            gray2 = cv2.resize(gray2, (w1, h1), interpolation=cv2.INTER_AREA)
            # Option 2: Resize both to a common dimension (e.g., minimum)
            # min_h = min(h1, h2)
            # min_w = min(w1, w2)
            # gray1 = cv2.resize(gray1, (min_w, min_h), interpolation=cv2.INTER_AREA)
            # gray2 = cv2.resize(gray2, (min_w, min_h), interpolation=cv2.INTER_AREA)


        score, diff = ssim(gray1, gray2, full=True) # `full=True` returns the diff image as well
        return score
    except Exception as e:
        print(f"Error comparing images {image_path1} and {image_path2}: {e}")
        return None


def compare_pages(pages1_data, pages2_data, base_url1, base_url2):
    """
    Compares pages based on normalized URLs and titles.
    pages1_data, pages2_data: Dictionaries from crawl_website
    {normalized_relative_path: {'img_path': '...', 'title': '...', 'full_url': '...'}}
    """
    results = []
    # Ensure the static folder exists at the root of the Flask app
    # The paths in pages_data are absolute, we need to make them relative for Flask.
    # Example: screenshots/site1_com/20240101120000/page_0_index.png
    # We need it as: site1_com/20240101120000/page_0_index.png for url_for('static', filename=...)

    # Create a combined set of all unique normalized paths
    all_normalized_paths = set(pages1_data.keys()) | set(pages2_data.keys())

    for norm_path in all_normalized_paths:
        data1 = pages1_data.get(norm_path)
        data2 = pages2_data.get(norm_path)

        result_entry = {
            "normalized_path": norm_path,
            "title1": data1['title'] if data1 else "N/A (Not crawled/found)",
            "title2": data2['title'] if data2 else "N/A (Not crawled/found)",
            "full_url1": data1['full_url'] if data1 else "#",
            "full_url2": data2['full_url'] if data2 else "#",
            "img1_full": None, "img1_thumb": None,
            "img2_full": None, "img2_thumb": None,
            "score": None
        }

        # --- Prepare paths for Flask's static serving ---
        # The img_path from crawler is like: 'screenshots/domain_com/timestamp/image.png'
        # We need to make it 'domain_com/timestamp/image.png' to be served from the 'screenshots' static folder
        # Flask's `static_url_path` defaults to `/static`. If `UPLOAD_FOLDER` is `screenshots`,
        # then `url_for('static', filename='screenshots_subfolder/image.png')`
        # So, paths should be relative to the `screenshots` directory.

        if data1:
            # Make path relative to 'screenshots' folder for Flask's `url_for`
            relative_img1_full = os.path.relpath(data1['img_path'], STATIC_FOLDER_FOR_FLASK)
            result_entry["img1_full"] = relative_img1_full.replace(os.sep, '/') # Ensure web paths
            thumb_name1 = "thumb_" + os.path.basename(data1['img_path'])
            thumb_dir1 = os.path.dirname(data1['img_path']) # Full path to thumb dir
            full_thumb_path1 = os.path.join(thumb_dir1, thumb_name1)
            # Create thumbnail and get its path relative to STATIC_FOLDER_FOR_FLASK
            created_thumb_path1 = create_thumbnail(data1['img_path'], full_thumb_path1)
            if created_thumb_path1:
                 # created_thumb_path1 is already relative to STATIC_FOLDER_FOR_FLASK/screenshots_subfolder/
                 # so it needs to be combined with its parent dirs relative to static.
                result_entry["img1_thumb"] = os.path.relpath(full_thumb_path1, STATIC_FOLDER_FOR_FLASK).replace(os.sep, '/')


        if data2:
            relative_img2_full = os.path.relpath(data2['img_path'], STATIC_FOLDER_FOR_FLASK)
            result_entry["img2_full"] = relative_img2_full.replace(os.sep, '/')
            thumb_name2 = "thumb_" + os.path.basename(data2['img_path'])
            thumb_dir2 = os.path.dirname(data2['img_path'])
            full_thumb_path2 = os.path.join(thumb_dir2, thumb_name2)
            created_thumb_path2 = create_thumbnail(data2['img_path'], full_thumb_path2)
            if created_thumb_path2:
                result_entry["img2_thumb"] = os.path.relpath(full_thumb_path2, STATIC_FOLDER_FOR_FLASK).replace(os.sep, '/')


        if data1 and data2:
            # Compare only if both pages were successfully crawled and screenshotted
            score = compare_images_ssim(data1['img_path'], data2['img_path'])
            result_entry["score"] = score
            if score is not None:
                print(f"Comparison: {norm_path} -> SSIM: {score:.4f}")
            else:
                print(f"Comparison failed for: {norm_path}")
        elif data1:
            print(f"Page only in site 1: {norm_path} ({data1['full_url']})")
        elif data2:
            print(f"Page only in site 2: {norm_path} ({data2['full_url']})")

        results.append(result_entry)

    # Sort results, e.g., by score (descending for better matches first, or handle None)
    results.sort(key=lambda x: (x['score'] is not None, x['score']), reverse=True)
    return results
