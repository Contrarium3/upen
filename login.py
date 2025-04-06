import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import pickle
import os
import requests
from PIL import Image
import io
import time

from scrape import * 
from utils import *
from loggers import *


def is_logged_in(driver):
    """More comprehensive check combining multiple indicators"""
    try:
        driver.get('https://eprm.ypen.gr/src/App/w1/view/')
        
        login_page_elements = driver.find_elements(By.CLASS_NAME, "dropdown-toggle")
        
        return len(login_page_elements) >0 
    except:
        return False
    


def login(only_login=False):
    try:
        options = Options()
     
        # options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm -usage")
        service = Service()
        

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 30)
        
        driver.get("https://eprm.ypen.gr/src/App/user/login")
        
        if load_cookies(driver):
            if is_logged_in(driver):  # Use your is_logged_in function
                log_info("Restored session from cookies")
                if not only_login:
                    scrape(driver)
                return
            else: log_info('Not logged in')
            
        log_info("No valid session found - performing fresh login")


        # Find username & password fields and fill them
        username = driver.find_element(By.NAME, "username")  
        password = driver.find_element(By.NAME, "password")  

        username.send_keys("yannistr")
        password.send_keys("123581321tr")

        # # Ask user to input CAPTCHA in terminal
        captcha_text = input("Enter the CAPTCHA text (see captcha.png or popup): ")

        # # Fill CAPTCHA into the form
        captcha_input = driver.find_element(By.NAME, "captcha")
        captcha_input.send_keys(captcha_text)

        # Click stay logged in 

        stay_logged = driver.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
        driver.execute_script("arguments[0].click();", stay_logged)

        # Submit the form
        submit_button = driver.find_element(By.NAME, "submit")
        submit_button.click()
        try:
            # Wait for successful login indicator (adjust to your site)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//h1[contains(text(), 'Η περιβαλλοντική αδειοδότηση στον 21ο αιώνα')]"))
            )
            print("Login successful! Proceeding with scraping...")
       
            save_cookies(driver)
            if not only_login:
                scrape(driver)
                print('Successfully finished Scraping ')
            driver.quit()
       
        except TimeoutException:
            # Check if login failed
            error_message = driver.find_elements(By.CLASS_NAME, "error-message")
            if error_message:
                print(f"Login failed: {error_message[0].text}")
            else:
                print("Login status unknown - page didn't load as expected")
            
            # Optionally retry or exit
            driver.quit()
            exit()
        
    except Exception as e:
        print(f'Error in login: {e}')
        driver.quit()
        exit()
        


if __name__ == '__main__':
    os.makedirs('Scraped', exist_ok=True)
    login()
    