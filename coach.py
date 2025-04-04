import requests
import json

# Define the base URL for the API
base_url = "https://pinballmap.com/api/v1/region/reno/locations.json"  

# Optionally, if the API requires parameters, you can define them here
params = {
    # Example: 'location_id': '123', or any other params the API might need
    'region' : 'Reno, NV'
}

# Send a GET request to the API
response = requests.get(base_url)

# Check if the request was successful (status code 200 means OK)
if response.status_code == 200:
    # Parse the JSON response
    data = response.json()

    print(json.dumps(data, indent=4))
else:
    print(f"Failed to fetch data: {response.status_code}")
