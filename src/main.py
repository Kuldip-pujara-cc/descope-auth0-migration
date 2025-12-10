from migration_utils import fetch_auth0_users, process_users, fetch_auth0_roles, process_roles, fetch_auth0_organizations, process_auth0_organizations, process_users_with_passwords, fetch_auth0_users_from_file
import sys
import argparse
import json


def main():
    """
    Main function to process Auth0 users, roles, permissions, and organizations, creating and mapping them together within your Descope project.
    """
    dry_run = False
    verbose = False
    with_passwords = False
    passwords_file_path = ""
    from_json = False
    json_file_path = ""
    batch_size = 50  # Default batch size
    
    
    parser = argparse.ArgumentParser(description='This is a program to assist you in the migration of your users, roles, permissions, and organizations to Descope.')
    parser.add_argument('--dry-run', action='store_true', help='Enable dry run mode')
    parser.add_argument('--verbose','-v', action='store_true',help='Enable verbose printing for live runs and dry runs')
    parser.add_argument('--with-passwords', nargs=1, metavar='file-path', help='Run the script with passwords from the specified file')
    parser.add_argument('--from-json', nargs=1, metavar='file-path', help='Run the script with users from the specified file rather than API')
    parser.add_argument('--skip-roles', action='store_true', help='Skip roles and permissions migration')
    parser.add_argument('--skip-orgs', action='store_true', help='Skip organizations/tenants migration')
    parser.add_argument('--batch-size', type=int, default=50, help='Number of users to process in each batch (default: 50)')
    
    args = parser.parse_args()

    if args.dry_run:
        dry_run=True
    
    if args.verbose:
        verbose = True

    if args.batch_size:
        batch_size = args.batch_size
        print(f"Using batch size: {batch_size}")

    skip_roles = False
    skip_orgs = False
    
    if args.skip_roles:
        skip_roles = True
        print("Skipping roles and permissions migration")
    
    if args.skip_orgs:
        skip_orgs = True
        print("Skipping organizations/tenants migration")
    
    if args.with_passwords:
        passwords_file_path = args.with_passwords[0]
        with_passwords = True
        print(f"Running with passwords from file: {passwords_file_path}")

    if with_passwords:
        found_password_users, successful_password_users, failed_password_users = process_users_with_passwords(passwords_file_path, dry_run, verbose, batch_size)
    
    if args.from_json:
        json_file_path = args.from_json[0]
        from_json=True

    # Fetch and Create Users
    if from_json == False:
        auth0_users = fetch_auth0_users()
    else:
        auth0_users = fetch_auth0_users_from_file(json_file_path)
        
    
    failed_users, successful_migrated_users, merged_users, disabled_users_mismatch = process_users(auth0_users, dry_run, from_json, verbose, batch_size)

    # Fetch, create, and associate users with roles and permissions
    if not skip_roles:
        auth0_roles = fetch_auth0_roles()
        failed_roles, successful_migrated_roles, roles_exist_descope, total_failed_permissions, successful_migrated_permissions, total_existing_permissions_descope, roles_and_users, failed_roles_and_users = process_roles(auth0_roles, dry_run, verbose)

    # Fetch, create, and associate users with Organizations
    if not skip_orgs:
        auth0_organizations = fetch_auth0_organizations()
        successful_tenant_creation, tenant_exists_descope, failed_tenant_creation, failed_users_added_tenants, tenant_users = process_auth0_organizations(auth0_organizations, dry_run, verbose)
    
    if dry_run == False:
        print("\n=== Migration Summary ===")
        print(f"Total users migrated: {successful_migrated_users}")
        print(f"Failed users: {len(failed_users)}")
        if with_passwords:
            print(f"Users with passwords: {successful_password_users}/{found_password_users}")
        if not skip_roles:
            print(f"Roles migrated: {successful_migrated_roles}")
        if not skip_orgs:
            print(f"Organizations migrated: {successful_tenant_creation}")

if __name__ == "__main__":
    main()
