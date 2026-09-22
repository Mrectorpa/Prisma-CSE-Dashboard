import requests
import json

url = "https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/serviceConnectivity?agg_by=tenant"

payload = json.dumps({
  "filter": {
    "rules": [
      {
        "operator": "in",
        "property": "node_type",
        "values": [
          51,
          48
        ]
      },
      {
        "operator": "in",
        "property": "site_state_name",
        "values": [
          "Up",
          "Down"
        ]
      }
    ]
  },
  "properties": [
    {
      "property": "site_state_name"
    },
    {
      "property": "node_type"
    },
    {
      "property": "sub_tenant_id"
    },
    {
      "alias": "count",
      "function": "distinct_count",
      "property": "site_name"
    }
  ]
})
headers = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
  'X-PANW-Region': 'americas',
  'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJraWQiOiJyc2Etc2lnbi1wa2NzMS0yMDQ4LXNoYTI1Ni8xIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiJhMzlkN2M3OS1hMDQwLTRiZGEtYjYxZC1jNGI4M2YyMDFiOTkiLCJjdHMiOiJPQVVUSDJfU1RBVEVMRVNTX0dSQU5UIiwiYXVkaXRUcmFja2luZ0lkIjoiOTVmMzQ1NTQtOWUyNy00ZjNmLWI2NDAtYWU3MTVhMjNlOGRmLTEzNDEyMTYxNzgiLCJzdWJuYW1lIjoiYTM5ZDdjNzktYTA0MC00YmRhLWI2MWQtYzRiODNmMjAxYjk5IiwiaXNzIjoiaHR0cHM6Ly9hdXRoLmFwcHMucGFsb2FsdG9uZXR3b3Jrcy5jb206NDQzL2FtL29hdXRoMiIsInRva2VuTmFtZSI6ImFjY2Vzc190b2tlbiIsInRva2VuX3R5cGUiOiJCZWFyZXIiLCJhdXRoR3JhbnRJZCI6IlMwMkRlQW9kM2h5aE15eWczLW1HVnJORklhOCIsImF1ZCI6Im1yZWN0b3Itc2VydmljZS1hY2NvdW50QDE2MDI0MzYxODYuaWFtLnBhbnNlcnZpY2VhY2NvdW50LmNvbSIsIm5iZiI6MTc4NTg2Mjc1MiwiZ3JhbnRfdHlwZSI6ImNsaWVudF9jcmVkZW50aWFscyIsInNjb3BlIjpbInRzZ19pZDoxMzUxMjQ4NTc3IiwicHJvZmlsZSIsImVtYWlsIl0sImF1dGhfdGltZSI6MTc4NTg2Mjc1MiwicmVhbG0iOiIvIiwiZXhwIjoxNzg1ODYzNjUyLCJpYXQiOjE3ODU4NjI3NTIsImV4cGlyZXNfaW4iOjkwMCwianRpIjoiRXdFVFZheHFZdFRSUndXQWtzVmcwTU5nT21JIiwidHNnX2lkIjoiMTM1MTI0ODU3NyIsImFjY2VzcyI6eyJwcm46MTM1MTI0ODU3Nzo6OjoiOlsic3VwZXJ1c2VyIiwiYmFzZSJdfX0.Ba04OiFk1QTEJJc3ciO19Zk-43R2FFqVVOJ0VEPvPKvKkENz3SVh1JqPI87Cpl0_n_iezqrLjStIkcYo46uf7MluUzetuXUyER8WXlMFJPatEr3GlSVpQON_J8p7og0cdBNkr62WV_gd7E1HNn2ZrdRiD8Q1frrZrcL-WTK6LjTj4lRDbUi6qvtTyJYK1Pc5GmiM2tYcnDbuH7J7KlO-whLmMNWXpkNbljhY4fR4YrzfRcGixiaa9lzID0Mqp53y8SjxcrU9f5bT2f1ijCqftFVIN85_tOS-0AlNpTr1k_4HBIVdHT9PwSxfmj0DJffgQpOB7r5ch3upE6ScCdxwDA'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)