import requests

url = "https://api.sase.paloaltonetworks.com/mt/pab/tenant/licenses"

payload = {}
headers = {
  'Accept': 'application/json'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)