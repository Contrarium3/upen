from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import json
import urllib.request
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support import expected_conditions as EC
import os
import time
from tqdm import tqdm
from urllib.parse import unquote
import sys
import multiprocessing
from functools import partial
import random
import math

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from login import login
from utils import create_driver, save_cookies
from pdfs import get_all_links

# Define constants with absolute paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(SCRIPT_DIR, 'Files')
INPUT_DIR = os.path.join(SCRIPT_DIR, 'Scraped')
BASE_URL = "https://eprm.ypen.gr/src/App/"
GLOBAL_PROGRESS_FILE = os.path.join(SCRIPT_DIR, "global_progress.json")

# Make sure the FILES_DIR exists
os.makedirs(FILES_DIR, exist_ok=True)

def is_internet_available():
    """Check if internet connection is available"""
    try:
        urllib.request.urlopen('https://google.com', timeout=5)
        return True
    except:
        return False

def wait_for_internet():
    """Wait until internet connection is restored"""
    while not is_internet_available():
        print("Internet connection lost - waiting to reconnect...")
        time.sleep(10)  # Check every 10 seconds
    print("Internet connection restored!")

def wait_for_download_complete(download_dir, expected_name=None, timeout=30, poll_interval=1):
    """
    Wait for download to complete by monitoring for new files in the directory.
    This version doesn't rely on temporary files.
    
    Args:
        download_dir: Directory to monitor for new files
        expected_name: Optional name pattern to look for
        timeout: Maximum time to wait in seconds
        poll_interval: How often to check in seconds
        
    Returns:
        True if new files are detected, False otherwise
    """
    # Get initial directory listing
    initial_files = set(os.listdir(download_dir))
    
    start_time = time.time()
    max_time = start_time + timeout
    
    # Monitor for new files
    while time.time() < max_time:
        time.sleep(poll_interval)
        current_files = set(os.listdir(download_dir))
        new_files = current_files - initial_files
        
        if new_files:
            if expected_name:
                # Check if any of the new files match the expected name
                matching_files = [f for f in new_files if expected_name.lower() in f.lower()]
                if matching_files:
                    return True
                # If no matching file, but we have new files, consider it a success anyway
                return True
            else:
                # No specific name expected, just return True on any new file
                return True
                
    # If we've gone through the full timeout without finding new files
    return False

def load_global_progress():
    """Load the global progress data from the JSON file"""
    if os.path.exists(GLOBAL_PROGRESS_FILE):
        try:
            with open(GLOBAL_PROGRESS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            print("Warning: Failed to load global progress file. Starting fresh.")
    return set()

def update_global_progress(completed_files, progress_lock):
    """Update the global progress file with newly completed files"""
    with progress_lock:
        # Load current progress
        current_progress = load_global_progress()
        
        # Add new completed files
        updated_progress = current_progress.union(completed_files)
        
        # Save back to file
        with open(GLOBAL_PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(updated_progress), f)

def check_file_exists(category, filename):
    """Check if a file already exists in the category directory"""
    category_dir = os.path.join(FILES_DIR, category)
    if not os.path.exists(category_dir):
        return False
    
    # Try exact match first
    if os.path.exists(os.path.join(category_dir, filename)):
        return True
    
    # Try case-insensitive match (helpful for some systems)
    filename_lower = filename.lower()
    for existing_file in os.listdir(category_dir):
        if existing_file.lower() == filename_lower:
            return True
    
    return False

def download_pdf_chunk(chunk_id, links_chunk, progress_lock):
    """Download a chunk of PDFs with a dedicated driver"""
    # Configure a new driver instance for this process
    try:
        print(f"Worker {chunk_id} starting...")
        login(only_login=True)  
        driver = create_driver('https://eprm.ypen.gr/')
        save_cookies(driver)
    except Exception as e:
        print(f"Worker {chunk_id} failed to initialize: {str(e)}")
        return 0, 0
    
    # Configure Chrome download settings
    if "chrome" in driver.capabilities['browserName'].lower():
        driver.command_executor._commands["send_command"] = (
            "POST", '/session/$sessionId/chromium/send_command')
        params = {
            'cmd': 'Page.setDownloadBehavior',
            'params': {'behavior': 'allow', 'downloadPath': os.path.abspath(FILES_DIR)}
        }
        driver.execute("send_command", params)
    
    # Track progress for resuming - using the global progress file
    with progress_lock:
        completed_files = load_global_progress()
    
    print(f"Worker {chunk_id} found {len(completed_files)} already completed downloads")
                
    success_count = 0
    error_count = 0
    error_log = []
    newly_completed = set()

    for category, links in links_chunk.items():
        category_dir = os.path.join(FILES_DIR, category)
        with progress_lock:
            os.makedirs(category_dir, exist_ok=True)

        for url in links:
            file_id = f"{category}/{url}"
            
            # Check if this file is in the global progress
            if file_id in completed_files:
                continue

            # Extract expected filename from URL
            expected_name = unquote(url.split('/')[-1].split('?')[0])
            
            # Double check if file already physically exists
            with progress_lock:
                if check_file_exists(category, expected_name):
                    # File exists but wasn't in our progress file
                    completed_files.add(file_id)
                    newly_completed.add(file_id)
                    success_count += 1
                    print(f"Worker {chunk_id} - File already exists: {category}/{expected_name}")
                    continue

            while True:  # Retry loop for internet recovery
                try:
                    # Set download directory for this category
                    if "chrome" in driver.capabilities['browserName'].lower():
                        params['params']['downloadPath'] = os.path.abspath(category_dir)
                        driver.execute("send_command", params)

                    # Get a snapshot of files before download
                    with progress_lock:
                        initial_files = set(os.listdir(category_dir))
                    
                    # Start the download
                    full_url = BASE_URL + url
                    driver.get(full_url)
                    
                    # Wait for new files to appear (ignoring temporary files)
                    if wait_for_download_complete(category_dir, expected_name):
                        # Get the current files after download
                        with progress_lock:
                            current_files = set(os.listdir(category_dir))
                        new_files = current_files - initial_files
                        
                        if new_files:
                            # Use the first new file detected
                            downloaded_file = list(new_files)[0]
                            success_count += 1
                            
                            # Add to local tracking sets
                            completed_files.add(file_id)
                            newly_completed.add(file_id)
                            
                            # Update global progress periodically (every 5 downloads)
                            if len(newly_completed) >= 5:
                                update_global_progress(newly_completed, progress_lock)
                                newly_completed = set()
                                
                            print(f"Worker {chunk_id} - Downloaded: {category}/{downloaded_file}")
                            break  # Exit retry loop on success
                        else:
                            error_log.append(f"No new files found for: {category}/{expected_name}")
                            error_count += 1
                            break
                    else:
                        error_log.append(f"Timeout: {category}/{expected_name}")
                        error_count += 1
                        break

                except WebDriverException as e:
                    wait_for_internet()  
                    login(only_login=True)  # Re-login if needed
                    driver = create_driver('https://eprm.ypen.gr/')
                    save_cookies(driver)
                    
                    if "net::ERR_INTERNET_DISCONNECTED" in str(e):
                        print(f"Worker {chunk_id} - Connection lost during download - will retry...")
                        time.sleep(5)
                        continue
                    error_log.append(f"Error: {category}/{url} - {str(e)}")
                    error_count += 1
                    break
                except Exception as e:
                    error_log.append(f"Error: {category}/{url} - {str(e)}")
                    error_count += 1
                    break

                # Add some random delay between downloads to avoid overwhelming the server
                # time.sleep(random.uniform(0.5, 2.0))

    # Update global progress with any remaining newly completed files
    if newly_completed:
        update_global_progress(newly_completed, progress_lock)

    # Write any errors to a log file
    if error_log:
        with open(os.path.join(SCRIPT_DIR, f"download_errors_{chunk_id}.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(error_log))
        print(f"Worker {chunk_id} - Errors logged: {len(error_log)}")

    # Clean up
    try:
        driver.quit()
    except:
        pass

    print(f"Worker {chunk_id} - Complete! Success: {success_count}, Errors: {error_count}")
    return success_count, error_count

def split_links_for_parallel(all_links, num_workers):
    """Split links dictionary into roughly equal chunks for parallel processing"""
    # Flatten the dictionary into a list of (category, url) tuples
    flat_links = []
    for category, urls in all_links.items():
        for url in urls:
            flat_links.append((category, url))
    
    # Shuffle the links to distribute load more evenly
    random.shuffle(flat_links)
    
    # Split into chunks
    chunk_size = math.ceil(len(flat_links) / num_workers)
    chunks = [flat_links[i:i + chunk_size] for i in range(0, len(flat_links), chunk_size)]
    
    # Convert chunks back to dictionary format
    chunked_dicts = []
    for chunk in chunks:
        chunk_dict = {}
        for category, url in chunk:
            if category not in chunk_dict:
                chunk_dict[category] = []
            chunk_dict[category].append(url)
        chunked_dicts.append(chunk_dict)
    
    return chunked_dicts

def main(num_workers=1):
    print(f"Script directory: {SCRIPT_DIR}")
    print(f"Files directory: {FILES_DIR}")
    print(f"Starting download with {num_workers} parallel workers")
    
    # Get all links first
    all_links, _ = get_all_links()
    total_links = sum(len(links) for links in all_links.values())
    
    print(f"Found {total_links} files to download across {len(all_links)} categories.")
    
    # Check existing files and update global progress
    initial_progress = load_global_progress()
    print(f"Found {len(initial_progress)} entries in global progress file")
    
    if total_links > 1000:
        confirm = input(f"WARNING: You're about to download {total_links} files. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Download cancelled.")
            return
    
    # Filter out links that are already in the global progress
    filtered_links = {}
    for category, urls in all_links.items():
        filtered_links[category] = []
        for url in urls:
            file_id = f"{category}/{url}"
            if file_id not in initial_progress:
                filtered_links[category].append(url)
    
    remaining_links = sum(len(links) for links in filtered_links.values())
    print(f"After filtering already downloaded files: {remaining_links} files remaining to download")
    
    if remaining_links == 0:
        print("All files have already been downloaded. Nothing to do!")
        return
    
    # Split links into chunks for parallel processing
    link_chunks = split_links_for_parallel(filtered_links, num_workers)
    
    # Create a manager for sharing the lock between processes
    with multiprocessing.Manager() as manager:
        # Create a lock for directory operations and progress file updates
        progress_lock = manager.Lock()
        
        # Create and start worker processes
        with multiprocessing.Pool(processes=num_workers) as pool:
            download_func = partial(download_pdf_chunk, progress_lock=progress_lock)
            results = pool.starmap(download_func, enumerate(link_chunks))
    
    # Process results
    total_success = sum(r[0] for r in results)
    total_errors = sum(r[1] for r in results)
    
    print(f"\nAll workers completed!")
    print(f"Total success: {total_success}/{remaining_links} ({(total_success/remaining_links)*100:.1f}%)")
    print(f"Total errors: {total_errors}")
    
    # Combine error logs
    combined_errors = []
    for i in range(num_workers):
        error_log_path = os.path.join(SCRIPT_DIR, f"download_errors_{i}.log")
        if os.path.exists(error_log_path):
            with open(error_log_path, "r", encoding="utf-8") as f:
                combined_errors.extend(f.readlines())
    
    if combined_errors:
        with open(os.path.join(SCRIPT_DIR, "download_errors_combined.log"), "w", encoding="utf-8") as f:
            f.writelines(combined_errors)
        print(f"Combined error log created with {len(combined_errors)} entries.")

if __name__ == "__main__":
    # Allow setting number of workers from command line
    num_workers = 10 # Default
    if len(sys.argv) > 1:
        try:
            num_workers = int(sys.argv[1])
        except ValueError:
            print(f"Invalid number of workers: {sys.argv[1]}. Using default: 10")
    
    main(num_workers)