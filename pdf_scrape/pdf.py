from aiohttp import ClientSession, CookieJar
import pickle
import asyncio
from ..login import login

# Load cookies function (no change here)
def load_cookies(filename="cookies.pkl"):
    """Load cookies from a pickle file and return them as a list of dicts"""
    try:
        with open(filename, 'rb') as cookie_file:
            cookies = pickle.load(cookie_file)
            print(f"Loaded cookies: {cookies}")  # Debugging: Inspect the loaded cookies

            return cookies
            
    except FileNotFoundError:
        print(f"{filename} not found!")
        return None
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return None

# Create authenticated session with selenium cookies
async def create_authenticated_session_with_selenium():
    login(only_login=True)
    
    # Get the cookies from Selenium after login
    selenium_cookies = load_cookies()
    
    # Debugging: print the actual structure of selenium_cookies
    print("Loaded cookies structure:", type(selenium_cookies))
    print(selenium_cookies)
    
    # Create a cookie jar
    cookie_jar = CookieJar(unsafe=True)
    
    # Add cookies to the jar using the update_cookies() method
    for cookie in selenium_cookies:
        print("Processing cookie:", cookie)
        
        # aiohttp expects cookies in this format: {name: value}
        cookie_dict = {
            cookie['name']: cookie['value']
        }
        
        # Add cookies to the cookie jar
        cookie_jar.update_cookies(cookie_dict)
    
    # Add common headers (User-Agent, etc.)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
        'Referer': 'https://eprm.ypen.gr/scr/App',  # If the login page has a specific referer URL
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    # Create the aiohttp session with the cookies and headers
    session = ClientSession(cookie_jar=cookie_jar, headers=headers)
    return session

# Main function
async def main():
    session = await create_authenticated_session_with_selenium()
    
    # After creating the session, you can now use aiohttp to make authenticated requests
    async with session.get("https://eprm.ypen.gr/src/App") as response:
        print(f"Status Code: {response.status}")
        print(f"Response Headers: {response.headers}")
        
        if response.status == 200:
            content = await response.text()
            print(content)  # Do something with the content
        else:
            print(f"Failed to fetch page, status: {response.status}")
    
    await session.close()
  
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDownload interrupted by user.")
