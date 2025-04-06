from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import json
import urllib.request
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support import expected_conditions as EC
import os
import time
from tqdm.asyncio import tqdm_asyncio
from urllib.parse import unquote
from aiohttp.typedefs import URL
from http.cookies import SimpleCookie
from aiohttp import ClientSession, CookieJar
from tqdm import tqdm

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from login import login
from utils import create_driver, save_cookies

from pdfs import get_all_links


FILES_DIR = 'Files'
INPUT_DIR = 'Scraped'
BASE_URL = "https://eprm.ypen.gr/src/App/"



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

def download_pdfs_with_selenium(driver, all_links):
    # Configure Chrome
    if "chrome" in driver.capabilities['browserName'].lower():
        driver.command_executor._commands["send_command"] = (
            "POST", '/session/$sessionId/chromium/send_command')
        params = {
            'cmd': 'Page.setDownloadBehavior',
            'params': {'behavior': 'allow', 'downloadPath': os.path.abspath(FILES_DIR)}
        }
        driver.execute("send_command", params)

    # Track progress for resuming
    completed_files = set()
    if os.path.exists("progress.tmp"):
        with open("progress.tmp", "r") as f:
            completed_files = set(f.read().splitlines())

    total_files = sum(len(set(links)) for links in all_links.values())
    success_count = 0
    error_log = []

    with tqdm(
        total=total_files,
        desc="Downloading PDFs",
        unit="file",
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{percentage:.0f}%]"
    ) as pbar:
        pbar.update(len(completed_files))  # Skip already downloaded files

        for category, links in all_links.items():
            category_dir = os.path.join(FILES_DIR, category)
            os.makedirs(category_dir, exist_ok=True)

            for url in links:
                file_id = f"{category}/{url}"
                if file_id in completed_files:
                    continue

                while True:  # Retry loop for internet recovery
                    try:

                        # Set download directory for this category
                        if "chrome" in driver.capabilities['browserName'].lower():
                            params['params']['downloadPath'] = os.path.abspath(category_dir)
                            driver.execute("send_command", params)

                        full_url = BASE_URL + url
                        driver.get(full_url)

                        expected_name = urllib.parse.unquote(url.split('/')[-1].split('?')[0])
                        
                        if wait_for_download_complete(category_dir):
                            downloaded_files = [
                                f for f in os.listdir(category_dir)
                                if os.path.isfile(os.path.join(category_dir, f))
                                and expected_name.lower() in f.lower()
                            ]

                            if downloaded_files:
                                success_count += 1
                                completed_files.add(file_id)
                                with open("progress.tmp", "a") as f:
                                    f.write(f"{file_id}\n")
                                pbar.set_postfix_str(f"Last: {category}/{expected_name}")
                                break  # Exit retry loop on success
                            else:
                                error_log.append(f"File missing: {category}/{expected_name}")
                                break
                        else:
                            error_log.append(f"Timeout: {category}/{expected_name}")
                            break

                    except WebDriverException as e:
                        wait_for_internet()  
                        login(only_login=True)  # Re-login if needed
                        driver = create_driver('https://eprm.ypen.gr/')
                        save_cookies(driver)
                        
                        if "net::ERR_INTERNET_DISCONNECTED" in str(e):
                            print("Connection lost during download - will retry...")
                            time.sleep(5)
                            continue
                        error_log.append(f"Error: {category}/{url} - {str(e)}")
                        break
                    except Exception as e:
                        error_log.append(f"Error: {category}/{url} - {str(e)}")
                        break

                pbar.update(1)

    # Cleanup
    # if os.path.exists("progress.tmp"):
    #     os.remove("progress.tmp")

    success_rate = (success_count / total_files) * 100
    print(f"\nDownload complete! Success: {success_count}/{total_files} ({success_rate:.1f}%)")
    
    if error_log:
        with open("download_errors.log", "w", encoding="utf-8") as f:
            f.write("\n".join(error_log))
        print(f"Errors logged: {len(error_log)}")

    return success_count

def wait_for_download_complete(download_dir, timeout=60, poll_interval=1):
    """Wait until no .crdownload or .part files exist"""
    start_time = time.time()
    while (time.time() - start_time) < timeout:
        time.sleep(poll_interval)
        if not any(
            f.endswith(('.crdownload', '.part')) 
            for f in os.listdir(download_dir)
        ):
            return True
    return False

def unquote(url):
    """Decode URL-encoded strings"""
    from urllib.parse import unquote
    return unquote(url)




def main():
    login(only_login=True)
    
    driver = create_driver('https://eprm.ypen.gr/')
    save_cookies(driver)

    if not driver:
        raise Exception("Failed to create driver or load cookies")
    
    all_links, _ = get_all_links()
    total_links = sum(len(links) for links in all_links.values())
    
    print(f"Found {total_links} files to download across {len(all_links)} categories.")
    
    if total_links > 1000:
        confirm = input(f"WARNING: You're about to download {total_links} files. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Download cancelled.")
            return
    
    # Use Selenium to download files
    error_count = download_pdfs_with_selenium(driver, all_links)
    
    print(f"\nDownload complete with {error_count} errors.")
    driver.quit()
    


if __name__ == "__main__":
    main()