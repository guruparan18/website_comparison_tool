from skimage.metrics import structural_similarity as ssim
import cv2
from PIL import Image # Using Pillow for robust image opening and thumbnails
import numpy as np
import os
import time # For potential timing/debugging

# Path to the folder where Flask serves static files from (e.g. 'screenshots')
# This needs to align with your Flask app's static_folder configuration for screenshots.
STATIC_FOLDER_FOR_FLASK = 'screenshots'

# Define a maximum dimension for comparison to speed up SSIM and reduce memory.
# Images will be resized (downscaled) if their width or height exceeds this.
MAX_COMPARISON_DIMENSION = 1920 # e.g., Resize to fit within 1920x1920

def create_thumbnail(image_path, thumb_path, size=(50, 100)):
    try:
        img = Image.open(image_path)
        img.thumbnail(size) # Preserves aspect ratio
        img.save(thumb_path)
        # Return path relative to the base of STATIC_FOLDER_FOR_FLASK
        # Example: if STATIC_FOLDER_FOR_FLASK is 'screenshots' and thumb_path is 'screenshots/site/ts/thumb_img.png'
        # this should return 'site/ts/thumb_img.png'
        return os.path.relpath(thumb_path, STATIC_FOLDER_FOR_FLASK).replace(os.sep, '/')
    except FileNotFoundError:
        print(f"Error creating thumbnail: Source image not found at {image_path}")
        return None
    except Exception as e:
        print(f"Error creating thumbnail for {os.path.basename(image_path)}: {e}")
        return None

def compare_images_ssim(image_path1, image_path2):
    try:
        # Load images using Pillow (more robust for various formats) then convert to OpenCV
        pil_img1 = Image.open(image_path1).convert('L') # Convert to grayscale with Pillow
        pil_img2 = Image.open(image_path2).convert('L')

        gray1_pil_w, gray1_pil_h = pil_img1.size
        gray2_pil_w, gray2_pil_h = pil_img2.size

        # If dimensions differ, or if images are too large, resize them
        # to a standard size for comparison.
        needs_resize1 = gray1_pil_w != gray2_pil_w or gray1_pil_h != gray2_pil_h or \
                        gray1_pil_w > MAX_COMPARISON_DIMENSION or gray1_pil_h > MAX_COMPARISON_DIMENSION
        needs_resize2 = gray1_pil_w != gray2_pil_w or gray1_pil_h != gray2_pil_h or \
                        gray2_pil_w > MAX_COMPARISON_DIMENSION or gray2_pil_h > MAX_COMPARISON_DIMENSION

        if needs_resize1 or needs_resize2:
            print(f"  Info: Standardizing image sizes for comparison. Original {os.path.basename(image_path1)}: {gray1_pil_w}x{gray1_pil_h}, {os.path.basename(image_path2)}: {gray2_pil_w}x{gray2_pil_h}.")
            
            # Determine a common target size, e.g., resize both to fit within MAX_COMPARISON_DIMENSION
            # while maintaining aspect ratio, and using the smaller of the two original aspect ratios as a guide, or simply resize both to same target.
            # For simplicity: resize both to have their largest dimension be MAX_COMPARISON_DIMENSION
            # Or, resize to the dimensions of the smaller image if one is much larger.

            # Strategy: Resize both images so their largest dimension is MAX_COMPARISON_DIMENSION,
            # then ensure they are the exact same size (e.g., by padding or slight crop, or resizing one to match other).
            # Simpler: Resize both to a fixed target if different, e.g. fixed width, proportional height.

            # Let's use a simpler strategy: if dimensions differ or are too large,
            # resize both to have their width as MAX_COMPARISON_DIMENSION (or smaller if original is smaller)
            # and proportional height. Then make heights equal.

            target_w = min(gray1_pil_w, gray2_pil_w, MAX_COMPARISON_DIMENSION)
            
            # Resize image 1
            ratio1 = target_w / float(gray1_pil_w)
            target_h1 = int(gray1_pil_h * ratio1)
            if gray1_pil_w != target_w or gray1_pil_h != target_h1 : # only resize if necessary
                 pil_img1 = pil_img1.resize((target_w, target_h1), Image.LANCZOS) # Pillow's resize

            # Resize image 2
            ratio2 = target_w / float(gray2_pil_w)
            target_h2 = int(gray2_pil_h * ratio2)
            if gray2_pil_w != target_w or gray2_pil_h != target_h2: # only resize if necessary
                pil_img2 = pil_img2.resize((target_w, target_h2), Image.LANCZOS)

            # If heights still differ slightly after proportional resize to same width, make them equal.
            # For example, resize the taller one to match the shorter one's height (maintaining new width)
            final_h = min(pil_img1.height, pil_img2.height)
            if pil_img1.height != final_h:
                pil_img1 = pil_img1.resize((target_w, final_h), Image.LANCZOS)
            if pil_img2.height != final_h:
                pil_img2 = pil_img2.resize((target_w, final_h), Image.LANCZOS)

            print(f"  Resized for comparison to: {pil_img1.width}x{pil_img1.height}")


        # Convert Pillow grayscale images to NumPy arrays for scikit-image
        gray1_np = np.array(pil_img1)
        gray2_np = np.array(pil_img2)

        # Ensure they are indeed the same shape before SSIM
        if gray1_np.shape != gray2_np.shape:
            # This shouldn't happen with the resize logic above, but as a fallback:
            print(f"  Error: Shapes still mismatch after resize attempt: {gray1_np.shape} vs {gray2_np.shape}. Skipping SSIM.")
            return None

        score, diff_img = ssim(gray1_np, gray2_np, full=True)
        # diff_img is also returned, could be saved for visualizing differences.
        return score

    except FileNotFoundError:
        print(f"Error: Image file not found. Cannot compare. Img1: {image_path1}, Img2: {image_path2}")
        return None
    except Exception as e:
        print(f"Error comparing images {os.path.basename(image_path1)} and {os.path.basename(image_path2)}: {e}")
        return None


def compare_pages(pages1_data, pages2_data, base_url1, base_url2):
    results = []
    # Sort for more predictable processing order, helps in debugging
    all_normalized_paths = sorted(list(set(pages1_data.keys()) | set(pages2_data.keys())))
    total_paths = len(all_normalized_paths)

    print(f"\nStarting comparison of {total_paths} unique page paths...")

    for i, norm_path in enumerate(all_normalized_paths):
        # More prominent progress indicator
        print(f"\n--- Comparing page {i+1}/{total_paths}: '{norm_path}' ---")

        data1 = pages1_data.get(norm_path)
        data2 = pages2_data.get(norm_path)

        result_entry = {
            "normalized_path": norm_path,
            "title1": data1['title'] if data1 and data1.get('title') else "N/A",
            "title2": data2['title'] if data2 and data2.get('title') else "N/A",
            "full_url1": data1['full_url'] if data1 and data1.get('full_url') else "#",
            "full_url2": data2['full_url'] if data2 and data2.get('full_url') else "#",
            "img1_full": None, "img1_thumb": None,
            "img2_full": None, "img2_thumb": None,
            "score": None
        }

        # --- Prepare image paths and create thumbnails ---
        # (Moved thumbnail creation before comparison, can also be done after)
        if data1 and data1.get('img_path'):
            if os.path.exists(data1['img_path']):
                # Make path relative to STATIC_FOLDER_FOR_FLASK for Flask's url_for
                result_entry["img1_full"] = os.path.relpath(data1['img_path'], STATIC_FOLDER_FOR_FLASK).replace(os.sep, '/')
                thumb_name1 = "thumb_" + os.path.basename(data1['img_path'])
                # Thumbnails are saved in the same directory as the full image
                full_thumb_path1 = os.path.join(os.path.dirname(data1['img_path']), thumb_name1)
                result_entry["img1_thumb"] = create_thumbnail(data1['img_path'], full_thumb_path1)
            else:
                print(f"  Image for site 1 ('{norm_path}') not found at: {data1['img_path']}")
        else:
            if data1: print(f"  Missing image path for site 1 page: '{norm_path}'")


        if data2 and data2.get('img_path'):
            if os.path.exists(data2['img_path']):
                result_entry["img2_full"] = os.path.relpath(data2['img_path'], STATIC_FOLDER_FOR_FLASK).replace(os.sep, '/')
                thumb_name2 = "thumb_" + os.path.basename(data2['img_path'])
                full_thumb_path2 = os.path.join(os.path.dirname(data2['img_path']), thumb_name2)
                result_entry["img2_thumb"] = create_thumbnail(data2['img_path'], full_thumb_path2)
            else:
                print(f"  Image for site 2 ('{norm_path}') not found at: {data2['img_path']}")
        else:
             if data2: print(f"  Missing image path for site 2 page: '{norm_path}'")

        # --- Compare images if both exist ---
        if data1 and data1.get('img_path') and data2 and data2.get('img_path') and \
           result_entry["img1_full"] and result_entry["img2_full"]: # Check if full paths were set (meaning files existed)
            
            print(f"  Comparing images for '{norm_path}'...")
            start_time = time.time()
            score = compare_images_ssim(data1['img_path'], data2['img_path'])
            end_time = time.time()
            print(f"  SSIM calculation for '{norm_path}' took {end_time - start_time:.2f} seconds.")
            
            result_entry["score"] = score
            if score is not None:
                print(f"  Comparison for '{norm_path}': SSIM = {score:.4f}")
            else:
                print(f"  Comparison failed or was skipped for '{norm_path}'.")
        elif data1 and data2 : # Both pages crawled but one or more images missing
             print(f"  Skipping comparison for '{norm_path}' due to missing image(s).")
        elif data1:
            print(f"  Page only in site 1: {norm_path} ({data1.get('full_url', 'N/A')})")
        elif data2:
            print(f"  Page only in site 2: {norm_path} ({data2.get('full_url', 'N/A')})")
        # else: This case (neither data1 nor data2) shouldn't happen if norm_path comes from their keys

        results.append(result_entry)

    results.sort(key=lambda x: (x['score'] is not None, x['score'] if x['score'] is not None else -1), reverse=True)
    print(f"\nComparison finished. Processed {total_paths} page paths.")
    return results
