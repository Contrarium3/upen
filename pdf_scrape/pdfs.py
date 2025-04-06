import os
import json
import asyncio
import aiohttp
import aiofiles
import random
import time
from tqdm.asyncio import tqdm_asyncio
from urllib.parse import unquote
import pickle
from aiohttp.typedefs import URL

from yarl import URL  # yarl is already a dependency of aiohttp
from http.cookies import SimpleCookie

from aiohttp import ClientSession, CookieJar

from login import login


async def create_authenticated_session_with_selenium(driver):
    """
    Uses Selenium to log in and solve CAPTCHA, then creates an aiohttp session 
    with the authenticated cookies.
    """
    login(only_login=True)
    
    # Get the cookies from Selenium after login
    selenium_cookies = driver.get_cookies()

    # Create a cookie jar and add cookies to it
    cookie_jar = CookieJar(unsafe=True)
    for cookie in selenium_cookies:
        # Convert the Selenium cookies to aiohttp's CookieJar format
        cookie_jar.update_cookies({
            cookie['name']: cookie['value']
        })

    # Create the aiohttp session with the cookies
    session = ClientSession(cookie_jar=cookie_jar)
    return session

def get_cookies_for_aiohttp(driver):
    """Convert Selenium cookies to aiohttp format with proper domain handling"""
    # Ensure we're on the right domain to get correct cookies
    driver.get("https://eprm.ypen.gr/")
    
    selenium_cookies = driver.get_cookies()
    cookie_jar = aiohttp.CookieJar(unsafe=True)  # unsafe allows all domains
    
    for cookie in selenium_cookies:
        # Skip cookies that don't belong to our domain
        if 'eprm.ypen.gr' not in cookie.get('domain', ''):
            continue
            
        # Create a cookie object
        cookie_obj = aiohttp.cookiejar.Morsel()
        cookie_obj.set(cookie['name'], cookie['value'], cookie.get('value', ''))
        
        # Set additional cookie attributes
        if 'domain' in cookie:
            cookie_obj['domain'] = cookie['domain']
        if 'path' in cookie:
            cookie_obj['path'] = cookie['path']
        if 'secure' in cookie:
            cookie_obj['secure'] = cookie['secure']
        if 'expiry' in cookie:
            cookie_obj['expires'] = str(cookie['expiry'])
        
        # Add the cookie to the jar
        cookie_jar.update_cookies({cookie['name']: cookie_obj})
    
    # # For debugging
    # print("Cookies being transferred:")
    # for cookie in cookie_jar:
    #     print(f"{cookie.key}={cookie.value} (domain: {cookie['domain']})")
    
    return cookie_jar

async def verify_session(session):
    """Check if session is actually authenticated"""
    test_url = "https://eprm.ypen.gr/"  # Change to a real protected URL
    async with session.get(test_url) as resp:
        content = await resp.text()
        if "login" in content.lower():
            print("Session verification failed - got login page")
            print(f"Status: {resp.status}")
            print(f"Response headers: {resp.headers}")
            print(f"Content preview: {content[:200]}")
            return False
        return True

def load_cookies(filename="cookies.pkl"):
    """Load cookies from a pickle file and return them as a dictionary"""
    try:
        with open(filename, 'rb') as cookie_file:
            cookies = pickle.load(cookie_file)
            cookie_dict = {}
            for cookie in cookies:
                cookie_dict[cookie['name']] = cookie['value']
            return cookie_dict
    except FileNotFoundError:
        print(f"{filename} not found!")
        return None
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return None
    

FILES_DIR = 'Files'
INPUT_DIR = 'Scraped'
BASE_URL = "https://eprm.ypen.gr/src/App/"

# Configuration settings
MAX_CONCURRENT_REQUESTS = 5  # Reduced from original
MAX_RETRIES = 3              # Add retry logic
MIN_DELAY = 0.5              # Minimum delay between requests in seconds
MAX_DELAY = 2.0              # Maximum delay between requests in seconds
REQUEST_TIMEOUT = 60         # Timeout for requests in seconds

os.makedirs(FILES_DIR, exist_ok=True)

def extract_links(obj, parent_key=None):
    links_dict = {}
    count = 0

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "links" and isinstance(value, list):
                if parent_key:  # Add links under the top-level parent
                    links_dict.setdefault(parent_key, []).extend(value)
                count += 1
            else:
                # Pass the current key as parent_key only if it's not "links"
                sub_links, sub_count = extract_links(value, parent_key or key)
                for k, v in sub_links.items():
                    links_dict.setdefault(k, []).extend(v)
                count += sub_count

    elif isinstance(obj, list):
        for item in obj:
            sub_links, sub_count = extract_links(item, parent_key)
            for k, v in sub_links.items():
                links_dict.setdefault(k, []).extend(v)
            count += sub_count

    return links_dict, count

def get_all_links():
    all_links = {}
    file_link_counts = {}

    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".json") and filename != "tabs.json":
            filepath = os.path.join(INPUT_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    links_dict, count = extract_links(data)
                    for k, v in links_dict.items():
                        all_links.setdefault(k, []).extend(v)
                    file_link_counts[filename] = count
                except Exception as e:
                    print(f"Error reading {filename}: {e}")

    for fname, count in file_link_counts.items():
        print(f"{fname}: {count} 'links' keys found.")

    return all_links, file_link_counts


def get_filename_from_response(response):
    # Try to get filename from Content-Disposition header first
    if 'Content-Disposition' in response.headers:
        import re
        disposition = response.headers['Content-Disposition']
        matches = re.findall(r'filename=(?:\"|\')(.+?)(?:\"|\');?', disposition)
        if matches:
            return unquote(matches[0])
    
    # Fall back to URL if Content-Disposition doesn't provide filename
    url_path = unquote(str(response.url.path))
    filename = os.path.basename(url_path)
    
    # If no extension in filename, try to determine from content-type
    if '.' not in filename and 'Content-Type' in response.headers:
        content_type = response.headers['Content-Type'].split(';')[0].strip()
        ext_map = {
            'application/pdf': '.pdf',
            'application/msword': '.doc',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
            'application/vnd.ms-excel': '.xls',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
            'application/vnd.ms-powerpoint': '.ppt',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
            'text/plain': '.txt',
            'text/html': '.html',
            'text/csv': '.csv',
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif'
        }
        if content_type in ext_map:
            filename += ext_map[content_type]
    
    # If we still have no filename, use a default with timestamp
    if not filename or filename == '':
        print(f"ERROR No filename found in response. Using url: {response.url.path.split('/')[-1]}")
        filename = str(response.url).split("/")[-1]
        
    return filename


async def download_file(session, url, dest_folder, category, pbar, semaphore):
    retries = 0
    while retries <= MAX_RETRIES:
        try:
            # Wait for semaphore to control concurrency
            async with semaphore:
                # Add random delay to avoid rate limiting
                await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                
                # Create category subfolder
                category_folder = os.path.join(dest_folder, category)
                os.makedirs(category_folder, exist_ok=True)
                
                # Get default filename from URL first (as fallback)
                default_name = url.split("/")[-1].split("?")[0]
                
                full_url = BASE_URL + url
                
                # Add detailed error capture
                try:
                    async with session.get(full_url, timeout=REQUEST_TIMEOUT) as resp:
                        print(full_url)
                        if resp.status == 200:
                            # Get the filename from the response
                            filename = get_filename_from_response(resp)
                            
                            # Use default name if we couldn't get a filename
                            if not filename or filename == '':
                                filename = default_name
                            
                            # Sanitize filename to remove invalid characters
                            filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
                            
                            path = os.path.join(category_folder, filename)
                            
                            # Skip if already downloaded
                            if os.path.exists(path):
                                pbar.update(1)
                                return True, f"Skipped (already exists): {category}/{filename}"
                            
                            # Read response content
                            content = await resp.read()
                            
                            # Check if content is valid (not empty or error page)
                            if len(content) < 100:  # Arbitrary check for very small files that might be error pages
                                content_str = content.decode('utf-8', errors='ignore')
                                if "error" in content_str.lower() or "not found" in content_str.lower():
                                    raise Exception(f"Received error page: {content_str[:100]}...")
                            
                            # Save file
                            async with aiofiles.open(path, mode='wb') as f:
                                await f.write(content)
                            
                            pbar.update(1)
                            print(f"Downloaded: {category}/{filename}")
                            return True, f"Downloaded: {category}/{filename}"
                        elif resp.status == 429:  # Too Many Requests
                            if retries < MAX_RETRIES:
                                # Exponential backoff for rate limiting
                                wait_time = (2 ** retries) + random.uniform(0, 1)
                                print(f"Rate limited. Waiting {wait_time:.2f}s before retry {retries+1}/{MAX_RETRIES} for {url}")
                                await asyncio.sleep(wait_time)
                                retries += 1
                                continue
                            else:
                                pbar.update(1)
                                return False, f"Failed after {MAX_RETRIES} retries due to rate limiting: {url}"
                        elif resp.status == 403:  # Forbidden
                            pbar.update(1)
                            return False, f"Access denied (403): {url} - May need authentication or session refresh"
                        else:
                            # For other status codes, try to get response body for more info
                            try:
                                error_content = await resp.text()
                                error_preview = error_content[:100] if error_content else "No content"
                            except:
                                error_preview = "Could not read error content"
                                
                            if retries < MAX_RETRIES:
                                print(f"HTTP {resp.status} for {url}. Retrying {retries+1}/{MAX_RETRIES}...")
                                retries += 1
                                continue
                            else:
                                pbar.update(1)
                                return False, f"Failed {url} | Status: {resp.status} | {error_preview}"
                except asyncio.TimeoutError:
                    if retries < MAX_RETRIES:
                        print(f"Timeout for {url}. Retrying {retries+1}/{MAX_RETRIES}...")
                        retries += 1
                        continue
                    else:
                        pbar.update(1)
                        return False, f"Timeout after {MAX_RETRIES} retries: {url}"
                        
        except aiohttp.ClientError as e:
            if retries < MAX_RETRIES:
                print(f"Client error: {str(e)} for {url}. Retrying {retries+1}/{MAX_RETRIES}...")
                retries += 1
                continue
            else:
                pbar.update(1)
                return False, f"Client error after {MAX_RETRIES} retries: {url} - {str(e)}"
        except Exception as e:
            if retries < MAX_RETRIES:
                print(f"Error: {str(e)} for {url}. Retrying {retries+1}/{MAX_RETRIES}...")
                retries += 1
                continue
            else:
                pbar.update(1)
                return False, f"Error after {MAX_RETRIES} retries: {url} - {str(e)}"


from utils import *


async def main():
    driver = create_driver('https://eprm.ypen.gr/')
    save_cookies(driver)

    if not driver:
        raise Exception("Failed to create driver or load cookies")
    
    # Get cookies in aiohttp format
    jar = get_cookies_for_aiohttp(driver)
    driver.quit()


    all_links, _ = get_all_links()
    
    # Count total links across all categories
    total_links = sum(len(links) for links in all_links.values())
    
    print(f"Found {total_links} files to download across {len(all_links)} categories.")
    
    # Save a list of all URLs to download for resume capability
    with open("all_downloads.json", "w", encoding="utf-8") as f:
        json.dump(all_links, f, indent=2)
        
    # Ask for confirmation before proceeding with many downloads
    if total_links > 1000:
        confirm = input(f"WARNING: You're about to download {total_links} files. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Download cancelled.")
            return
    
    # Configure connection settings for better performance
    conn = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS, ssl=False)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    
    # Create a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    # Create progress bar
    pbar = tqdm_asyncio(total=total_links, desc="Downloading files")
    
    results = {"success": 0, "failed": 0, "errors": []}
    
    # Create error log file
    error_log_path = "download_errors.log"
  

    async with aiohttp.ClientSession(
            cookie_jar=jar,
            connector=conn, 
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': BASE_URL,
                'Connection': 'keep-alive',
                # Add more headers if needed
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Upgrade-Insecure-Requests': '1'
            }
        ) as session:
        # Create tasks for each category and URL
        tasks = []
        for category, links in all_links.items():
            # Start with a small subset for testing
            links_set = set(links)  # Remove duplicates
            for url in links_set:
                if url and url.strip():  # Ensure URL is not empty
                    tasks.append(download_file(session, url, FILES_DIR, category, pbar, semaphore))
        
        # Process tasks as they complete
        for future in asyncio.as_completed(tasks):
            success, message = await future
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(message)
                
                # Write error to log file immediately
                async with aiofiles.open(error_log_path, "a", encoding="utf-8") as error_log:
                    await error_log.write(f"{message}\n")
            
            # Show periodic progress
            if (results["success"] + results["failed"]) % 100 == 0:
                success_rate = results["success"] / (results["success"] + results["failed"]) * 100
                print(f"\nProgress: {results['success']} success, {results['failed']} failed ({success_rate:.1f}% success rate)")
    
    # Show final stats
    print(f"\nDownload complete. Success: {results['success']}, Failed: {results['failed']}")
    print(f"Success rate: {(results['success'] / (results['success'] + results['failed']) * 100):.1f}%")
    
    if results["errors"]:
        print(f"First 5 errors (full log in {error_log_path}):")
        for error in results["errors"][:5]:
            print(f"  - {error}")
        if len(results["errors"]) > 5:
            print(f"  ... and {len(results['errors']) - 5} more errors")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDownload interrupted by user. Progress has been saved to error log.")