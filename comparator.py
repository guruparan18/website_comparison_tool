# comparator.py
from skimage.metrics import structural_similarity as ssim
import cv2
from PIL import Image
import numpy as np
import os
import time

# This constant MUST match the value of static_folder in app.py's Flask constructor
# AND app.config['UPLOAD_FOLDER']. It's the root directory for all screenshot data.
BASE_SCREENSHOT_DIR_NAME = "screenshots"
MAX_COMPARISON_DIMENSION = 1920  # For resizing images before SSIM

MIN_CONTOUR_AREA = 100
PIXEL_DIFF_THRESHOLD = 30


def analyze_pixel_and_structural_differences(
    image_path1, image_path2, diff_image_save_rel_path=None
):
    """
    Compares two images using SSIM and also calculates pixel difference percentage,
    and saves a visual diff image.
    diff_image_save_rel_path: Project-relative path to save the diff image,
                              e.g., 'screenshots/site_name/timestamp/diff_page.png'
    """
    analysis_results = {
        "ssim_score": None,
        "diff_percent": None,
        "num_significant_diff_regions": 0,
        "largest_diff_area_percent": None,  # Placeholder for future contour analysis
        "diff_image_template_path": None,  # For url_for in template
    }

    try:
        pil_img1_orig = Image.open(image_path1)
        pil_img2_orig = Image.open(image_path2)

        # --- Convert to Grayscale and Resize for SSIM and Diff ---
        # Reusing similar resizing logic from your existing compare_images_ssim
        # Ensure pil_img1 and pil_img2 are the resized grayscale PIL images of the same dimensions
        pil_img1 = pil_img1_orig.convert("L")
        pil_img2 = pil_img2_orig.convert("L")

        w1, h1 = pil_img1.size
        w2, h2 = pil_img2.size

        if (
            w1 != w2
            or h1 != h2
            or w1 > MAX_COMPARISON_DIMENSION
            or h1 > MAX_COMPARISON_DIMENSION
            or w2 > MAX_COMPARISON_DIMENSION
            or h2 > MAX_COMPARISON_DIMENSION
        ):
            target_w = min(w1, w2, MAX_COMPARISON_DIMENSION)
            r1 = target_w / float(w1) if w1 > 0 else 0
            th1 = int(h1 * r1)
            r2 = target_w / float(w2) if w2 > 0 else 0
            th2 = int(h2 * r2)

            if w1 != target_w or h1 != th1:
                pil_img1 = pil_img1.resize(
                    (max(1, target_w), max(1, th1)), Image.LANCZOS
                )
            if w2 != target_w or h2 != th2:
                pil_img2 = pil_img2.resize(
                    (max(1, target_w), max(1, th2)), Image.LANCZOS
                )

            final_h = min(pil_img1.height, pil_img2.height)
            final_w = pil_img1.width  # Widths should be same now
            if pil_img1.height != final_h:
                pil_img1 = pil_img1.resize((final_w, final_h), Image.LANCZOS)
            if pil_img2.height != final_h:
                pil_img2 = pil_img2.resize((final_w, final_h), Image.LANCZOS)

        gray1_np = np.array(pil_img1)  # Already grayscale PIL image
        gray2_np = np.array(pil_img2)

        if gray1_np.shape != gray2_np.shape:
            print(
                f"  ERROR: Shape mismatch for diff analysis after resize: {gray1_np.shape} vs {gray2_np.shape}"
            )
            return analysis_results  # Return defaults

        # 1. SSIM Score
        score, ssim_diff_map = ssim(
            gray1_np, gray2_np, full=True
        )  # Get full diff map if needed later
        analysis_results["ssim_score"] = score

        # 2. Pixel Difference Percentage
        abs_diff_img = cv2.absdiff(gray1_np, gray2_np)
        # Threshold needs tuning: lower is more sensitive. Start with 25-35.
        _, threshold_img = cv2.threshold(
            abs_diff_img, PIXEL_DIFF_THRESHOLD, 255, cv2.THRESH_BINARY
        )

        img_h, img_w = threshold_img.shape
        total_pixels_in_image = img_h * img_w
        diff_pixels = cv2.countNonZero(threshold_img)
        analysis_results["diff_percent"] = (
            (diff_pixels / total_pixels_in_image) * 100
            if total_pixels_in_image > 0
            else 0
        )

        # 3. Contour Analysis on the threshold_img
        # Use threshold_img.copy() if findContours modifies the source (depends on OpenCV version)
        contours, _ = cv2.findContours(
            threshold_img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        significant_contours = []
        if contours:
            for contour in contours:
                area = cv2.contourArea(contour)
                if area >= MIN_CONTOUR_AREA:
                    significant_contours.append(contour)

            analysis_results["num_significant_diff_regions"] = len(significant_contours)

            if significant_contours:
                largest_contour = max(significant_contours, key=cv2.contourArea)
                largest_area = cv2.contourArea(largest_contour)
                analysis_results["largest_diff_region_area_percent"] = (
                    (largest_area / total_pixels_in_image) * 100
                    if total_pixels_in_image > 0
                    else 0.0
                )

        # 4. Save Visual Difference Image (the thresholded one)
        if diff_image_save_rel_path:
            abs_save_path = os.path.abspath(
                diff_image_save_rel_path
            )  # Already project-relative
            try:
                os.makedirs(os.path.dirname(abs_save_path), exist_ok=True)
                # Save the threshold_img (black and white diff)
                Image.fromarray(threshold_img).save(
                    abs_save_path
                )  # Use Pillow to save to handle paths easily
                analysis_results["diff_image_template_path"] = _get_path_for_template(
                    diff_image_save_rel_path
                )
                print(f"  Visual difference image saved: {abs_save_path}")
            except Exception as e_save:
                print(f"  ERROR saving visual diff image to {abs_save_path}: {e_save}")

        return analysis_results

    except FileNotFoundError:
        print(
            f"Error in analysis: File not found. Img1: {image_path1}, Img2: {image_path2}"
        )
        return analysis_results
    except Exception as e:
        print(
            f"Error during image difference analysis ({os.path.basename(image_path1)} vs {os.path.basename(image_path2)}): {e}"
        )
        return analysis_results


def _get_path_for_template(project_relative_path):
    norm_path = os.path.normpath(project_relative_path)
    parts = norm_path.split(os.sep)
    if parts and parts[0] == BASE_SCREENSHOT_DIR_NAME:
        template_path = os.path.join(*parts[1:])
        return template_path.replace(os.sep, "/")
    else:
        print(
            f"ERROR: Path '{project_relative_path}' doesn't start with base dir '{BASE_SCREENSHOT_DIR_NAME}'."
        )
        return None


def create_thumbnail(source_project_rel_path, thumb_project_rel_path, size=(50, 100)):
    try:
        abs_source_path = os.path.abspath(source_project_rel_path)
        abs_thumb_save_path = os.path.abspath(thumb_project_rel_path)
        os.makedirs(os.path.dirname(abs_thumb_save_path), exist_ok=True)
        img = Image.open(abs_source_path)
        img.thumbnail(size)
        img.save(abs_thumb_save_path)
        return _get_path_for_template(thumb_project_rel_path)
    except FileNotFoundError:
        print(
            f"Error creating thumbnail: Source not found at '{source_project_rel_path}'"
        )
        return None
    except Exception as e:
        print(f"Error creating thumbnail from '{source_project_rel_path}': {e}")
        return None


# (compare_images_ssim function - use the robust one from previous answers that handles resizing)
def compare_images_ssim(image_path1, image_path2):
    # This is the robust version from previous answers that handles resizing and errors
    try:
        pil_img1 = Image.open(image_path1).convert("L")
        pil_img2 = Image.open(image_path2).convert("L")
        gray1_pil_w, gray1_pil_h = pil_img1.size
        gray2_pil_w, gray2_pil_h = pil_img2.size

        needs_resize1 = (
            gray1_pil_w != gray2_pil_w
            or gray1_pil_h != gray2_pil_h
            or gray1_pil_w > MAX_COMPARISON_DIMENSION
            or gray1_pil_h > MAX_COMPARISON_DIMENSION
        )
        needs_resize2 = (
            gray1_pil_w != gray2_pil_w
            or gray1_pil_h != gray2_pil_h
            or gray2_pil_w > MAX_COMPARISON_DIMENSION
            or gray2_pil_h > MAX_COMPARISON_DIMENSION
        )

        if needs_resize1 or needs_resize2:
            target_w = min(gray1_pil_w, gray2_pil_w, MAX_COMPARISON_DIMENSION)
            ratio1 = target_w / float(gray1_pil_w) if gray1_pil_w > 0 else 0
            target_h1 = int(gray1_pil_h * ratio1)
            if gray1_pil_w != target_w or gray1_pil_h != target_h1:
                pil_img1 = pil_img1.resize(
                    (max(1, target_w), max(1, target_h1)), Image.LANCZOS
                )

            ratio2 = target_w / float(gray2_pil_w) if gray2_pil_w > 0 else 0
            target_h2 = int(gray2_pil_h * ratio2)
            if gray2_pil_w != target_w or gray2_pil_h != target_h2:
                pil_img2 = pil_img2.resize(
                    (max(1, target_w), max(1, target_h2)), Image.LANCZOS
                )

            final_h = min(pil_img1.height, pil_img2.height)
            final_w = pil_img1.width
            if pil_img1.height != final_h:
                pil_img1 = pil_img1.resize((final_w, final_h), Image.LANCZOS)
            if pil_img2.height != final_h:
                pil_img2 = pil_img2.resize((final_w, final_h), Image.LANCZOS)

        gray1_np = np.array(pil_img1)
        gray2_np = np.array(pil_img2)

        if gray1_np.shape != gray2_np.shape:
            print(
                f"  Error: Shapes mismatch after resize: {gray1_np.shape} vs {gray2_np.shape}. Skipping."
            )
            return None

        score, diff_img = ssim(gray1_np, gray2_np, full=True)
        return score
    except FileNotFoundError:
        print(
            f"Error comparing: File not found. Img1: {image_path1}, Img2: {image_path2}"
        )
        return None
    except Exception as e:
        print(
            f"Error comparing {os.path.basename(image_path1)} and {os.path.basename(image_path2)}: {e}"
        )
        return None


def get_ssim_classification(score):
    if score is None:
        return {"text": "N/A", "range_display": "(Score not available)"}

    # Ensure score is within a typical SSIM range for classification, e.g. clamp to [-1, 1] if it can go outside
    # For scikit-image's ssim, it's usually in [-1, 1]
    score = max(-1.0, min(1.0, score))  # Clamp score just in case

    if score == 1.0:
        return {"text": "Perfect Match", "range_display": "[1.0]"}
    elif score > 0.95:
        return {"text": "Very Similar", "range_display": "(> 0.95 & < 1.0)"}
    elif score > 0.90:  # implicitly score <= 0.95
        return {"text": "Good Similarity", "range_display": "(0.90 - 0.95]"}
    elif score > 0.80:  # implicitly score <= 0.90
        return {"text": "Fair Similarity", "range_display": "(0.80 - 0.90]"}
    elif score > 0.60:  # implicitly score <= 0.80
        return {"text": "Moderate Similarity", "range_display": "(0.60 - 0.80]"}
    else:  # score <= 0.60
        return {"text": "Low Similarity", "range_display": "(<= 0.60)"}


def compare_pages(pages1_data, pages2_data, base_url1, base_url2):
    results = []
    all_normalized_paths = sorted(
        list(set(pages1_data.keys()) | set(pages2_data.keys()))
    )
    total_paths = len(all_normalized_paths)
    print(f"\nStarting comparison of {total_paths} unique page paths...")

    for i, norm_path in enumerate(all_normalized_paths):
        # ... (result_entry initialization, title, url, and thumbnail path generation as before) ...
        print(f"\n--- Comparing page {i + 1}/{total_paths}: '{norm_path}' ---")
        data1 = pages1_data.get(norm_path)
        data2 = pages2_data.get(norm_path)

        result_entry = {
            "normalized_path": norm_path,
            "title1": "N/A",
            "title2": "N/A",
            "full_url1": "#",
            "full_url2": "#",
            "img1_full": None,
            "img1_thumb": None,
            "img2_full": None,
            "img2_thumb": None,
            "score": None,
            "ssim_classification_text": "N/A",
            "ssim_classification_range": "",
            "diff_percent": None,
            "num_significant_diff_regions": 0,
            "largest_diff_region_area_percent": 0.0,
            "diff_image_template_path": None,  # New fields
        }
        # ... (Populate titles, full_urls, imgX_full, imgX_thumb paths using _get_path_for_template as before)
        if data1:
            result_entry.update(
                {
                    "title1": data1.get("title", "N/A"),
                    "full_url1": data1.get("full_url", "#"),
                }
            )
        if data2:
            result_entry.update(
                {
                    "title2": data2.get("title", "N/A"),
                    "full_url2": data2.get("full_url", "#"),
                }
            )

        if data1 and data1.get("img_path"):
            if os.path.exists(data1["img_path"]):
                result_entry["img1_full"] = _get_path_for_template(data1["img_path"])
                thumb_filename = "thumb_" + os.path.basename(data1["img_path"])
                thumb_project_rel_path = os.path.join(
                    os.path.dirname(data1["img_path"]), thumb_filename
                )
                result_entry["img1_thumb"] = create_thumbnail(
                    data1["img_path"], thumb_project_rel_path
                )
        if data2 and data2.get("img_path"):
            if os.path.exists(data2["img_path"]):
                result_entry["img2_full"] = _get_path_for_template(data2["img_path"])
                thumb_filename = "thumb_" + os.path.basename(data2["img_path"])
                thumb_project_rel_path = os.path.join(
                    os.path.dirname(data2["img_path"]), thumb_filename
                )
                result_entry["img2_thumb"] = create_thumbnail(
                    data2["img_path"], thumb_project_rel_path
                )

        if result_entry["img1_full"] and result_entry["img2_full"]:
            print(f"  Analyzing differences for '{norm_path}'...")
            start_time = time.time()

            # Construct path to save diff image
            # It will be saved relative to project root, e.g., screenshots/site1_name/timestamp/diff_norm_path.png
            diff_img_filename = f"diff_{norm_path.replace('/', '_')}_{os.path.basename(data1['img_path'])}.png"
            diff_image_save_location = None
            if data1 and data1.get("img_path"):  # Use first image's directory structure
                diff_image_save_location = os.path.join(
                    os.path.dirname(data1["img_path"]), diff_img_filename
                )

            analysis = analyze_pixel_and_structural_differences(
                data1["img_path"],  # Original project-relative path
                data2["img_path"],  # Original project-relative path
                diff_image_save_location,
            )
            end_time = time.time()
            print(
                f"  Analysis for '{norm_path}' took {end_time - start_time:.2f} seconds."
            )

            result_entry["score"] = analysis["ssim_score"]
            result_entry["diff_percent"] = analysis["diff_percent"]
            result_entry["num_significant_diff_regions"] = analysis[
                "num_significant_diff_regions"
            ]
            result_entry["largest_diff_region_area_percent"] = analysis[
                "largest_diff_region_area_percent"
            ]
            result_entry["diff_image_template_path"] = analysis[
                "diff_image_template_path"
            ]

            classification = get_ssim_classification(analysis["ssim_score"])
            result_entry["ssim_classification_text"] = classification["text"]
            result_entry["ssim_classification_range"] = classification[
                "range_display"
            ]  # Keep this for now, can be removed from display later if not needed

            if analysis["ssim_score"] is not None:
                print(
                    f"  SSIM: {analysis['ssim_score']:.4f} ({classification['text']}), "
                    f"Diff %: {analysis['diff_percent']:.2f}%, "
                    f"Sig. Regions: {analysis['num_significant_diff_regions']}, "
                    f"Largest Region: {analysis['largest_diff_region_area_percent']:.2f}%"
                )
            else:
                print(f"  Analysis failed or was skipped for '{norm_path}'.")
        # ... (elif data1, elif data2, results.append, sort) ...
        elif data1:
            print(f"  Page only in site 1: {norm_path}")
        elif data2:
            print(f"  Page only in site 2: {norm_path}")
        results.append(result_entry)

    results.sort(
        key=lambda x: (
            x["score"] is not None,
            x["score"] if x["score"] is not None else -1,
        ),
        reverse=True,
    )
    print(f"\nComparison finished. Processed {total_paths} page paths.")
    return results
