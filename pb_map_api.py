import requests
import json

# Define the base URL for the API
pin_map_base_url = "https://pinballmap.com"
get_reno_locations = "/api/v1/region/reno/locations.json"  

# Send a GET request to the API
#response = requests.get(base_url)

# Check if the request was successful (status code 200 means OK)
#if response.status_code == 200:
#    # Parse the JSON response
#    data = response.json()

#    print(json.dumps(data, indent=4))
#else:
#    print(f"Failed to fetch data: {response.status_code}")

"""
Fetches locations in the specified region from the Pinball Map API.
    
Args:
    region (str): The region to fetch locations for.
        
Returns:
    list: A list of locations in the specified region.
"""
def get_locations_in_region(region):
    
    url = f"{pin_map_base_url}/api/v1/region/{region}/locations.json"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        return data['locations']
    else:
        print(f"Failed to fetch data: {response.status_code}")
        return []
    
def get_machines_at_location(location):
    machine_names = []
    for machine_xref in location['location_machine_xrefs']:
        machine = machine_xref['machine']
        machine_names.append(machine['name'])
    return machine_names