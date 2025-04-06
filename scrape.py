import requests
from all_tabs import known_tabs
from id import * 
from loggers import * 
from bs4 import BeautifulSoup
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import re
import time


def is_public_view(tab):
    return "_public" in tab

BASE_URL  = 'https://eprm.ypen.gr/src/App/'

def scrape(driver):
    try:
        driver.get(BASE_URL)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.nav")))

        navs = driver.find_elements(By.CSS_SELECTOR, "ul.nav")

        # Skip the first nav
        target_navs = navs[1:]  

        # Collect all <a> links inside those navs
        nav_links = []
        for nav in target_navs:
            nav_links.extend(nav.find_elements(By.CSS_SELECTOR, "li a"))

        tabs = {}
        for link in nav_links:
            href = link.get_attribute("href")
            # Skip empty or None values
            if not href:
                continue
                
            # Skip fragment-only links
            if href == '#' or href.endswith('/#'):
                continue
            
            # Skip the base URL itself
            base_no_slash = BASE_URL.rstrip('/')
            if href == BASE_URL or href == base_no_slash:
                continue
            
            # Extract path
            if href.startswith(BASE_URL):
                path = href.replace(BASE_URL, '').rstrip('/')
            else:
                # For relative URLs
                path = href.lstrip('/').rstrip('/')
            
            # Skip empty paths
            if not path:
                continue
            tabs[path] = link.text.strip()
            

        with open('Scraped/tabs.json', 'w') as f:
            json.dump(tabs, f, indent=4, ensure_ascii=False)
        print(f"Found {len(tabs)} tabs")
            
                
        if set(tabs.keys()) != set(known_tabs):
            log_error(f"Tabs do not match known tabs: {set(tabs.keys())}")
        else: 
            print('Tabs match known tabs')

        
        for tab in tabs.keys():
            # if 'w12' not in tab or 'public' in tab: continue
            # if '_public' not in tab : continue
            
            print(f'Scraping tab: {tab}')
            # if not is_public_view(tab): continue
            scrape_tab(driver , tab)
            print('\n\n\n')
            # break # REMOVE
            
    except Exception as e:
         log_error(f"Error on scrape {e}")


def scrape_tab(driver, tab):
    try:
        driver.get(f"{BASE_URL}/{tab}")
        
        # Set dropdown to 100 items per page
        dropdown = Select(WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "datatable-dummy_length"))
        ))
        
        dropdown.select_by_value("100")
        
        WebDriverWait(driver, 10).until(
                lambda d: ("100" in d.find_element(By.ID, "datatable-dummy_length").text)
            )
        time.sleep(1)
        
        log_info(f"Selected: {dropdown.first_selected_option.get_attribute('value')}")

        try:
        # Wait for initial table load
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tbody tr a"))
            )
        except Exception as e:
            log_info('No records in this tab: Continue...')
            return []
            


        title = driver.find_element(By.TAG_NAME, "h1").text
        log_info(f'Scraping tab {tab} {title}...')
        
        all_projects = []
        current_page = 1
        global panel_set
        while True:
            # Get fresh HTML after potential page reload
            page_html = driver.page_source
            soup = BeautifulSoup(page_html, 'html.parser')

            # Extract page info (e.g., "Εμφανίζονται 1 Έως 100 Από 313")
            page_info = driver.find_element(By.CSS_SELECTOR, "#datatable-dummy_info").text
            match = re.search(r"([\d,]+) Έως ([\d,]+) Από ([\d,]+)", page_info)
            if match:
                start, end, total =  int(match.group(1).replace(",", "")), int(match.group(2).replace(",", "")) , int(match.group(3).replace(",", ""))
                current_page = (start // 100) + 1
                log_info(f"Page {current_page}: Records {start}-{end} (Total: {total})")

            if total == 0:
                log_info('No records in this tab: Continue...')
                return []
    
            # Scrape current page
            is_public  = is_public_view(tab)
            projects = scrape_page(driver, soup, is_public = is_public)
            all_projects.extend(projects)

            # Exit if last page (fewer than 100 projects)
            if len(projects) < 100:
                break

            # Click "Next" and wait for table to reload
            try:
                next_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#datatable-dummy_next"))
                )
                if "disabled" in next_button.get_attribute("class"):
                    break  # No more pages
                
                next_button.click()
                # Wait for table to refresh (old rows become stale)
                WebDriverWait(driver, 10).until(
                    EC.staleness_of(driver.find_element(By.CSS_SELECTOR, "tbody tr")))
            except Exception as e:
                log_error(f"Failed to go to next page: {e}")
                break

        if total!= len(all_projects):
            log_error(f"Missmatch in length of total {total} vs scraped {len(all_projects)} in this tab: {tab} , {title}")
            
        else:
            log_info(f"Correctly identified total projects : {len(all_projects)}")
            
        scraped = {}
        c = -1
        for project in all_projects:
            c += 1
            if c % 100 == 0:
                log_info(f"Perccent completed for this tab {tab}: {c / len(all_projects) * 100:.2f}%")
            
            pet = project['pet']
            
            try:
                scraped.update( scrape_project(pet , driver, f"https://eprm.ypen.gr{project['url']}", tab))
                
            except Exception as e:
                log_error(f"Failed to scrape project from https://eprm.ypen.gr{project['url']}: {str(e)}")
                
        # Write to a JSON file
        with open(f"Scraped/{tab.replace('/' , '_')}.json", "w") as file:
            json.dump(scraped, file, indent=4, ensure_ascii=False)  # indent for pretty formatting

        print(f"Dictionary written to Scraped/{tab.replace('/' , '_')}.json")
        log_info(f"Dictionary written to Scraped/{tab.replace('/' , '_')}.json")
        return all_projects

    except Exception as e:
        log_error(f'Error on scrape tab {tab}: {e}')
        return []
            
        



def scrape_page(driver, soup, is_public=False):
    try:
        projects = []
        
        if is_public:
            # Handle public view structure
            for row in soup.select('tbody tr'):
                try:
                    cells = row.find_all('td')
                    if len(cells) >= 3:  # Public view has 3 columns
                        link = cells[0].find('a')
                        if link:
                            projects.append({
                                'project_name': link.get_text(strip=True),
                                'url': link['href'],
                                'pet': cells[1].get_text(strip=True),
                                'status': cells[2].get_text(strip=True),
                                # Other fields will be empty for public views
                                'protocol': '',
                                'date': ''
                            })
                except Exception as e:
                    log_error(f"Error processing public view row: {e}")
                    continue
        else:
            # Handle regular view structure
            for row in soup.select('tbody tr'):
                try:
                    cells = row.find_all('td')
                    if len(cells) >= 5:  # Regular view has 5 columns
                        link = cells[0].find('a')
                        if link:
                            projects.append({
                                'project_name': link.get_text(strip=True),
                                'url': link['href'],
                                'pet': cells[1].get_text(strip=True),
                                'protocol': cells[2].get_text(strip=True),
                                'date': cells[3].get_text(strip=True),
                                'status': cells[4].get_text(strip=True)
                            })
                except Exception as e:
                    log_error(f"Error processing regular row: {e}")
                    continue
                    
        log_info(f"Found {len(projects)} projects in this page.")
        return projects
    
    except Exception as e:
        log_error(f'Failed in scrape page: {e}')
        return []





def scrape_project(pet, driver, project_url, tab):
    driver.get(project_url)
    log_info(f"Loading project page: {project_url}")
    match = re.search(r"(w\d+_.+)", project_url.replace("/" , "_"))
    if match:
        extracted_value = match.group(1)  # This gets the part starting with w{number} and everything after
        key = f"{pet}_{extracted_value}"
    else :
        key = f"{pet}_{project_url}"
    
    
    try:
        # Wait for panels to load and get page source
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".panel-group"))
        )
        
        # Parse with BeautifulSoup
        project_soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Find all panels
        panels = project_soup.select('div.panel-default')
        # log_info(f"Found {len(panels)} panels")
        
        results = {}
        for panel in panels:
            panel_id = panel.get('id', 'no_id') 
            panel_data = extract_panel_data(panel, panel_id, project_url)
            if key in results:
                results[key].update(panel_data)
            else:
                results[key] = panel_data
            
        return results
        
    except Exception as e:
        log_error(f"Error scraping project: {str(e)}")
        return []
