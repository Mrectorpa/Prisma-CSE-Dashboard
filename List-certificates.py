import requests

url = "https://api.sase.paloaltonetworks.com/sse/config/v1/certificates?folder=Mobile Users"

payload = {}
headers = {
  'Accept': 'application/json',
  'Authorization': 'Bearer <token>'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)