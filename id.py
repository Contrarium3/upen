import json
from bs4 import BeautifulSoup
import re

from loggers import *


import pandas as pd
from pyproj import Transformer
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

transformer = Transformer.from_crs("EPSG:4326", "EPSG:2100", always_xy=True)


# download files!!!!!!!!!!

ids = {'panel-location', 'panel-project_info', 'panel-clarifications', 'panel-additional_files', 'panel-opinions', 'panel-application_authority', 'panel-copies', 'panel-opinion_kespa', 
       'panel-files', 'panel-publication', 'panel-actions', 'panel-studier_info', 'panel-consultation', 'panel-evaluation', 'panel-application_info', 'panel-company_info'} 


# DONE: 
# {'panel-additional_files',
#   'panel-application_authority',
#   'panel-application_info',
#   'panel-company_info',
#   'panel-consultation',
#   'panel-copies',
#   'panel-evaluation',
#   'panel-files',
#   'panel-location',
#   'panel-opinions',
#   'panel-project_info',
#   'panel-publication',
#   'panel-studier_info'}


def extract_panel_data(panel, panel_id, project_url):
    results = {}
    data = {}

    
    ### Get location panel data
    if panel_id == "panel-location":
        return extract_panel_location(panel , panel_id, project_url)
    

    elif panel_id in ["panel-opinions", 'panel-publication'] :
        data['Γνωμοδοτήσεις'] = extract_panel_opinions(panel, panel_id, project_url)
    
    else:
        tables = panel.find_all("table")
        num_tables = len(tables)
        if num_tables > 0: 
            log_info(f'Solid Info: {num_tables} tables found for {panel_id} in {project_url}')
        if num_tables > 1: 
            print(f'Solid Info: {num_tables} tables found for {panel_id} in {project_url}')
            
    
        # Process each table
        for j, table in enumerate(tables):
            rows = table.select('tbody tr')
            if rows:  # Check if there are any rows
                data[f'table_{j}'] = extract_table(table, panel_id, project_url)
        
    try:
        
        form_groups = panel.find_all(class_='form-group')
        # log_info(f'{len(form_groups)} form groups found in panel: {panel_id}')
        i= 0
        for form_group in form_groups :
            label_tag = form_group.find(class_ = 'control-label')
            if not label_tag:  
                # log_info(f"Missing label in panel {panel_id} for {project_url}, form group position: {i}/{len(form_groups)}")
                text = form_group.get_text(strip=True)
                if text != "":
                    data[f'text_{i}'] = form_group.get_text(strip=True)
                continue  # Skip this iteration if no label is found
            
            label = label_tag.get_text(strip=True)
            control_view = form_group.find(class_='control-view')

            if control_view:
                # Handle different control-view content types
                if control_view.find('ul', class_='no-style'):
                    items = [li.get_text(strip=True) for li in control_view.find_all('li')]
                    links = [li.find('a')['href'] for li in control_view.find_all('li') if li.find('a')]
                    
                    if links != []:
                        links = set(links)
                        data[label] = {"items": items, "links": list(links)}
                    else : 
                        data[label] = items
                    

                elif control_view.find('table'):
                    rows = []
                    links = []
                    tbody = control_view.find('tbody')
                    if tbody:
                        for tr in tbody.find_all('tr'):
                            rows.append([td.get_text(strip=True) for td in tr.find_all('td')])
                            links.append( [a['href'] for td in tr.find_all('td') for a in td.find_all('a')] )
                    
                    if links != []:
                        links = set(links)
                        data[label] = {"rows": rows, "links": list(links)}
                    else : 
                        data[label] = rows

                else:
                    text = control_view.get_text(strip=True)
                    links = [a['href'] for a in control_view.find_all('a')]
                    if links != []:
                        links = set(links)
                        data[label] = {"text": text, "links": list(links)}
                    else : 
                        data[label] = text
                    

                    
            else : 
                if label == 'Έντυπο Δ11Έντυπο Δ11' or label == 'Παρατηρήσεις' or label == "":
                    pass
                else:
                    log_error(f'Missing control view in a form groupp in extract panel data {panel_id} , label: {label} for {project_url}')
                    
        results[panel_id] = data
        return results
    

    except Exception as e:
        log_error(f"Error in extract_panel_data (Panel ID: {panel_id}) for {project_url}: {e}")
        return {}  # Return an empty dictionary to prevent further issues




# def extract_location_panel(panel):
    try:
        results = {}
        data = {}
        
        # Extract coordinates from hidden input
        hidden_input = panel.find('input', {'id': 'mapLatLng'})
        if hidden_input:
            data['Coordinates'] = hidden_input['value']

        # Extract point type (Linear or Non-Linear)
        point_type_select = panel.find('select', {'id': 'sel_point_type'})
        if point_type_select:
            selected_option = point_type_select.find('option', selected=True)
            data['Point Type'] = selected_option.get_text(strip=True) if selected_option else "Unknown"

        # Extract individual coordinate points
        data['Coordinate Points'] = []
        for row in panel.find_all('div', {'id': lambda x: x and x.startswith('point_data_row_')}):
            point_label = row.find_previous_sibling('label')
            point_name = point_label.get_text(strip=True) if point_label else "Unknown"
            
            lat_input = row.find('input', {'name': 'lat[]'})
            lng_input = row.find('input', {'name': 'lng[]'})
            x_input = row.find('input', {'name': 'latEGSA[]'})
            y_input = row.find('input', {'name': 'lngEGSA'})

            if lat_input and lng_input and x_input and y_input:
                data['Coordinate Points'].append({
                    "Point": point_name,
                    "Latitude (WGS84)": lat_input['value'],
                    "Longitude (WGS84)": lng_input['value'],
                    "X (EGSA87)": x_input['value'],
                    "Y (EGSA87)": y_input['value']
                })

        # Extract address
        address_label = panel.find('label', string=lambda x: x and "Τοπωνύμιο - Διεύθυνση" in x)
        if address_label:
            address_container = address_label.find_next('div', class_='control-view')
            data['Address'] = address_container.get_text(strip=True) if address_container else "Unknown"

        # Extract administrative region
        region_label = panel.find('label', string=lambda x: x and "Περιφέρεια" in x)
        if region_label:
            region_ul = region_label.find_next('ul', class_='control-view')
            data['Region'] = region_ul.get_text(strip=True) if region_ul else "Unknown"
        result
        return data

    except Exception as e:
        log_error(f"Error in extract_location_panel: {e}")
        return {}

def extract_panel_location(panel, panel_id, project_url):
    try:
        
        data = {}
        
        result = {
            "coordinates": {
                "type": None,
                "points": [],
                "raw": panel.find('input', {'id': 'mapLatLng'})['value'] if panel.find('input', {'id': 'mapLatLng'}) else None
            },
            "location_name": None,
            "administrative_hierarchies": []
        }

        # Determine point type
        script = panel.find('script', string=re.compile('var pointTYpe ='))
        if script:
            point_type_match = re.search(r'var pointTYpe = "(\d)"', script.string)
            result['coordinates']['type'] = "linear" if point_type_match and point_type_match.group(1) == "1" else "single"

        # Extract raw coordinates
        raw_coords = []
        if result['coordinates']['raw']:
            raw_coords = result['coordinates']['raw'].split('-')
            raw_coords = [coord.split(',') for coord in raw_coords if coord]

        # Extract points by matching with raw coordinates
        point_containers = panel.find_all('div', id=re.compile('point_data_row'))
        
        for i, container in enumerate(point_containers):
            # Determine point type
            point_type = ["Αρχή", "Μέση", "Τέλος"][i] if i < 3 else f"Point {i+1}"
            
            # Get coordinates - prioritize raw coordinates when available
            if i < len(raw_coords):
                lat, lng = raw_coords[i]
            else:
                lat = lng = None

            x, y = transformer.transform(lng , lat)
            x , y = round(x , 2) , round(y , 2) 
            def smart_round(x):
                if x == int(x):
                    x = f"{int(x)}"
                    return x
                else: 
                    x = str(x)
                    return x
                
            x = smart_round(x)
            y = smart_round(y)                
                

            point = {
                "type": point_type,
                "EGSA87": {
                    "x": x,
                    "y": y
                },
                "WGS84": {
                    "φ": lat if lat else None,
                    "λ": lng if lng else None
                }
            }
            result['coordinates']['points'].append(point)

        # Location name - look for the control-view div after the map
        map_div = panel.find('div', id='googlemap')
        if map_div:
            location_div = map_div.find_next('div', class_='control-view')
            if location_div:
                result['location_name'] = location_div.get_text(strip=True)

        # Administrative hierarchies
        hierarchy_lists = panel.find_all('ul', class_='hidden-chained-location')
        for ul in hierarchy_lists:
            for li in ul.find_all('li'):
                hierarchy = [part.strip() for part in li.get_text(strip=True).split('/') if part.strip()]
                if hierarchy:
                    result['administrative_hierarchies'].append(hierarchy)



        data[panel_id] = result
        return data
    
    except Exception as e:
        log_error(f'Error in extract panel location for {project_url}: {e}')
        data[panel_id] = {}
        return data


# extract the table for panel opinions
def extract_panel_opinions(panel,panel_id, project_url):
    try:
        empty = "file/view/bTVVOTdSTy9qSlkrdTVSQ1U1a2hRbzk5cXN0TFBRMnJTb3RkOXgycjNPamlXbmdWV2Q1Qnd0clM4eG1oZldqb0xpTjNTaE9kM2w5ODBpZ0llbFRyaEE9PQ,,"
        
        # Initialize lists to store data
        data = []
        links = []
        
        # result = {}

        # Find all rows in the table body
        rows = panel.select('table tbody tr')

        if len(rows) == 0 :
            return {}
        links = []
        for row in rows:
            # Extract each column's data
            cols = row.find_all('td')
            
            # Get the text content or file link for each column
            service = cols[0].get_text(strip=True)
            evaluation = cols[1].get_text(strip=True)
            
            # Handle the file link in the opinion column
            
            # FOR DOWNLOAD!
            opinion_link = cols[2].find('a')
            opinion_href  = opinion_link['href'] if opinion_link and opinion_link['href']!=empty else ''
            opinion = opinion_link.text if opinion_link else ''
            links.append(opinion_href)

            
            # Get protocol number and date
            protocol = cols[3].get_text(strip=True)
            
            # Get additional data (empty in this case)
            additional_data = cols[4].find('a')
            additional_href = additional_data['href'] if additional_data and additional_data['href']!=empty else ''
            additional = additional_data.text if additional_data else ''
            links.append(additional_href)

            
            data.append([
            service,
            evaluation,
            opinion,
            # opinion_href,
            protocol,
            additional,
            # additional_href
        ])

        # Create DataFrame with text and link columns
        df = pd.DataFrame(data, columns=[
            'Υπηρεσία', 
            'Αξιολόγηση', 
            'Γνωμοδότηση', 
            # 'Γνωμοδότηση (Link)', 
            'Αρ. Πρωτ. εγγράφου και ημερομηνία', 
            'Συμπληρωματικά στοιχεία', 
            # 'Συμπληρωματικά στοιχεία (Link)'
        ])
        
        df_dict = df.to_dict(orient='records')
        # Add links to the DataFrame
        links = list(set(links))
        
        final_dict = {}
        final_dict['items'] = df_dict
        final_dict['links'] = links

        
        return  final_dict
    
    except Exception as e:
        log_error(f"Error in extract panel opinions for {panel_id} for {project_url}: {e}")
        return {}
    

import pandas as pd
from bs4 import BeautifulSoup

def extract_table(table, panel_id ,  project_url):
    """
    Extracts structured data and links from an HTML table using BeautifulSoup.

    Parameters:
    - panel: BeautifulSoup object containing the table
    - panel_id: Optional identifier for debugging/logging
    - project_url: Optional URL base for relative links
    - empty_value: Value used to identify empty/placeholder links

    Returns:
    - dict: {
        'items': list of dicts (each row),
        'links': list of extracted non-empty links
      }
    """
    try:
        empty_value = "file/view/bTVVOTdSTy9qSlkrdTVSQ1U1a2hRbzk5cXN0TFBRMnJTb3RkOXgycjNPamlXbmdWV2Q1Qnd0clM4eG1oZldqb0xpTjNTaE9kM2w5ODBpZ0llbFRyaEE9PQ,,"
       
        rows = table.select('tbody tr')
        if not rows:
            return {}

        # --- Auto-detect column headers from <thead> ---
        headers = []
        thead = table.find('thead')
        if thead:
            header_cells = thead.find_all('th')
            headers = [th.get_text(strip=True) for th in header_cells]

        all_data = []
        all_links = set()

        for row in rows:
            cols = row.find_all('td')
            row_data = []
            for col in cols:
                text = col.get_text(strip=True)
                link_tag = col.find('a')
                link_href = link_tag['href'] if link_tag and link_tag.get('href') and link_tag['href'] != empty_value else ''
                link_text = link_tag.get_text(strip=True) if link_tag else ''

                cell_value = link_text if link_href else text
                row_data.append(cell_value)

                if link_href:
                    all_links.add(link_href)

            all_data.append(row_data)

        # If headers were not found or count mismatches, generate fallback
        max_cols = max(len(row) for row in all_data)
        if not headers or len(headers) != max_cols:
            headers = [f"Column {i+1}" for i in range(max_cols)]

        df = pd.DataFrame(all_data, columns=headers[:max_cols])
        return {
            'items': df.to_dict(orient='records'),
            'links': list(all_links)
        }

    except Exception as e:
        print(f"Error extracting table from panel {panel_id} in {project_url}: {e}")
        return {}

