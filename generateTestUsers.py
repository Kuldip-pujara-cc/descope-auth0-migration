import requests
import json

# Function to generate user details
def generate_user_details(i):
    return {
        "email": f"user{i}@example.com",
        "blocked": False,
        "email_verified": True,
        "given_name": f"Given{i}",
        "family_name": f"Family{i}",
        "name": f"Given{i} Family{i}",
        "nickname": f"Nick{i}",
        "picture": f"http://example.com/user{i}.jpg",
        "password": f"password{i}!33W",
        "connection": "Username-Password-Authentication"
    }

# Define the URL and headers
url = 'https://dev-zx7jen5gbxsmqmet.us.auth0.com/api/v2/users'
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Authorization': 'Bearer <JWT TOKEN>'
}

for i in range(1, 101):
    data = generate_user_details(i)
    response = requests.post(url, headers=headers, json=data)
    print(response.status_code, response.json())
