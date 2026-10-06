
import requests
import json

# --- CONFIGURATION ---
TSG_ID = "YOUR_TSG_ID"
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REGION = "us"  # Region code (e.g., 'us', 'de', 'jp')
AUTH_URL = "https://auth.apps.paloaltonetworks.com/am/oauth2/access_token"
API_URL = "https://pa-us01.api.prismaaccess.com/api/sase/v3.0/resource/query/sites/rn_spn_node_site_list"

def get_token():
    payload = {'grant_type': 'client_credentials', 'scope': f'tsg_id:{TSG_ID}'}
    resp = requests.post(AUTH_URL, data=payload, auth=(CLIENT_ID, CLIENT_SECRET))
    return resp.json().get('access_token')

def query_site_list(token):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-PANW-Region': REGION
    }
    
    # Insights 3.0 Mandatory Payload Structure
    payload = {
        "properties": [
            "site_name",
            "node_name",
            "status",
            "compute_location"
        ],
        "filter": {
            "operator": "and",
            "rules": [
                {
                    "property": "event_time",
                    "operator": "last_n_days",
                    "values": [7]
                }
            ]
        },
        "limit": 100
    }

    print(f"Querying endpoint with mandatory properties and filter...")
    response = requests.post(API_URL, headers=headers, json=payload)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None

if __name__ == "__main__":
    access_token = get_token()
    if access_token:
        result = query_site_list(access_token)
        if result:
            print(json.dumps(result, indent=2))
