import requests
import json

url = "https://api.sase.paloaltonetworks.com/insights/v3.0/resource/query/sites/bandwidth_consumption_histogram"

payload = json.dumps({
  "filter": {
    "rules": [
      {
        "operator": "last_n_days",
        "property": "event_time",
        "values": [
          30
        ]
      },
      {
        "operator": "in",
        "property": "edge_location_display_name",
        "values": [
          "US West"
        ]
      },
      {
        "operator": "in",
        "property": "site_name",
        "values": [
          "CSN-ECMP"
        ]
      },
      {
        "operator": "in",
        "property": "node_type",
        "values": [
          48,
          157
        ]
      },
      {
        "operator": "in",
        "property": "instance_state",
        "values": [
          0,
          1,
          2
        ]
      },
      {
        "operator": "in",
        "property": "aggregate_region_display_name",
        "values": [
          "US West"
        ]
      },
      {
        "operator": "in",
        "property": "transport_type",
        "values": [
          "IPSEC",
          "GRE"
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
  'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJraWQiOiJyc2Etc2lnbi1wa2NzMS0yMDQ4LXNoYTI1Ni8xIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiI5NmEzOGE0YS0xYjg4LTQ2ZmUtYTVhYS0zZjIyYzhmYmVkNzgiLCJjdHMiOiJPQVVUSDJfU1RBVEVMRVNTX0dSQU5UIiwiYXVkaXRUcmFja2luZ0lkIjoiNDY2Y2YxYzItYWRjYi00NDc1LWI1ZGMtOTJkYWE4ZTFiZGQyLTE5MDU4OTYxMyIsInN1Ym5hbWUiOiI5NmEzOGE0YS0xYjg4LTQ2ZmUtYTVhYS0zZjIyYzhmYmVkNzgiLCJpc3MiOiJodHRwczovL2F1dGguYXBwcy5wYWxvYWx0b25ldHdvcmtzLmNvbTo0NDMvYW0vb2F1dGgyIiwidG9rZW5OYW1lIjoiYWNjZXNzX3Rva2VuIiwidG9rZW5fdHlwZSI6IkJlYXJlciIsImF1dGhHcmFudElkIjoiajRXMDZyV1huNjNCM090Q3hvVnlwdHgta0VRIiwiYXVkIjoibXJlY3Rvci1zdmMtYWNjb3VudEAxNjAyNDM2MTg2LmlhbS5wYW5zZXJ2aWNlYWNjb3VudC5jb20iLCJuYmYiOjE3OTEyMzM4NzcsImdyYW50X3R5cGUiOiJjbGllbnRfY3JlZGVudGlhbHMiLCJzY29wZSI6WyJ0c2dfaWQ6MTM1MTI0ODU3NyIsInByb2ZpbGUiLCJlbWFpbCJdLCJhdXRoX3RpbWUiOjE3OTEyMzM4NzcsInJlYWxtIjoiLyIsImV4cCI6MTc5MTIzNDc3NywiaWF0IjoxNzkxMjMzODc3LCJleHBpcmVzX2luIjo5MDAsImp0aSI6ImlEU29Fc0gxTkU4MkRoVzRHb3Qxay1mQnNoayIsInRzZ19pZCI6IjEzNTEyNDg1NzciLCJhY2Nlc3MiOnsicHJuOjEzNTEyNDg1Nzc6Ojo6IjpbInZpZXdfb25seV9hZG1pbiIsInNvY19hbmFseXN0IiwiYmFzZSJdLCJwcm46MTM1MTI0ODU3NzpwcmlzbWFfYWNjZXNzOjo6IjpbInNvY19hbmFseXN0Il19fQ.Rr61ZwI6y3HqGep7Iv7f1QkiE05KP4eVSjOxHlENODOS35lcG2poYa_wooFm0rBkSVK0asMXstz4DHU0fmOgOPFHcJHif83tM9VbGbgvnmrewCvS57MtoqgZi88Nh9uP0HZOefPE41uGIkkZ_gXjFe_fZs-bcY5kvHJZ7JzOuhE8uerAGGqPV_01OhWUzWq8QrA9j4Bvvk8MsOurwT5AtUnCO115BCzvoa5N0ddFTqGyMcLDu-c6HWx7tV575PTioix102dwT0rRW21i1e-TI0bWmlzxWtOjDOJDIigpOhn0EN02gzkM69SYJjYw3q_6cTQCP1Cbw_6kYqnk30ALIQ'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)