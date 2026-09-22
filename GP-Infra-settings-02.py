import requests

url = "https://api.sase.paloaltonetworks.com/sse/config/v1/mobile-agent/infrastructure-settings?folder=Mobile Users"

headers = {
    'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJraWQiOiJyc2Etc2lnbi1wa2NzMS0yMDQ4LXNoYTI1Ni8xIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiJhMzlkN2M3OS1hMDQwLTRiZGEtYjYxZC1jNGI4M2YyMDFiOTkiLCJjdHMiOiJPQVVUSDJfU1RBVEVMRVNTX0dSQU5UIiwiYXVkaXRUcmFja2luZ0lkIjoiOTVlYTdkZjgtYzBjMi00OGMzLWI4NDQtNWIxOGJiYWJmODYyLTEwNzA4MDU1MDEiLCJzdWJuYW1lIjoiYTM5ZDdjNzktYTA0MC00YmRhLWI2MWQtYzRiODNmMjAxYjk5IiwiaXNzIjoiaHR0cHM6Ly9hdXRoLmFwcHMucGFsb2FsdG9uZXR3b3Jrcy5jb206NDQzL2FtL29hdXRoMiIsInRva2VuTmFtZSI6ImFjY2Vzc190b2tlbiIsInRva2VuX3R5cGUiOiJCZWFyZXIiLCJhdXRoR3JhbnRJZCI6Il8xai1udzc1eFJvZExQaWI3SFZDV3lHanVjayIsImF1ZCI6Im1yZWN0b3Itc2VydmljZS1hY2NvdW50QDE2MDI0MzYxODYuaWFtLnBhbnNlcnZpY2VhY2NvdW50LmNvbSIsIm5iZiI6MTc4NDY1NzYxMCwiZ3JhbnRfdHlwZSI6ImNsaWVudF9jcmVkZW50aWFscyIsInNjb3BlIjpbInRzZ19pZDoxOTQ3OTg1MzgzIiwicHJvZmlsZSIsImVtYWlsIl0sImF1dGhfdGltZSI6MTc4NDY1NzYxMCwicmVhbG0iOiIvIiwiZXhwIjoxNzg0NjU4NTEwLCJpYXQiOjE3ODQ2NTc2MTAsImV4cGlyZXNfaW4iOjkwMCwianRpIjoidExXenVsSS14M3J6RWVLdkN4MGZheUZWQlBvIiwidHNnX2lkIjoiMTk0Nzk4NTM4MyIsImFjY2VzcyI6eyJwcm46MTk0Nzk4NTM4Mzo6OjoiOlsic3VwZXJ1c2VyIiwiYmFzZSJdfX0.m_eX43x_JlCaqGGWUo9kKzTj4pUmpiOAv23z1NPH5S5oNIsJb36_7IWx-kk4Sc3vAqh-ye_aj1GDnYqe_OB3P7qDBPJHSUTMQQ4HqMMaekW0wjMp_MHU0CdmhchZD-W4-JDAZy0brsZutwUKDlXtXaSYy5s-1rQ50fkKh8eLy8EJ01DFtvxJzO9gEEBf0LST92H-WydEN3hmO8kw8XDzkSkSVkZnv9LYdGdsiIUUd_8-3zAn4GCrzW7w5Qg7VFutnXdSsulTl82xG1_0SrYAnNtTbjsI_5wf5Qv8ksATLtxSNeIjyEOH3CaJRFZ2w9cE5WRmDfcLy8DuJSRYIhXfAQ'
}

# Python dictionary representation
payload = {
    "name": "Mobile-Users-Infra-Settings",
    "ipv6": True,
    "ip_pools": [
        {
            "name": "Primary-IP-Pool",
            "ip_pool": [
                "10.100.0.0/16"
            ]
        }
    ],
    "dns_servers": [
        {
            "name": "Deloitte-DNS-Config",
            "dns_suffix": [
                "deloitte.com"
            ],
            "internal_dns_match": [
                {
                    "name": "Internal-Match-Rule",
                    "domain_list": [
                        "*.deloitte.com"
                    ],
                    "primary": {
                        "dns_server": "10.28.10.58"
                    },
                    "secondary": {
                        "dns_server": "10.26.10.58"
                    }
                }
            ],
            "primary_public_dns": {
                "dns_server": "use_cloud_default"
            },
            "secondary_public_dns": {
                "dns_server": "use_cloud_default"
            }
        }
    ],
    "enable_wins": {
        "no": {}  # Selected 'no' (or provide 'yes' block instead)
    },
    "portal_hostname": {
        "default_domain": {  # Selected 'default_domain' (or 'custom_domain')
            "hostname": "gp-portal.deloitte.com"
        }
    },
    "udp_queries": {
        "retries": {
            "attempts": 1,
            "interval": 1
        }
    }
}

response = requests.put(url, headers=headers, json=payload)
print(response.text)