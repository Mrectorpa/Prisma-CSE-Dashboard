import requests
import json

url = "https://api.strata.paloaltonetworks.com/config/mobile-agent/v1/agent-profiles?folder=Mobile Users"

payload = json.dumps({
  "name": "Always On - COA-ALL-TES",
  "folder": "Mobile Users",
  "gateways": {
    "external": {
      "list": [
        {
          "name": "US-RUW-ALL",
          "fqdn": "ushdcpavpn01.us.deloitte.com",  # Moved up out of the 'choice' node
          "manual": True,
          "priority_rule": [
            {
              "name": "any",
              "priority": "0",
            }
          ]
        }
      ]
    }
  }
})
headers = {
  'Content-Type': 'application/json',
  'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJraWQiOiJyc2Etc2lnbi1wa2NzMS0yMDQ4LXNoYTI1Ni8xIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiJhMzlkN2M3OS1hMDQwLTRiZGEtYjYxZC1jNGI4M2YyMDFiOTkiLCJjdHMiOiJPQVVUSDJfU1RBVEVMRVNTX0dSQU5UIiwiYXVkaXRUcmFja2luZ0lkIjoiMTJlNDAzYTYtYWIyZC00OTllLTllOWMtZmE0ZmIwZjY4MThmLTQzODg2ODYzMSIsInN1Ym5hbWUiOiJhMzlkN2M3OS1hMDQwLTRiZGEtYjYxZC1jNGI4M2YyMDFiOTkiLCJpc3MiOiJodHRwczovL2F1dGguYXBwcy5wYWxvYWx0b25ldHdvcmtzLmNvbTo0NDMvYW0vb2F1dGgyIiwidG9rZW5OYW1lIjoiYWNjZXNzX3Rva2VuIiwidG9rZW5fdHlwZSI6IkJlYXJlciIsImF1dGhHcmFudElkIjoiV0RkWGJYQmJEd3Rsc2dNX210ZGM5LUU1MzJFIiwiYXVkIjoibXJlY3Rvci1zZXJ2aWNlLWFjY291bnRAMTYwMjQzNjE4Ni5pYW0ucGFuc2VydmljZWFjY291bnQuY29tIiwibmJmIjoxNzgyMzA5MzY2LCJncmFudF90eXBlIjoiY2xpZW50X2NyZWRlbnRpYWxzIiwic2NvcGUiOlsidHNnX2lkOjE5NDc5ODUzODMiLCJwcm9maWxlIiwiZW1haWwiXSwiYXV0aF90aW1lIjoxNzgyMzA5MzY2LCJyZWFsbSI6Ii8iLCJleHAiOjE3ODIzMTAyNjYsImlhdCI6MTc4MjMwOTM2NiwiZXhwaXJlc19pbiI6OTAwLCJqdGkiOiJqTGpxQlVhdTBoYTNya3ZTQlkxVnU4Nm5zSWMiLCJ0c2dfaWQiOiIxOTQ3OTg1MzgzIiwiYWNjZXNzIjp7InBybjoxOTQ3OTg1MzgzOjo6OiI6WyJzdXBlcnVzZXIiLCJiYXNlIl19fQ.GeGs4WPmvvvRWFm44kIasMXFLPUJ0RsA-DUADDQkQhKNcqP0ftKSizfcFdWUC5pEcDGJDKDkSAKRPEK3YSuMfPILeKGMnxdXuw8MsyHTyXIgZ3JoqAMYH4cuJaPoXvMp21a1Ugr80QWAH9rrpD5GuAZVbi7stagVusslw4nnOK95NDcSDRaktv4QwuYMJsSFfVpUMCGwvAJ_9FTrtATOjzcBdM7jq5fjAU532L43co5OM2GB8DuzAot7x9sQn-HsMiqmpEcR2wLo54_IC_2ZumGUt8DRc8zAms947x4EAr7Mw7CSlISfLq2nn9bR9NIOv1DkYwb6WqBgFtpIqjpX0Q'
}

response = requests.request("PUT", url, headers=headers, data=payload)

print(response.text)