<img width="1400" alt="Descope Auth0 Migration Tool" src="https://github.com/descope/descope-auth0-migration/assets/32936811/992ee6e4-682c-4659-b333-f1d32c16258f">

# Descope Auth0 User Migration Tool

This repository includes a Python utility for migrating your Auth0 users, organizations, permissions, and roles to Descope.

This utility allows you to migrate users by loading them from the Auth0 API, and optionally, you can load users' passwords from the exported password file received from Auth0.

## Setup 💿

1. (Optional) To export hashed password from Auth0, open a [ticket](https://support.auth0.com/tickets) with Auth0 support to
   request an export of your user's password hashes.

2. Clone the Repo:

```
git clone git@github.com:descope/descope-auth0-migration.git
```

3. Create a Virtual Environment

```
python3 -m venv venv
source venv/bin/activate
```

4. Install the Necessary Python libraries

```
pip3 install -r requirements.txt
```

5. Setup Your Environment Variables

You can change the name of the `.env.example` file to `.env` to use as a template.

```env
AUTH0_TOKEN=Your_Auth0_Token
AUTH0_TENANT_ID=Your_Auth0_Tenant_ID
DESCOPE_PROJECT_ID=Your_Descope_Project_ID
DESCOPE_MANAGEMENT_KEY=Your_Descope_Management_Key
DESCOPE_BASE_URL=Your_Descope_Base_URL
```

**a. AUTH0_TOKEN** (Required)

To get an Auth0 token, go [here](https://manage.auth0.com/#/apis/management/explorer), then copy the token to your `.env` file. These tokens are only valid for 24 hours by default.

**b. AUTH0_TENANT_ID** (Required)

Your Auth0 Tenant ID can be found in the URL of your Auth0 dashboard. For example, when you login to Auth0, your URL might look something like this:

```
https://manage.auth0.com/dashboard/us/dev-xyz/
```

Your tenant ID is: `dev-xyz`. You can also read more about it [here](https://auth0.com/docs/get-started/tenant-settings/find-your-tenant-name-or-tenant-id).

**c. DESCOPE_PROJECT_ID** (Required)

To get your Descope Project ID, go [here](https://app.descope.com/settings/project), then copy the project ID to your `.env` file.

**d. DESCOPE_MANAGEMENT_KEY** (Required)

To create a Descope Management Key, go [here](https://app.descope.com/settings/company/managementkeys), then copy the token to your `.env` file.

**e. DESCOPE_BASE_URL** (Required)

Set the base URL based on your Descope project's region:

- **US Region**: `https://api.descope.com/v1` (or `https://CNAME.descope.com/v1` if using a custom domain)
- **EU Region**: `https://euc1.descope.com/v1` (or `https://CNAME.euc1.descope.com/v1` if using a custom domain)
- **AU Region**: `https://api.aps2.descope.com/v1` (or `https://CNAME.aps2.descope.com/v1` if using a custom domain)

Example for AU Region:
```env
DESCOPE_BASE_URL=https://api.aps2.descope.com/v1
```

6. The tool depends on a few custom user attributes that will automatically be created for you. The below outlines the machine names of the attributes created within the [user's custom attributes](https://app.descope.com/users/attributes) section of the Descope console.

- `connection` (type: text): This custom attribute will contain the different connection types associated to the user which was
  migrated from Auth0.
- `freshlyMigrated` (type: Boolean): This custom attribute will be set to true during the migration. This allows for you
  to later check this via a conditional during Descope flow execution.

Once you've set all of that up, you're ready to run the script.

## Running the Migration Script 🚀

### Options

You can run the script to capture the users from the Auth0 database via API, or you can utilize it to fetch users from an exported file.

The below options show the example commands for fetching users from the Auth0 database via API; however, there is a 1000 user limitation from the Auth0 user API. So it is recommended to export a JSON of users if you have more than 1000 users. In order to export the JSON, follow [these steps](https://auth0.com/docs/customize/extensions/user-import-export-extension#export-users).

### Command-Line Arguments

- `--from-json <file-path>`: Load users from a JSON file instead of the Auth0 API
- `--with-passwords <file-path>`: Include password hashes from the specified file
- `--dry-run`: Run in simulation mode without making actual changes
- `--verbose` or `-v`: Enable detailed output during migration
- `--batch-size <number>`: Set the number of users to process per batch (default: 50, recommended: 50-100)
- `--skip-roles`: Skip roles and permissions migration
- `--skip-orgs`: Skip organizations/tenants migration

### Preparing Your Data Files

Before running the migration, you need to prepare your JSON files:

1. **Create a json folder** (if it doesn't exist):
   ```bash
   mkdir -p json
   ```

2. **Place your exported JSON files** in the `json/` folder:
   - `export_user.json` - Your exported users from Auth0
   - `with_password_user.json` - Password hashes from Auth0 (if available)

3. **Combine both JSON files** (if you have passwords):
   
   Run the following command to merge `export_user.json` and `with_password_user.json`:
   ```bash
   jq -c --slurpfile file2 json/export_user.json '. as $item | $item + {passwordHash: $file2[]|select(.email==$item.Email).passwordHash} // $item' json/with_password_user.json > json/combined.json
   ```

4. **Create a blank.json file**:
   
   Create an empty JSON file (used when migrating only password users):
   ```bash
   touch json/blank.json
   ```

5. **Run the migration**:
   ```bash
   python3 src/main.py --from-json json/blank.json --with-passwords json/combined.json --batch-size 100
   ```

### Examples

**Dry run with passwords:**
```bash
python3 src/main.py --from-json ./path_to_user_export.json --with-passwords ./path_to_exported_password_users_file.json --dry-run
```

**Dry run without passwords:**
```bash
python3 src/main.py --from-json ./path_to_user_export.json --dry-run
```

**Live run with passwords and custom batch size:**
```bash
python3 src/main.py --from-json ./path_to_user_export.json --with-passwords ./path_to_exported_password_users_file.json --batch-size 100
```

**Live run without passwords:**
```bash
python3 src/main.py --from-json ./path_to_user_export.json
```

**Live run from API (up to 1000 users):**
```bash
python3 src/main.py
```

**Verbose output with custom batch size:**
```bash
python3 src/main.py --from-json ./path_to_user_export.json --verbose --batch-size 75
```

**Skip roles and organizations:**
```bash
python3 src/main.py --from-json ./path_to_user_export.json --skip-roles --skip-orgs
```

### Batch Processing

The migration tool uses batch API calls for improved performance. By default, users are processed in batches of 50. You can adjust this using the `--batch-size` parameter:

- **Smaller batches (10-25)**: More stable but slower
- **Medium batches (50-75)**: Balanced performance (recommended)
- **Larger batches (100+)**: Faster but may hit rate limits

The tool automatically retries on rate limit errors, so larger batch sizes can significantly speed up migration for large user bases.

### Dry run

You can dry run the migration script which will allow you to see the number of users, tenants, roles, etc which will be migrated
from Auth0 to Descope.

#### With Passwords

```
python3 src/main.py --dry-run --with-passwords ./path_to_exported_password_users_file.json
```

The output would appear similar to the following:

```
Using batch size: 50
Running with passwords from file: ./path_to_exported_users_file.json
Would migrate 2 users from Auth0 with Passwords to Descope
Would migrate 112 users from Auth0 to Descope
Would migrate 2 roles from Auth0 to Descope
Would migrate MyNewRole with 2 associated permissions.
Would migrate Role with 0 associated permissions.
Would migrate 2 organizations from Auth0 to Descope
Would migrate Tenant 1 with 5 associated users.
Would migrate Tenant 2 with 4 associated users.
```

#### Without Passwords

```
python3 src/main.py --dry-run
```

The output would appear similar to the following:

```
Would migrate 112 users from Auth0 to Descope
Would migrate 2 roles from Auth0 to Descope
Would migrate MyNewRole with 2 associated permissions.
Would migrate Role with 0 associated permissions.
Would migrate 2 organizations from Auth0 to Descope
Would migrate Tenant 1 with 5 associated users.
Would migrate Tenant 2 with 4 associated users.
```

### Live run

#### With Passwords

To migrate your Auth0 users, simply run the following command:

```bash
python3 src/main.py --with-passwords ./path_to_exported_password_users_file.json --batch-size 100
```

The output will include the responses of the created users, organizations, roles, and permissions as well as the mapping between the various objects within Descope. A log file will also be generated in the format of `migration_log_%d_%m_%Y_%H:%M:%S.log`. Any items which failed to be migrated will also be listed with the error that occurred during the migration.

```
Using batch size: 100
Running with passwords from file: ./path_to_exported_users_file.json
Starting migration of 2 users from Auth0 password file
Progress: Batch 1/1 processing 2 users
Batch creation successful: 2 users created
Starting migration of 112 users with TRUE batch API calls (batch size: 100)

Batch 1: users 1 to 100
Progress: 100/112 users processed. Success: 100

Batch 2: users 101 to 112
Progress: 112/112 users processed. Success: 110
Starting migration of 2 roles found via Auth0 API
Starting migration of MyNewRole with 2 associated permissions.
Starting migration of Role with 0 associated permissions.

=== Migration Summary ===
Total users migrated: 110
Failed users: 2
Users with passwords: 2/2
Roles migrated: 2
Organizations migrated: 2
```


#### Without Passwords

To migrate your Auth0 users, simply run the following command:

```bash
python3 src/main.py
```

The output will include the responses of the created users, organizations, roles, and permissions as well as the mapping between the various objects within Descope. A log file will also be generated in the format of `migration_log_%d_%m_%Y_%H:%M:%S.log`. Any items which failed to be migrated will also be listed with the error that occurred during the migration.

```
Using batch size: 50
Starting migration of 112 users found via Auth0 API with batch size 50

Batch 1: users 1 to 50
Progress: 50/112 users processed. Success: 50

Batch 2: users 51 to 100
Progress: 100/112 users processed. Success: 100

Batch 3: users 101 to 112
Progress: 112/112 users processed. Success: 110

Starting migration of 2 roles found via Auth0 API
Starting migration of MyNewRole with 2 associated permissions.
Starting migration of Role with 0 associated permissions.

=== Migration Summary ===
Total users migrated: 110
Failed users: 2
Roles migrated: 2
Organizations migrated: 2
```

### Performance Optimization

The migration tool uses batch API calls to significantly improve migration speed:

- **Batch Processing**: Users are created in batches (default: 50 users per API call)
- **Automatic Retry**: Built-in retry logic handles rate limits automatically
- **Progress Tracking**: Real-time progress updates during migration
- **Customizable Batch Size**: Adjust batch size based on your needs and API limits

For large user bases (10,000+ users), using `--batch-size 100` can reduce migration time by up to 90% compared to individual user creation.

### Post Migration Verification

Once the migration tool has ran successfully, you can check the [users](https://app.descope.com/users),
[roles](https://app.descope.com/authorization), [permissions](https://app.descope.com/authorization/permissions),
and [tenants](https://app.descope.com/tenants) for the migrated items from Auth0. You can verify the created items
based on the output of the migration tool.

The migration log file (`migration_log_*.log` in the `logs/` directory) contains detailed information about:
- Successfully migrated users
- Failed migrations with specific error messages
- Merged user accounts
- Disabled user accounts
- API retry attempts and rate limit handling

## Testing 🧪

Unit testing can be performed by running the following command:

```
python3 -m unittest tests.test_migration
```

## Issue Reporting ⚠️

For any issues or suggestions, feel free to open an issue in the GitHub repository.

## License 📜

This project is licensed under the MIT License - see the LICENSE file for details.
