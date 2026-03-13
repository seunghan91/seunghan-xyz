---
title: "When Google OAuth Client ID Project Number Differs from Firebase Project Number"
date: 2025-06-15
draft: false
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

---

## Root Cause

```bash
# Check all project list
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://cloudresourcemanager.googleapis.com/v1/projects" | \
  python3 -c "import sys,json; [print(p['projectNumber'], p['projectId']) for p in json.load(sys.stdin)['projects']]"
```

Confirmed that no project with the number `1091056260493` exists in the results.

Possible causes:
- Created in a different Google account in the past
- The project was deleted
- An OAuth client created for a different purpose and left abandoned

---

## Solution: Create New in the Correct Project

Created a new OAuth client in the GCP project corresponding to the actual Firebase project number (`333977052282`).

**Google Cloud Console -> APIs & Services -> Credentials -> Create OAuth client ID**

- Application type: Web application
- Name: Any name

Result:
```
Client ID: 333977052282-xxxxxxxxx.apps.googleusercontent.com
Client Secret: GOCSPX-xxxxxxxxxxxxxxxx
```

The leading number (`333977052282`) matches the Firebase project number.

---

## Relationship Between OAuth Client and Firebase Project

A Firebase project runs internally on top of a GCP project. The **project number visible in Firebase console = GCP project number**.

When creating an OAuth client, the number at the beginning of the Client ID depends on which GCP project it is created in. If the OAuth client is intended to integrate with a Firebase app, it **must be created in the same Firebase/GCP project**.

```
Firebase project: my-app (project number: 333977052282)
                    | Must be created in the same project
OAuth Client ID: 333977052282-xxxxx.apps.googleusercontent.com
```

---

## Finding JSON Files in the Downloads Folder

If previously downloaded OAuth client JSON files exist, the filename contains the Client ID.

```bash
ls ~/Downloads/client_secret_*.json
# client_secret_333977052282-xxxxx.apps.googleusercontent.com.json
```

Check whether the leading number in the filename matches the current Firebase project number.

---

## Summary

- The leading number in a Google OAuth Client ID = GCP project number
- Firebase project number = the GCP project number of that Firebase app
- If the two differ, the OAuth client was created in a different project
- If the Client ID in `.env` differs from the current Firebase project number, creating a new one is the quickest fix
