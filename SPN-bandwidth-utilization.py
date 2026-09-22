import requests
import json

url = "https://api.sase.paloaltonetworks.com/insights/v3.0/resource/query/sites/bandwidth_consumption_histogram"

payload = json.dumps({
  "filter": {
    "rules": [
      {
        "operator": "last_n_hours",
        "property": "event_time",
        "values": [
          5
        ]
      }
    ]
  },
  "histogram": {
    "enableEmptyInterval": True,
    "property": "event_time",
    "range": "minute",
    "value": 30
  }
})
headers = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
  'PANW-Region': 'americas',
  'Prisma-Tenant': '1351248577',
  'Authorization': 'Bearer <token>'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)