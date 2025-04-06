import pickle
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from loggers import * 


COOKIE_FILE = "cookies.pkl"

def is_logged_in(driver):
    """More comprehensive check combining multiple indicators"""
    try:
        driver.get('https://eprm.ypen.gr/src/App/w1/view/')
        
        login_page_elements = driver.find_elements(By.CLASS_NAME, "dropdown-toggle")
        
        return len(login_page_elements) >0 
    except:
        return False
    

def create_driver(project_url):
    try:
        """Create and return a new Selenium driver instance."""
        # Add your driver initialization logic here
        options = webdriver.ChromeOptions()
        # options.add_argument('--headless')  
        # options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm -usage')
        service = Service()
            

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    
        if load_cookies(driver, project_url):
            log_info("Probably Restored session from cookies")
                
        else: 
            log_info('error in loading cookies')
            return False
            
        return driver

    except Exception as e:
        log_error(f'Fail in create driver for parallel projects')
    



def save_cookies(driver):
    """Save cookies to a file"""
    # First get to the domain where cookies are valid
    driver.get("https://eprm.ypen.gr/")  
    with open(COOKIE_FILE, "wb") as file:
        pickle.dump(driver.get_cookies(), file)
    log_info("Cookies saved successfully")

def load_cookies(driver, project_url = None):
    """Load cookies from file and add them to the driver"""
    if not os.path.exists(COOKIE_FILE):
        return False
        
    try:
        if not project_url:
        # First navigate to the domain before adding cookies
            driver.get("https://eprm.ypen.gr/src/App/w1/view/")
        else:
            driver.get(project_url)
        
        with open(COOKIE_FILE, "rb") as file:
            cookies = pickle.load(file)
            
            # Clear existing cookies first
            driver.delete_all_cookies()
            
            for cookie in cookies:
                # Fix domain if needed (some sites require specific domain format)
                if 'eprm.ypen.gr' not in cookie['domain']:
                    cookie['domain'] = 'eprm.ypen.gr'
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    log_error(f"Couldn't add cookie: {e}")
                    continue
                    
        log_info("Cookies loaded successfully")
        return True
    
    except Exception as e:
        log_error(f"Error loading cookies: {e}")
        return False
