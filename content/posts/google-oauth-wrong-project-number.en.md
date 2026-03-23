---
title: "When Google OAuth Client ID Project Number Differs from Firebase Project Number"
date: 2025-06-15
draft: true
tags: ["Google OAuth", "Firebase", "GCP", "Troubleshooting"]
description: "Experience where the Google OAuth Client ID stored in .env had a different project number from the Firebase project, causing secret lookup failures."
cover:
  image: "/images/og/google-oauth-wrong-project-number.png"
  alt: "Google Oauth Wrong Project Number"
  hidden: true
---

Here is a case where I was trying to reconfigure Google OAuth in a new environment, but the project number in the stored Client ID did not match the Firebase project number, making it impossible to find the secret.

---

## Situation

The `.env` file contained the following:

```
GOOGLE_CLIENT_ID=1091056260493-xxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=   # empty
```

Checking the Firebase console, the actual project number for the app was `333977052282`.

The leading number in a Google OAuth Client ID is the **GCP project number**. So a project with the number `1091056260493` should exist somewhere, but checking the gcloud account revealed no project with that number.

In this situation, most developers find themselves asking: "The Client ID exists, so why can't I find the Secret?" The error message typically looks like this:

```
Error 401: invalid_client
The OAuth client was not found.
```

Or, in a Rails app using Devise with OmniAuth:

```
OmniAuth::Strategies::OAuth2::CallbackError
invalid_client: The OAuth client was not found.
```

Because the Client ID appears to exist, it is easy to initially assume the Secret is wrong, or that there is an issue with how `.env` variables are being loaded. But the real problem is that **the Client ID itself belongs to a project that is no longer accessible from the current account**.

---

## Understanding GCP Project Numbers

When you create a project in Google Cloud, three identifiers are assigned:

| Identifier | Example | Notes |
|------------|---------|-------|
| Project ID | `my-app-2025` | Human-readable unique string, cannot be changed |
| Project Number | `333977052282` | System-assigned unique integer, cannot be changed |
| Project Name | `My App` | Display label, can be changed |

When you create an OAuth client, it is issued a Client ID in the format `{project-number}-{random-string}.apps.googleusercontent.com`. This means that just by looking at the number at the front of a Client ID, you can immediately tell **which GCP project the OAuth client belongs to**.

A Firebase project is a layer that runs on top of a GCP project. The "Project number" shown in Firebase Console under Project Settings is identical to the **GCP project number** of the underlying project.

---

## Root Cause Analysis

```bash
# Check all projects accessible from the current gcloud account
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://cloudresourcemanager.googleapis.com/v1/projects" | \
  python3 -c "import sys,json; [print(p['projectNumber'], p['projectId']) for p in json.load(sys.stdin)['projects']]"
```

Confirmed that no project with the number `1091056260493` exists in the results.

Possible causes:
- Created under a different Google account in the past
- The project was deleted
- An OAuth client created for a different purpose and left abandoned

When you work on multiple projects over time, it is common to create and delete test GCP projects. It is also common in team settings to copy an OAuth Client ID configured under a colleague's account directly into `.env`, then have that colleague leave the team or have the original project deleted.

---

## Step-by-Step Debugging

### Step 1: Extract the Project Number from the Client ID

Extract the project number from the Client ID.

```bash
# Check Client ID in .env
grep GOOGLE_CLIENT_ID .env

# Extract only the leading number
echo "1091056260493-xxxxxxxx.apps.googleusercontent.com" | cut -d'-' -f1
# Output: 1091056260493
```

### Step 2: Confirm the Firebase Project Number

Check the "Project number" in Firebase Console under Project Settings > General. Alternatively, use the CLI:

```bash
# If firebase-tools is installed
firebase projects:list

# Or with gcloud
gcloud projects list --format="table(projectNumber, projectId, name)"
```

### Step 3: Compare the Two Numbers

```bash
CLIENT_PROJECT_NUM=$(grep GOOGLE_CLIENT_ID .env | cut -d'=' -f2 | cut -d'-' -f1)
FIREBASE_PROJECT_NUM="333977052282"  # confirmed from Firebase Console

if [ "$CLIENT_PROJECT_NUM" = "$FIREBASE_PROJECT_NUM" ]; then
  echo "Match: OAuth client from the same project"
else
  echo "Mismatch: Client ID=$CLIENT_PROJECT_NUM, Firebase=$FIREBASE_PROJECT_NUM"
  echo "A new OAuth client must be created"
fi
```

### Step 4: Verify Whether the Project Exists

```bash
# Query a project by its specific project number
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://cloudresourcemanager.googleapis.com/v1/projects/1091056260493" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('projectId', 'NOT FOUND'))"
```

If the project does not exist or you do not have access, you will receive `NOT FOUND` or a 403 error.

---

## Solution: Create a New Client in the Correct Project

Created a new OAuth client in the GCP project corresponding to the actual Firebase project number (`333977052282`).

**Google Cloud Console -> APIs & Services -> Credentials -> Create OAuth client ID**

- Application type: Web application
- Name: Any name
- Authorized redirect URIs: enter the actual callback URL in use

Result:
```
Client ID: 333977052282-xxxxxxxxx.apps.googleusercontent.com
Client Secret: GOCSPX-xxxxxxxxxxxxxxxx
```

The leading number (`333977052282`) matches the Firebase project number.

After creation, update `.env`:
```bash
GOOGLE_CLIENT_ID=333977052282-xxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
```

---

## Relationship Between OAuth Client and Firebase Project

A Firebase project runs internally on top of a GCP project. The **project number visible in Firebase console = GCP project number**.

When creating an OAuth client, the number at the beginning of the Client ID depends on which GCP project it is created in. If the OAuth client is intended to integrate with a Firebase app, it **must be created in the same Firebase/GCP project**.

```
Firebase project: my-app (project number: 333977052282)
                    | Must be created in the same project
OAuth Client ID: 333977052282-xxxxx.apps.googleusercontent.com
```

Why does this matter? During the OAuth authentication flow, when Google's servers receive a Client ID, they look up the configuration for that project. Allowed redirect URIs, app name, scopes, and consent screen settings are all stored in that project. If the Client ID belongs to a project that has been deleted or is otherwise inaccessible, Google's servers return an `invalid_client` error.

This is also why having the correct Client ID is not enough on its own. The project that issued the Client ID must still exist and must be accessible to the service account or user initiating the OAuth flow.

---

## Finding JSON Files in the Downloads Folder

If previously downloaded OAuth client JSON files exist, the filename contains the Client ID.

```bash
ls ~/Downloads/client_secret_*.json
# client_secret_333977052282-xxxxx.apps.googleusercontent.com.json
```

Check whether the leading number in the filename matches the current Firebase project number.

You can also inspect the file contents directly:

```bash
cat ~/Downloads/client_secret_*.json | python3 -c "
import sys, json
data = json.load(sys.stdin)
web = data.get('web', {})
print('client_id:', web.get('client_id'))
print('project_id:', web.get('project_id'))
"
```

If you find a JSON file from the correct project this way, you can reuse it without creating a new client.

---

## Prevention Tips

**1. Add project number comments to your `.env` file**

```bash
# Firebase project: my-app (project number: 333977052282)
GOOGLE_CLIENT_ID=333977052282-xxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
```

Explicitly noting the Firebase project number alongside the Client ID in a comment makes it immediately obvious if there is a mismatch when reconfiguring later.

**2. Maintain consistent project naming**

Set the GCP project ID and Firebase project ID to be the same, or use a recognizable prefix to indicate that they are related. For example: `my-app-prod`, `my-app-staging`.

**3. Verify the active project before creating an OAuth client**

Before creating a new OAuth client, always confirm that the currently selected GCP project is the same as the Firebase project.

```bash
# Check the currently selected project
gcloud config get-value project

# Verify it matches the Firebase project ID
firebase use
```

**4. Periodically audit long-lived `.env` files**

In long-running projects, the values set early in development often persist unchanged. This is especially true in team settings where membership changes or the GCP project structure is reorganized. It is worth periodically verifying that OAuth clients referenced in `.env` still belong to an accessible, active project.

---

## Key Takeaways

- **The leading number in a Google OAuth Client ID is the GCP project number.** From this number alone you can immediately identify which project the OAuth client belongs to.
- **The Firebase project number equals the GCP project number of the underlying GCP project.** Firebase and GCP are two different consoles looking at the same project.
- **If the two numbers differ, you are using an OAuth client from the wrong project.** This is one of the most common root causes of the `invalid_client` error.
- **If the Secret is nowhere to be found**, first suspect that the Client ID itself belongs to a project that is no longer accessible, rather than assuming a `.env` loading issue or a typo in the Secret.
- **The fix is straightforward**: create a new OAuth client in the GCP project that corresponds to your Firebase project, then update `.env` with the new Client ID and Secret.
- **Downloaded JSON files in your Downloads folder can be a lifesaver.** If a file from the correct project was downloaded in the past, it can be reused without creating a new client from scratch.
