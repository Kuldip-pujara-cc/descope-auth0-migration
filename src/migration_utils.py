import json
import os
import sys
import requests
from dotenv import load_dotenv
import logging
import time
from datetime import datetime

from descope import (
    AuthException,
    DescopeClient,
    AssociatedTenant,
    RoleMapping,
    AttributeMapping,
    UserPassword,
    UserPasswordBcrypt,
    UserObj
)

log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# datetime object containing current date and time
now = datetime.now()

dt_string = now.strftime("%d_%m_%Y_%H:%M:%S")
logging_file_name = os.path.join(log_directory, f"migration_log_{dt_string}.log")
logging.basicConfig(
    filename=logging_file_name,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

"""Load and read environment variables from .env file"""
load_dotenv()
AUTH0_TOKEN = os.getenv("AUTH0_TOKEN")
AUTH0_TENANT_ID = os.getenv("AUTH0_TENANT_ID")
DESCOPE_PROJECT_ID = os.getenv("DESCOPE_PROJECT_ID")
DESCOPE_MANAGEMENT_KEY = os.getenv("DESCOPE_MANAGEMENT_KEY")

try:
    descope_client = DescopeClient(
        project_id=DESCOPE_PROJECT_ID, management_key=DESCOPE_MANAGEMENT_KEY
    )
except AuthException as error:
    logging.error(f"Failed to initialize Descope Client: {error}")
    sys.exit()


def api_request_with_retry(action, url, headers, data=None, max_retries=4, timeout=10):
    """
    Handles API requests with additional retry on timeout and rate limit.

    Args:
    - action (string): 'get' or 'post'
    - url (string): The URL of the path for the api request
    - headers (dict): Headers to be sent with the request
    - data (json): Optional and used only for post, but the payload to post
    - max_retries (int): The max number of retries
    - timeout (int): The timeout for the request in seconds
    Returns:
    - API Response
    - Or None
    """
    retries = 0
    while retries < max_retries:
        try:
            if action == "get":
                response = requests.get(url, headers=headers, timeout=timeout)
            else:
                response = requests.post(
                    url, headers=headers, data=data, timeout=timeout
                )

            if (
                response.status_code != 429
            ):  # Not a rate limit error, proceed with response
                return response

            # If rate limit error, prepare for retry
            retries += 1
            wait_time = 5**retries
            logging.info(f"Rate limit reached. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

        except requests.exceptions.ReadTimeout as e:
            # Handle read timeout exception
            logging.warning(f"Read timed out. (read timeout={timeout}): {e}")
            retries += 1
            wait_time = 5**retries
            logging.info(f"Retrying attempt {retries}/{max_retries}...")
            time.sleep(
                wait_time
            )  # Wait for 5 seconds before retrying or use a backoff strategy

        except requests.exceptions.RequestException as e:
            # Handle other request exceptions
            logging.error(f"A request exception occurred: {e}")
            break  # In case of other exceptions, you may want to break the loop

    logging.error("Max retries reached. Giving up.")
    return None


### Begin Auth0 Actions

def fetch_auth0_users_from_file(file_path):
    """
    Fetch and parse Auth0 users from the provided file.
    Uses JSON file directly without Auth0 API calls for faster processing.
    
    Returns:
    - all_users (list): A list of parsed Auth0 users if successful, empty list otherwise.
    """
    all_users = []
    with open(file_path, "r") as file:
        for line in file:
            if line.strip():  # Skip empty lines
                user_data = json.loads(line)
                
                # Normalize the user data structure
                # Handle both Auth0 export formats (with "Id" or "user_id")
                normalized_user = {
                    "user_id": user_data.get("Id") or user_data.get("user_id"),
                    "email": user_data.get("Email") or user_data.get("email"),
                    "email_verified": user_data.get("Email Verified") or user_data.get("email_verified", False),
                    "name": user_data.get("Name") or user_data.get("name", ""),
                    "given_name": user_data.get("Given Name") or user_data.get("given_name", ""),
                    "family_name": user_data.get("Family Name") or user_data.get("family_name", ""),
                    "nickname": user_data.get("Nickname") or user_data.get("nickname", ""),
                    "picture": user_data.get("Picture") or user_data.get("picture", ""),
                    "created_at": user_data.get("Created At") or user_data.get("created_at", ""),
                    "updated_at": user_data.get("Updated At") or user_data.get("updated_at", ""),
                }
                
                all_users.append(normalized_user)
    
    logging.info(f"Loaded {len(all_users)} users from file: {file_path}")
    return all_users

def fetch_auth0_users():
    """
    Fetch and parse Auth0 users from the provided endpoint.

    Returns:
    - all_users (Dict): A list of parsed Auth0 users if successful, empty list otherwise.
    """
    headers = {"Authorization": f"Bearer {AUTH0_TOKEN}"}
    page = 0
    per_page = 20
    all_users = []
    while True:
        response = api_request_with_retry(
            "get",
            f"https://{AUTH0_TENANT_ID}.au.auth0.com/api/v2/users?page={page}&per_page={per_page}",
            headers=headers,
        )
        if response.status_code != 200:
            logging.error(
                f"Error fetching Auth0 users. Status code: {response.status_code}"
            )
            return all_users
        users = response.json()
        if not users:
            break
        all_users.extend(users)
        page += 1
    return all_users


def fetch_auth0_roles():
    """
    Fetch and parse Auth0 roles from the provided endpoint.

    Returns:
    - all_roles (Dict): A list of parsed Auth0 roles if successful, empty list otherwise.
    """
    headers = {"Authorization": f"Bearer {AUTH0_TOKEN}"}
    page = 0
    per_page = 20
    all_roles = []
    while True:
        response = api_request_with_retry(
            "get",
            f"https://{AUTH0_TENANT_ID}.au.auth0.com/api/v2/roles?page={page}&per_page={per_page}",
            headers=headers,
        )
        if response.status_code != 200:
            logging.error(
                f"Error fetching Auth0 roles. Status code: {response.status_code}"
            )
            return all_roles
        roles = response.json()
        if not roles:
            break
        all_roles.extend(roles)
        page += 1
    return all_roles


def get_users_in_role(role):
    """
    Get and parse Auth0 users associated with the provided role.

    Returns:
    - role (string): The role ID to get the associated members
    """
    headers = {"Authorization": f"Bearer {AUTH0_TOKEN}"}
    page = 0
    per_page = 20
    all_users = []

    while True:
        response = api_request_with_retry(
            "get",
            f"https://{AUTH0_TENANT_ID}.au.auth0.com/api/v2/roles/{role}/users?page={page}&per_page={per_page}",
            headers=headers,
        )
        if response.status_code != 200:
            logging.error(
                f"Error fetching Auth0 users in roles. Status code: {response.status_code}"
            )
            return all_users
        users = response.json()
        if not users:
            break
        all_users.extend(users)
        page += 1
    return all_users


def get_permissions_for_role(role):
    """
    Get and parse Auth0 permissions for a role

    Args:
    - role (string): The id of the role to query for permissions
    Returns:
    - all_permissions (string): Dictionary of all permissions associated to the role.
    """
    headers = {"Authorization": f"Bearer {AUTH0_TOKEN}"}
    page = 0
    per_page = 20
    all_permissions = []

    while True:
        response = api_request_with_retry(
            "get",
            f"https://{AUTH0_TENANT_ID}.au.auth0.com/api/v2/roles/{role}/permissions?per_page={per_page}&page={page}",
            headers=headers,
        )
        if response.status_code != 200:
            logging.error(
                f"Error fetching Auth0 permissions in roles. Status code: {response.status_code}"
            )
            return all_permissions
        permissions = response.json()
        if not permissions:
            break
        all_permissions.extend(permissions)
        page += 1
    return all_permissions


def fetch_auth0_organizations():
    """
    Fetch and parse Auth0 organization members from the provided endpoint.

    Returns:
    - all_organizations (string): Dictionary of all organizations within the Auth0 tenant.
    """
    headers = {"Authorization": f"Bearer {AUTH0_TOKEN}"}
    page = 0
    per_page = 20
    all_organizations = []

    while True:
        response = api_request_with_retry(
            "get",
            f"https://{AUTH0_TENANT_ID}.au.auth0.com/api/v2/organizations?per_page={per_page}&page={page}",
            headers=headers,
        )
        if response.status_code != 200:
            logging.error(
                f"Error fetching Auth0 organizations. Status code: {response.status_code}"
            )
            return all_organizations
        organizations = response.json()
        if not organizations:
            break
        all_organizations.extend(organizations)
        page += 1
    return all_organizations


def fetch_auth0_organization_members(organization):
    """
    Fetch and parse Auth0 organization members from the provided endpoint.

    Args:
    - organization (string): Auth0 organization ID to fetch the members
    Returns:
    - all_members (dict): Dictionary of all members within the organization.
    """
    headers = {"Authorization": f"Bearer {AUTH0_TOKEN}"}
    page = 0
    per_page = 20
    all_members = []

    while True:
        response = api_request_with_retry(
            "get",
            f"https://{AUTH0_TENANT_ID}.au.auth0.com/api/v2/organizations/{organization}/members?per_page={per_page}&page={page}",
            headers=headers,
        )
        if response.status_code != 200:
            logging.error(
                f"Error fetching Auth0 organization members. Status code: {response.status_code}"
            )
            return all_members
        members = response.json()
        if not members:
            break
        all_members.extend(members)
        page += 1
    return all_members


### End Auth0 Actions

### Begin Descope Actions


def create_descope_role_and_permissions(role, permissions):
    """
    Create a Descope role and its associated permissions using the Descope Python SDK.

    Args:
    - role (dict): A dictionary containing role details from Auth0.
    - permissions (dict): A dictionary containing permissions details from Auth0.
    """
    permissionNames = []
    success_permissions = 0
    existing_permissions_descope = []
    failed_permissions = []
    for permission in permissions:
        name = permission["permission_name"]
        description = permission.get("description", "")
        try:
            descope_client.mgmt.permission.create(name=name, description=description)
            permissionNames.append(name)
            success_permissions += 1
        except AuthException as error:
            error_message_dict = json.loads(error.error_message)
            if  error_message_dict["errorCode"] == "E024104":
                existing_permissions_descope.append(name)
                permissionNames.append(name)
                logging.error(f"Unable to create permission: {name}.")
                logging.error(f"Status Code: {error.status_code}")
                logging.error(f"Error: {error.error_message}")
            else:
                failed_permissions.append(f"{name}, Reason: {error.error_message}")
                logging.error(f"Unable to create permission: {name}.")
                logging.error(f"Status Code: {error.status_code}")
                logging.error(f"Error: {error.error_message}")


    role_name = role["name"]
    if not check_role_exists_descope(role_name):
        role_description = role.get("description", "")
        try:
            descope_client.mgmt.role.create(
                name=role_name,
                description=role_description,
                permission_names=permissionNames,
            )
            return True, False, success_permissions, existing_permissions_descope, failed_permissions, ""
        except AuthException as error:
            logging.error(f"Unable to create role: {role_name}.")
            logging.error(f"Status Code: {error.status_code}")
            logging.error(f"Error: {error.error_message}")
            return (
                False,
                False,
                success_permissions,
                existing_permissions_descope,
                failed_permissions,
                f"{role_name}  Reason: {error.error_message}",
            )
    else:
        return False, True, success_permissions, existing_permissions_descope, failed_permissions, ""


def create_descope_user(user):
    """
    Create a Descope user based on matched Auth0 user data using Descope Python SDK.

    Args:
    - user (dict): A dictionary containing user details fetched from Auth0 API or JSON file.
    """
    try:
        login_ids = []
        connections = []
        
        # Handle identities if present (from API)
        identities = user.get("identities", [])
        
        if identities:
            # Original logic for API data with identities
            for identity in identities:
                if "Username" in identity["connection"]:
                    login_ids.append(user.get("email"))
                    connections.append(identity["connection"])
                elif "sms" in identity["connection"]:
                    login_ids.append(user.get("phone_number"))
                    connections.append(identity["connection"])
                elif "-" in identity["connection"]:
                    login_ids.append(
                        identity["connection"].split("-")[0] + "-" + identity["user_id"]
                    )
                    connections.append(identity["connection"])
                else:
                    login_ids.append(identity["connection"] + "-" + identity["user_id"])
                    connections.append(identity["connection"])
        else:
            # Handle JSON file data without identities field
            # Use email as primary login ID, or construct from user_id
            email = user.get("email")
            user_id = user.get("user_id", "")
            
            if email:
                login_ids.append(email)
            elif user_id:
                login_ids.append(user_id)
            else:
                # Skip users without email or user_id
                logging.warning(f"Skipping user without email or user_id: {user}")
                return False, None, None, user.get("name", "unknown")
            
            connections.append("imported-from-json")

        emails = [user.get("email")]
        
        # Check if we have valid login_ids
        if not login_ids or len(login_ids) == 0:
            logging.error(f"No valid login_id found for user: {user.get('email', user.get('user_id', 'unknown'))}")
            return False, None, None, user.get("user_id", "unknown")

        users = []
        try:
            resp = descope_client.mgmt.user.search_all(emails=emails)
            users = resp["users"]
        except AuthException as error:
            pass

        if len(users) == 0:
            login_id = login_ids[0]
            email = user.get("email")
            # Check if user has phone number and if it's from SMS provider
            phone = None
            if identities:
                for identity in identities:
                    if identity.get("provider") == "sms":
                        phone = user.get("phone_number")
                        break
            
            display_name = user.get("name")
            given_name = user.get("given_name")
            family_name = user.get("family_name")
            picture = user.get("picture")
            verified_email = user.get("email_verified", False)
            verified_phone = user.get("phone_verified", False) if phone else False
            custom_attributes = {
                "connection": ",".join(map(str, connections)),
                "freshlyMigrated": True,
            }
            additional_login_ids = login_ids[1 : len(login_ids)]
                
            # Create the user
            resp = descope_client.mgmt.user.create(
                login_id=login_id,
                email=email,
                display_name=display_name,
                given_name=given_name,
                family_name=family_name,
                phone=phone,
                picture=picture,
                custom_attributes=custom_attributes,
                verified_email=verified_email,
                verified_phone=verified_phone,
                additional_login_ids=additional_login_ids,
            )

            # Update user status if necessary
            status = "disabled" if user.get("blocked", False) else "enabled"
            if status == "disabled":
                try:
                    resp = descope_client.mgmt.user.deactivate(login_id=login_id)
                except AuthException as error:
                    logging.error(f"Unable to deactivate user.")
                    logging.error(f"Status Code: {error.status_code}")
                    logging.error(f"Error: {error.error_message}")
            elif status == "enabled":
                try:
                    resp = descope_client.mgmt.user.activate(login_id=login_id)
                except AuthException as error:
                    logging.error(f"Unable to activate user.")
                    logging.error(f"Status Code: {error.status_code}")
                    logging.error(f"Error: {error.error_message}")
            return True, "", False, ""
        else:
            user_to_update = users[0]
            if user.get("picture"):
                picture = user.get("picture")
            else:
                picture = user_to_update["picture"]

            if user.get("given_name"):
                given_name = user.get("given_name")
            else:
                given_name = user_to_update["givenName"]

            if user.get("family_name"):
                family_name = user.get("family_name")
            else:
                family_name = user_to_update["familyName"]

            custom_attributes = user_to_update.get("customAttributes") or {}
            if custom_attributes and "connection" in custom_attributes:
                for connection in custom_attributes["connection"].split(","):
                    if connection in connections:
                        connections.remove(connection)
            if len(connections) == 0:
                login_id = user_to_update["loginIds"][0]
                status = "disabled" if user.get("blocked", False) else "enabled"
                if status == "disabled" or user_to_update["status"] == "disabled":
                    try:
                        resp = descope_client.mgmt.user.deactivate(login_id=login_id)
                    except AuthException as error:
                        logging.error(f"Unable to deactivate user.")
                        logging.error(f"Status Code: {error.status_code}")
                        logging.error(f"Error: {error.error_message}")
                    return None, "", True, user.get("user_id")
                return None, "", None, ""
            additional_connections = ",".join(map(str, connections))
            if custom_attributes and "connection" in custom_attributes and additional_connections:
                custom_attributes["connection"] += "," + additional_connections
            else:
                custom_attributes["connection"] = additional_connections

            try:
                login_ids.pop(login_ids.index(user_to_update["loginIds"][0]))
            except Exception as e:
                pass
            login_id = user_to_update["loginIds"][0]
            resp = descope_client.mgmt.user.update(
                login_id=login_id,
                email=user_to_update["email"],
                display_name=user_to_update["name"],
                given_name=given_name,
                family_name=family_name,
                phone=user_to_update["phone"],
                picture=picture,
                custom_attributes=custom_attributes,
                verified_email=user_to_update["verifiedEmail"],
                verified_phone=user_to_update["verifiedPhone"],
                additional_login_ids=login_ids,
            )
            # TODO: Handle user statuses? Yea, that's my thinking, if either are disabled, merge them, disable the merged one, print the disabled accounts that hit this scenario in the completion?
            status = "disabled" if user.get("blocked", False) else "enabled"
            if status == "disabled" or user_to_update["status"] == "disabled":
                try:
                    resp = descope_client.mgmt.user.deactivate(login_id=login_id)

                except AuthException as error:
                    logging.error(f"Unable to deactivate user.")
                    logging.error(f"Status Code: {error.status_code}")
                    logging.error(f"Error: {error.error_message}")
                return True, user.get("name"), True, user.get("user_id")
            return True, user.get("name"), False, ""
    except AuthException as error:
        logging.error(f"Unable to create user. {user}")
        logging.error(f"Error: {error.error_message}")
        return (
            False,
            "",
            False,
            user.get("user_id") + " Reason: " + error.error_message,
        )


def add_user_to_descope_role(user, role):
    """
    Add a Descope user based on matched Auth0 user data.

    Args:
    - user (str): Login ID of the user you wish to add to role
    - role (str): The name of the role which you want to add the user to
    """
    role_names = [role]

    try:
        resp = descope_client.mgmt.user.add_roles(login_id=user, role_names=role_names)
        logging.info("User role successfully added")
        return True, ""
    except AuthException as error:
        logging.error(
            f"Unable to add role to user.  Status code: {error.error_message}"
        )
        return False, f"{user} Reason: {error.error_message}"


def create_descope_tenant(organization):
    """
    Create a Descope create_descope_tenant based on matched Auth0 organization data.

    Args:
    - organization (dict): A dictionary containing organization details fetched from Auth0 API.
    """
    name = organization["display_name"]
    tenant_id = organization["id"]

    try:
        resp = descope_client.mgmt.tenant.create(name=name, id=tenant_id)
        return True, ""
    except AuthException as error:
        logging.error("Unable to create tenant.")
        logging.error(f"Error:, {error.error_message}")
        return False, f"Tenant {name} failed to create Reason: {error.error_message}"


def add_descope_user_to_tenant(tenant, loginId):
    """
    Map a descope user to a tenant based on Auth0 data using Descope SDK.

    Args:
    - tenant (string): The tenant ID of the tenant to associate the user.
    - loginId (string): the loginId of the user to associate to the tenant.
    """
    try:
        resp = descope_client.mgmt.user.add_tenant(login_id=loginId, tenant_id=tenant)
        return True, ""
    except AuthException as error:
        logging.error("Unable to add user to tenant.")
        logging.error(f"Error:, {error.error_message}")
        return False, error.error_message

def check_tenant_exists_descope(tenant_id):

    try:
        tenant_resp = descope_client.mgmt.tenant.load(tenant_id)
        return True
    except:
        return False

def check_role_exists_descope(role_name):

    try:
        roles_resp = descope_client.mgmt.role.search(role_names=[role_name])
        if roles_resp["roles"]:
            return True
        else:
            return False
    except:
        return False


### End Descope Actions:

### Begin Process Functions


def create_descope_users_batch(users_batch, verbose=False):
    """
    Create multiple users in a single batch API call to Descope.
    This dramatically reduces API calls and speeds up migration.
    
    Returns: (success_count, failed_users, merged_users, disabled_mismatch)
    """
    import time
    
    new_user_objects = []
    new_users_map = {}
    
    success_count = 0
    failed_users = []
    merged_users = []
    disabled_users_mismatch = []
    
    # Build UserObj list for batch creation (skip existence check for speed)
    for user in users_batch:
        try:
            email = user.get("email")
            if not email:
                failed_users.append(user.get('user_id', 'unknown'))
                continue
            
            login_ids = []
            connections = []
            identities = user.get("identities", [])
            
            if identities:
                for identity in identities:
                    if "Username" in identity["connection"]:
                        login_ids.append(email)
                        connections.append(identity["connection"])
                    elif "sms" in identity["connection"]:
                        login_ids.append(user.get("phone_number"))
                        connections.append(identity["connection"])
                    elif "-" in identity["connection"]:
                        login_ids.append(identity["connection"].split("-")[0] + "-" + identity["user_id"])
                        connections.append(identity["connection"])
                    else:
                        login_ids.append(identity["connection"] + "-" + identity["user_id"])
                        connections.append(identity["connection"])
            else:
                login_ids.append(email)
                connections.append("imported-from-json")
            
            if not login_ids:
                failed_users.append(email)
                continue
            
            # Build custom attributes including nickname
            custom_attrs = {
                "connection": ",".join(connections),
                "freshlyMigrated": True,
            }
            # Add nickname to custom attributes since UserObj doesn't have a nickname field
            if user.get("nickname"):
                custom_attrs["nickname"] = user.get("nickname")
            
            user_obj = UserObj(
                login_id=login_ids[0],
                email=email,
                display_name=user.get("name") or user.get("nickname") or email,
                given_name=user.get("given_name"),
                family_name=user.get("family_name"),
                phone=user.get("phone_number") if identities else None,
                picture=user.get("picture"),
                custom_attributes=custom_attrs,
                verified_email=user.get("email_verified", False),
                verified_phone=user.get("phone_verified", False) if user.get("phone_number") else False,
                additional_login_ids=login_ids[1:] if len(login_ids) > 1 else [],
            )
            new_user_objects.append(user_obj)
            new_users_map[email] = user
            
        except Exception as e:
            logging.error(f"Error preparing user {user.get('email', 'unknown')}: {e}")
            failed_users.append(user.get('email', 'unknown'))
    
    # Batch create with retry
    if new_user_objects:
        max_retries = 3
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                descope_client.mgmt.user.invite_batch(
                    users=new_user_objects,
                    invite_url="https://localhost",
                    send_mail=False,
                    send_sms=False
                )
                
                # Update status for blocked users
                for user_obj in new_user_objects:
                    try:
                        original_user = new_users_map.get(user_obj.email)
                        if original_user and original_user.get("blocked", False):
                            descope_client.mgmt.user.deactivate(login_id=user_obj.login_id)
                    except:
                        pass
                
                success_count = len(new_user_objects)
                break
                
            except AuthException as error:
                error_msg = str(error.error_message) if hasattr(error, 'error_message') else str(error)
                
                if 'E130429' in error_msg or 'rate limit' in error_msg.lower():
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = 60 * retry_count
                        print(f"  Rate limit. Waiting {wait_time}s... (retry {retry_count}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        for user_obj in new_user_objects:
                            failed_users.append(user_obj.email)
                        break
                else:
                    logging.error(f"Batch creation failed: {error_msg}")
                    for user_obj in new_user_objects:
                        failed_users.append(user_obj.email)
                    break
    
    return success_count, failed_users, merged_users, disabled_users_mismatch


def process_users(api_response_users, dry_run, from_json, verbose, batch_size=50):
    """
    Process users with TRUE batch API calls - creates 50 users per API call instead of 1.

    Args:
    - api_response_users (list): A list of users fetched from Auth0 API or JSON file.
    - batch_size (int): Number of users to create per API call (default: 50)
    """
    failed_users = []
    successful_migrated_users = 0
    merged_users = []
    disabled_users_mismatch = []
    
    # inital_custom_attributes = {"connection": "String","freshlyMigrated":"Boolean"}
    # create_custom_attributes_in_descope(inital_custom_attributes)

    if dry_run:
        print(f"Would migrate {len(api_response_users)} users from Auth0 to Descope")
        if verbose:
            for user in api_response_users:
                print(f"\tUser: {user.get('name', user.get('email', 'unknown'))}")

    else:
        if from_json:
            print(
            f"Starting migration of {len(api_response_users)} users with TRUE batch API calls (batch size: {batch_size})"
            )
        else:
            print(
            f"Starting migration of {len(api_response_users)} users found via Auth0 API with batch size {batch_size}"
            )
        
        # Process users with TRUE batch API calls
        for i in range(0, len(api_response_users), batch_size):
            batch = api_response_users[i:i + batch_size]
            
            if verbose:
                print(f"\nBatch {i//batch_size + 1}: users {i+1} to {min(i+batch_size, len(api_response_users))}")
            
            # Single API call for the entire batch!
            batch_success, batch_failed, batch_merged, batch_disabled = create_descope_users_batch(batch, verbose)
            
            successful_migrated_users += batch_success
            failed_users.extend(batch_failed)
            merged_users.extend(batch_merged)
            disabled_users_mismatch.extend(batch_disabled)
            
            # Progress update
            if (i + batch_size) % 100 == 0 or (i + batch_size) >= len(api_response_users):
                print(f"Progress: {min(i + batch_size, len(api_response_users))}/{len(api_response_users)} users processed. Success: {successful_migrated_users}")
                
    return (
        failed_users,
        successful_migrated_users,
        merged_users,
        disabled_users_mismatch,
    )


def process_roles(auth0_roles, dry_run, verbose):
    """
    Process the Auth0 organizations - creating roles, permissions, and associating users

    Args:
    - auth0_roles (dict): Dictionary of roles fetched from Auth0
    """
    failed_roles = []
    successful_migrated_roles = 0
    roles_exist_descope = 0
    total_existing_permissions_descope = []
    total_failed_permissions = []
    successful_migrated_permissions = 0
    roles_and_users = []
    failed_roles_and_users = []
    if dry_run:
        print(f"Would migrate {len(auth0_roles)} roles from Auth0 to Descope")
        if verbose:
            for role in auth0_roles:
                permissions = get_permissions_for_role(role["id"])
                print(
                    f"\tRole: {role['name']} with {len(permissions)} associated permissions"
                )
    else:
        print(f"Starting migration of {len(auth0_roles)} roles found via Auth0 API")
        for role in auth0_roles:
            permissions = get_permissions_for_role(role["id"])
            if verbose:
                print(
                    f"\tRole: {role['name']} with {len(permissions)} associated permissions"
                )
            (
                success,
                role_exists,
                success_permissions,
                existing_permissions_descope,
                failed_permissions,
                error,
            ) = create_descope_role_and_permissions(role, permissions)
            if success:
                successful_migrated_roles += 1
                successful_migrated_permissions += success_permissions
            elif role_exists:
                roles_exist_descope += 1
                successful_migrated_permissions += success_permissions
            else:
                failed_roles.append(error)
                successful_migrated_permissions += success_permissions
            if len(failed_permissions) != 0:
                for item in failed_permissions:
                    total_failed_permissions.append(item)
            if len(existing_permissions_descope) != 0:
                for item in existing_permissions_descope:
                    if item not in total_existing_permissions_descope:
                        total_existing_permissions_descope.append(item)
            users = get_users_in_role(role["id"])

            users_added = 0
            for user in users:
                success, error = add_user_to_descope_role(user["email"], role["name"])
                if success:
                    users_added += 1
                else:
                    failed_roles_and_users.append(
                        f"{user['user_id']} failed to be added to {role['name']} Reason: {error}"
                    )
            roles_and_users.append(f"Mapped {users_added} user to {role['name']}")
            if successful_migrated_roles % 10 == 0 and successful_migrated_roles > 0 and not verbose:
                print(f"Still working, migrated {successful_migrated_roles} roles.")

    return (
        failed_roles,
        successful_migrated_roles,
        roles_exist_descope,
        total_failed_permissions,
        successful_migrated_permissions,
        total_existing_permissions_descope,
        roles_and_users,
        failed_roles_and_users,
    )


def process_auth0_organizations(auth0_organizations, dry_run, verbose):
    """
    Process the Auth0 organizations - creating tenants and associating users

    Args:
    - auth0_organizations (dict): Dictionary of organizations fetched from Auth0
    """
    successful_tenant_creation = 0
    tenant_exists_descope = 0
    failed_tenant_creation = []
    failed_users_added_tenants = []
    tenant_users = []
    if dry_run:
        print(
            f"Would migrate {len(auth0_organizations)} organizations from Auth0 to Descope"
        )
        if verbose:
            for organization in auth0_organizations:
                org_members = fetch_auth0_organization_members(organization["id"])
                print(
                    f"\tOrganization: {organization['display_name']} with {len(org_members)} associated users"
                )
    else:
        print(f"Starting migration of {len(auth0_organizations)} organizations found via Auth0 API")
        for organization in auth0_organizations:
            
            if not check_tenant_exists_descope(organization["id"]):
                success, error = create_descope_tenant(organization)
                if success:
                    successful_tenant_creation += 1
                else:
                    failed_tenant_creation.append(error)
            else:
                tenant_exists_descope += 1
                    

            org_members = fetch_auth0_organization_members(organization["id"])
            if verbose:
                print(f"\tOrganization: {organization['display_name']} with {len(org_members)} associated users")
            users_added = 0
            for user in org_members:
                success, error = add_descope_user_to_tenant(
                    organization["id"], user["email"]
                )
                if success:
                    users_added += 1
                else:
                    failed_users_added_tenants.append(
                        f"User {user['email']} failed to be added to tenant {organization['display_name']} Reason: {error}"
                    )
            tenant_users.append(
                f"Associated {users_added} users with tenant: {organization['display_name']} "
            )
            if successful_tenant_creation % 10 == 0 and successful_tenant_creation > 0 and not verbose:
                print(f"Still working, migrated {successful_tenant_creation} organizations.")
    return (
        successful_tenant_creation,
        tenant_exists_descope,
        failed_tenant_creation,
        failed_users_added_tenants,
        tenant_users,
    )

### End Process Functions

### Password Functions


def read_auth0_export(file_path):
    """
    Read and parse the Auth0 export file formatted as NDJSON.

    Args:
    - file_path (str): The path to the Auth0 export file.

    Returns:
    - list: A list of parsed Auth0 user data.
    """
    with open(file_path, "r") as file:
        data = [json.loads(line) for line in file if line.strip()]
    return data

def process_users_with_passwords(file_path, dry_run, verbose, batch_size=50):
    users = read_auth0_export(file_path)
    successful_password_users = 0
    failed_password_users = []

    if dry_run:
        print(
            f"Would migrate {len(users)} users from Auth0 with Passwords to Descope"
        )
        if verbose:
            for user in users:
                print(f"\tuser: {user.get('email', 'unknown')}")

    else:
        print(
            f"Starting migration of {len(users)} users from Auth0 password file with batch size {batch_size}"
        )
        
        # Process users in batches
        for i in range(0, len(users), batch_size):
            batch = users[i:i + batch_size]
            user_objects = []
            
            for user in batch:
                try:
                    login_ids = []
                    connections = []
                    identities = user.get("identities", [])
                    email = user.get('email', '')
                
                    
                    if identities:
                        for identity in identities:
                            if "type" in identity and identity["type"] == "email":
                                login_ids.append(email)
                                connections.append(identity["type"])
                                connections.append(identity["connection"])
                            elif "sms" in identity["connection"]:
                                login_ids.append(user.get("phone_number"))
                                connections.append(identity["connection"])
                            elif "-" in identity["connection"]:
                                login_ids.append(identity["connection"].split("-")[0] + "-" + identity["user_id"])
                                connections.append(identity["connection"])
                            else:
                                login_ids.append(identity["connection"] + "-" + identity["user_id"])
                                connections.append(identity["connection"])
                    else:
                        login_ids.append(email)
                        connections.append("imported-from-json")
                    


                    extracted_user = {
                        'email_verified': user.get('email_verified', False),
                        'email': user.get('email', ''),
                        'connection': user.get('connection', ''),
                        'passwordHash': user.get('passwordHash', ''),
                        "user_id": user.get("Id") or user.get("user_id"),
                        "email": user.get("Email") or user.get("email"),
                        "email_verified": user.get("Email Verified") or user.get("email_verified", False),
                        "name": user.get("Name") or user.get("name", ""),
                        "given_name": user.get("Given Name") or user.get("given_name", ""),
                        "family_name": user.get("Family Name") or user.get("family_name", ""),
                        "nickname": user.get("Nickname") or user.get("nickname", ""),
                        "picture": user.get("Picture") or user.get("picture", ""),
                        "created_at": user.get("Created At") or user.get("created_at", ""),
                        "updated_at": user.get("Updated At") or user.get("updated_at", ""),
                    }
                    if extracted_user['email']:
                        user_obj = build_user_object_with_passwords(extracted_user)
                        user_objects.extend(user_obj)  # user_obj is already a list
                    else:
                        user_obj = build_user_object_with_passwords(extracted_user)
                        logging.warning(f"Skipping user with missing email or password: {user}")
                        failed_password_users.append(extracted_user['email'] or 'unknown')
                except Exception as e:
                    logging.error(f"Error preparing user {user.get('email', 'unknown')}: {e}")
                    failed_password_users.append(user.get('email', 'unknown'))
            
            # Create batch of users
            if user_objects:
                success_count, failed_list = create_users_with_passwords_batch(user_objects)
                successful_password_users += success_count
                failed_password_users.extend(failed_list)
                
                if (i + batch_size) % 100 == 0 or (i + batch_size) >= len(users):
                    print(f"Progress: {min(i + batch_size, len(users))}/{len(users)} users processed")
                    
    return len(users), successful_password_users, failed_password_users


def build_user_object_with_passwords(extracted_user):
    if not extracted_user['passwordHash']:
        logging.warning(f"Migrating user without password hash: {extracted_user['email']}")
        return [
            UserObj(
                login_id=extracted_user['email'],
                email=extracted_user['email'],
                verified_email=True,#extracted_user['email_verified'],
                custom_attributes = {
                    "connection": "Username-Password-Authentication", #database name
                    "freshlyMigrated": True,
                },
                phone=extracted_user.get('phone_number'),
                display_name=extracted_user.get('name') or extracted_user.get('nickname') or extracted_user['email'],
                given_name=extracted_user.get('given_name'),
                family_name=extracted_user.get('family_name'),
                picture=extracted_user.get('picture'),
                additional_login_ids=[],
            )
        ]

    #else
    userPasswordToCreate=UserPassword(
        hashed=UserPasswordBcrypt(
            hash=extracted_user['passwordHash']
        )
    )
    user_object=[
        UserObj(
            login_id=extracted_user['email'],
            email=extracted_user['email'],
            verified_email=True,#extracted_user['email_verified'],
            password=userPasswordToCreate,
            custom_attributes = {
                "connection": "Username-Password-Authentication", #database name
                "freshlyMigrated": True,
            },
            phone=extracted_user.get('phone_number'),
            display_name=extracted_user.get('name') or extracted_user.get('nickname') or extracted_user['email'],
            given_name=extracted_user.get('given_name'),
            family_name=extracted_user.get('family_name'),
            picture=extracted_user.get('picture'),
            additional_login_ids=[],
        )
    ]
    return user_object

def create_users_with_passwords(user_object):
    # Create the user (kept for backward compatibility)
    try:
        resp = descope_client.mgmt.user.invite_batch(
            users=user_object,
            invite_url="https://localhost",
            send_mail=False,
            send_sms=False
        )
        return True
    except AuthException as error:
        logging.error("Unable to create user with password.")
        logging.error(f"Error:, {error.error_message}")
        return False

def create_users_with_passwords_batch(user_objects, max_retries=3):
    """
    Create multiple users with passwords in batch with rate limit handling.
    
    Args:
    - user_objects (list): List of UserObj to create
    - max_retries (int): Maximum number of retries on rate limit
    
    Returns:
    - success_count (int): Number of successfully created users
    - failed_users (list): List of email addresses that failed
    """
    import time
    
    success_count = 0
    failed_users = []
    retry_count = 0
    
    while retry_count <= max_retries:
        try:
            resp = descope_client.mgmt.user.invite_batch(
                users=user_objects,
                invite_url="https://localhost",
                send_mail=False,
                send_sms=False
            )
            success_count = len(user_objects)
            return success_count, failed_users
            
        except AuthException as error:
            error_msg = str(error.error_message) if hasattr(error, 'error_message') else str(error)
            
            # Check if it's a rate limit error
            if 'E130429' in error_msg or 'rate limit' in error_msg.lower():
                retry_count += 1
                if retry_count <= max_retries:
                    # Extract retry-after time or use exponential backoff
                    wait_time = 60 * retry_count  # Exponential backoff: 60, 120, 180 seconds
                    logging.warning(f"Rate limit hit. Waiting {wait_time} seconds before retry {retry_count}/{max_retries}")
                    print(f"Rate limit reached. Waiting {wait_time} seconds... (retry {retry_count}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logging.error(f"Max retries reached. Failed to create batch of {len(user_objects)} users")
                    for user_obj in user_objects:
                        failed_users.append(user_obj.email)
                    return success_count, failed_users
            else:
                # Non-rate-limit error - fail the batch
                logging.error(f"Unable to create user batch: {error_msg}")
                for user_obj in user_objects:
                    failed_users.append(user_obj.email)
                return success_count, failed_users
    
    return success_count, failed_users
    
def create_custom_attributes_in_descope(custom_attr_dict):
    """
    Creates custom attributes in Descope

    Args:
    - custom_attr_dict: Dictionary of custom attribute names and assosciated data types {"name" : dataType, ...} 
    """

    type_mapping = {
        'String': 1,
        'Number': 2,
        'Boolean': 3
    }
  
    # Takes indivdual custom attribute and makes a json body for create attribute post request
    custom_attr_post_body = []
    for custom_attr_name, custom_attr_type in custom_attr_dict.items():
        custom_attr_body = {
            "name": custom_attr_name,
            "type": type_mapping.get(custom_attr_type, 1), # Default to 0 if type not found
            "options": [],
            "displayName": custom_attr_name,
            "defaultValue": {},
            "viewPermissions": [],
            "editPermissions": [],
            "editable": True
        }
        custom_attr_post_body.append(custom_attr_body)

    # Combine all custom attribute post request bodies into one
    # Request for custom attributes to be created using a post request
    try:
        endpoint = "https://api.descope.com/v1/mgmt/user/customattribute/create"
        data = {"attributes":custom_attr_post_body}
        headers = {
            "Authorization": f"Bearer {DESCOPE_PROJECT_ID}:{DESCOPE_MANAGEMENT_KEY}",
            "Content-Type": "application/json"
            }
        response = api_request_with_retry(
            action="post",
            url=endpoint,
            headers=headers,
            data=json.dumps(data)
            )
        
        if response.ok:
            logging.info(f"Custom attributes successfully created in Descope")
        else: 
            response.raise_for_status()

    except requests.HTTPError as e:
        error_dict = {
            "status_code":e.response.status_code,
            "error_reason":e.response.reason,
            "error_message":e.response.text
            }
        logging.error(f"Failed to create custom Attributes: {str(error_dict)}")

# def fetch_auth0_password_user(email):
#     """
#     Fetch and parse Auth0 users from the provided endpoint.

#     Returns:
#     - all_users (Dict): A list of parsed Auth0 users if successful, empty list otherwise.
#     """
#     headers = {"Authorization": f"Bearer {AUTH0_TOKEN}", "Accept": "application/json"}
#     page = 0
#     per_page = 20
#     user = []
#     response = api_request_with_retry(
#         "get",
#         f"https://{AUTH0_TENANT_ID}.au.auth0.com/api/v2/users-by-email?email=chris%40wa9pie.net",
#         headers=headers,
#     )
#     if response.status_code != 200:
#         logging.error(
#             f"Error fetching Auth0 users. Status code: {response.status_code}"
#         )
#         return False
#     return response.json()

### End Password Functions