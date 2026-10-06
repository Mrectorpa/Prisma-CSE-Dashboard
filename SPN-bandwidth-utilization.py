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
  'Prisma-Tenant': '1604685921',
  'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJraWQiOiJyc2Etc2lnbi1wa2NzMS0yMDQ4LXNoYTI1Ni8xIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiI5NmEzOGE0YS0xYjg4LTQ2ZmUtYTVhYS0zZjIyYzhmYmVkNzgiLCJjdHMiOiJPQVVUSDJfU1RBVEVMRVNTX0dSQU5UIiwiYXVkaXRUcmFja2luZ0lkIjoiODZiMzNiOWUtNjIzZC00MjNiLTk0OGMtYzk1MTg3OGI4MTRmLTE4Njg3MTA1MSIsInN1Ym5hbWUiOiI5NmEzOGE0YS0xYjg4LTQ2ZmUtYTVhYS0zZjIyYzhmYmVkNzgiLCJpc3MiOiJodHRwczovL2F1dGguYXBwcy5wYWxvYWx0b25ldHdvcmtzLmNvbTo0NDMvYW0vb2F1dGgyIiwidG9rZW5OYW1lIjoiYWNjZXNzX3Rva2VuIiwidG9rZW5fdHlwZSI6IkJlYXJlciIsImF1dGhHcmFudElkIjoicXNCeEZSUDZuNG1ISUdISTBNMG5XUDYxWGVZIiwiYXVkIjoibXJlY3Rvci1zdmMtYWNjb3VudEAxNjAyNDM2MTg2LmlhbS5wYW5zZXJ2aWNlYWNjb3VudC5jb20iLCJuYmYiOjE3OTEyMjIzMDksImdyYW50X3R5cGUiOiJjbGllbnRfY3JlZGVudGlhbHMiLCJzY29wZSI6WyJwcm9maWxlIiwidHNnX2lkOjE2MDI0MzYxODYiLCJlbWFpbCJdLCJhdXRoX3RpbWUiOjE3OTEyMjIzMDksInJlYWxtIjoiLyIsImV4cCI6MTc5MTIyMzIwOSwiaWF0IjoxNzkxMjIyMzA5LCJleHBpcmVzX2luIjo5MDAsImp0aSI6InNqM0JCSy1xWEJ6MWRXc295S2xjdHppc0tWWSIsInRzZ19pZCI6IjE2MDI0MzYxODYiLCJhY2Nlc3MiOnsicHJuOjE2MDI0MzYxODY6Ojo6IjpbInZpZXdfb25seV9hZG1pbiIsImJhc2UiXX19.W_hgiv-UiIZjxw5waKw9aFnpBVFRcFsr7BFSIW-VeifWQg6vPCYbPOR0KrjK48-BqOBBSvN3Ox1_vl0vN-XKLbBbvInKRNcBaiXFUCVoHNeXns1h80QAm-HaLXJxF9-fEJ7CZ0sRLFHCaLTne2DlXBYjTpCu8eMb8VUaeCtwn6gbpG-CeWlMd_ogVej-KjOvnUomm28qEiVhcy48-OncoBF-TZq5T4pEKyHQQGWxgrr2zjMm-Jh1d2Y_iiVTeHQoLaJYM26pyZF2olo-ur7eegQ4pWmI2F3fywkMlfnFT4OcGVBuNxT8QtmpMx5FlO1dd3xPogq3SACC2Ftch94K2w'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)