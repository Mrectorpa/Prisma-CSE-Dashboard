import requests
import json

url = "https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/resource"

payload = json.dumps({
  "properties": [
    {
      "property": "node_type"
    },
    {
      "alias": "node_count",
      "function": "count",
      "property": "node_type"
    }
  ]
})
headers = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
  'X-PANW-Region': 'americas',
  'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJraWQiOiJyc2Etc2lnbi1wa2NzMS0yMDQ4LXNoYTI1Ni8xIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiJhMzlkN2M3OS1hMDQwLTRiZGEtYjYxZC1jNGI4M2YyMDFiOTkiLCJjdHMiOiJPQVVUSDJfU1RBVEVMRVNTX0dSQU5UIiwiYXVkaXRUcmFja2luZ0lkIjoiYmI4NWIxZDctMjE1NS00OTM5LWI1NTUtNWJiODNkNmE0ODRhLTIyNjE0MjE2NyIsInN1Ym5hbWUiOiJhMzlkN2M3OS1hMDQwLTRiZGEtYjYxZC1jNGI4M2YyMDFiOTkiLCJpc3MiOiJodHRwczovL2F1dGguYXBwcy5wYWxvYWx0b25ldHdvcmtzLmNvbTo0NDMvYW0vb2F1dGgyIiwidG9rZW5OYW1lIjoiYWNjZXNzX3Rva2VuIiwidG9rZW5fdHlwZSI6IkJlYXJlciIsImF1dGhHcmFudElkIjoiUlZ0R0gwMTkzRFJERTN3MUtSdlp4LXgwbHdzIiwiYXVkIjoibXJlY3Rvci1zZXJ2aWNlLWFjY291bnRAMTYwMjQzNjE4Ni5pYW0ucGFuc2VydmljZWFjY291bnQuY29tIiwibmJmIjoxNzgwNDI2NzMzLCJncmFudF90eXBlIjoiY2xpZW50X2NyZWRlbnRpYWxzIiwic2NvcGUiOlsicHJvZmlsZSIsInRzZ19pZDoxNjAyNDM2MTg2IiwiZW1haWwiXSwiYXV0aF90aW1lIjoxNzgwNDI2NzMzLCJyZWFsbSI6Ii8iLCJleHAiOjE3ODA0Mjc2MzMsImlhdCI6MTc4MDQyNjczMywiZXhwaXJlc19pbiI6OTAwLCJqdGkiOiJJbDVJdnJPXzhQa1pya3IxVzV4ZUNtTkhDQnMiLCJ0c2dfaWQiOiIxNjAyNDM2MTg2IiwiYWNjZXNzIjp7InBybjoxNjAyNDM2MTg2Ojo6OiI6WyJzdXBlcnVzZXIiLCJiYXNlIl19fQ.IiO8jwz__bKcQQIwWOQegkan2Tx2cb6qVm3XRUiXU7M46fHAxPMQxVAkWfmtn0xqTYfo_sXVMMzH9IL9iIfVCF1v66LEQwN16neVTvgIZs1aNaqfB5xSfCm1LNZmedvfJ3zqpmp09gzugV_wTY2MdCarmC44f1_kLMrnMG7eewwfKkbKFt2xYEvUzo3mNv8gk5NbubAQ3uc6M-kHmOwXjxFDJ0CJmFyiw0My0QgAzvR_gDDAS4AEOpDnsWEKwlwn72NLoDelCsLioyk2AHh5zhUqnaDhMTpSn3yrX7HnA8GZYtPlT-IeoRB7N5WcdJ0XaWnqprKeXC-wDIq4qDK0Kw'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)