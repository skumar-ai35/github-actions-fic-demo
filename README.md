# GitHub Actions → Azure Functions: Passwordless Deployment with Federated Identity Credentials

This repository is a complete, runnable demonstration of deploying a Python
Azure Function using GitHub Actions **without storing any secrets**.

Instead of a client secret or certificate, the workflow uses **Federated
Identity Credentials (FIC)** — also known as Workload Identity Federation or
OIDC authentication. GitHub's OIDC provider issues a short-lived signed JWT
for each run; Azure validates that JWT against a pre-configured trust
relationship and issues an access token. No password ever leaves either system.

---

## What this demo shows

| Capability | Detail |
|---|---|
| **Zero secrets** | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` are GitHub Variables (non-sensitive IDs), not secrets. No `client-secret` field exists anywhere. |
| **Short-lived tokens** | The OIDC JWT GitHub issues is valid for ~5 minutes and is scoped to a single workflow run. |
| **Least-privilege identity** | The Entra App Registration has Contributor access only on the target Resource Group, not the whole subscription. |
| **Auditable** | Every deployment appears in Entra sign-in logs with the federated credential details. |
| **Python v2 Functions model** | Uses the decorator-based programming model (no `function.json` files). |

---

## Prerequisites

Before triggering the workflow you must complete the one-time Azure and GitHub
setup described in [infra/README.md](infra/README.md).  At a high level you need:

- **An Azure subscription** with permission to create resources and assign RBAC roles.
- **A GitHub repository** (fork or clone of this repo) with Actions enabled.
- The following Azure resources created manually via the Azure Portal:
  - Resource Group: `rg-fic-demo`
  - Storage Account (any name, LRS, Standard)
  - Function App (Python 3.11, Linux, Consumption plan)
- An **Entra App Registration** with two Federated Identity Credentials:
  - One for the `main` branch (`ref:refs/heads/main`)
  - One for the `production` environment (`environment:production`) — required
    because the workflow sets `environment: production`, which changes the JWT
    subject claim from the branch form to the environment form.
- The App Registration's service principal assigned **Contributor** on the
  Resource Group.
- Four **GitHub Variables** added to your repository:
  - `AZURE_CLIENT_ID`
  - `AZURE_TENANT_ID`
  - `AZURE_SUBSCRIPTION_ID`
  - `AZURE_FUNCTION_APP_NAME`
- A GitHub **Environment** named `production`.

---

## Folder structure

```
github-actions-fic-demo/
├── .github/
│   └── workflows/
│       └── deploy.yml          ← The CI/CD pipeline (OIDC login, test, deploy)
├── src/
│   ├── function_app.py         ← Azure Function v2 (HTTP trigger, GET & POST)
│   ├── host.json               ← Functions host configuration (bundle 4.x)
│   ├── requirements.txt        ← azure-functions==1.21.0
│   └── tests/
│       └── test_function.py    ← pytest unit tests (no running host required)
├── infra/
│   └── README.md               ← Step-by-step Azure Portal setup (no CLI)
└── README.md                   ← This file
```

---

## One-time infrastructure setup

Follow **[infra/README.md](infra/README.md)** for the complete portal walkthrough.
It covers:

- Part 1 — Resource Group, Storage Account, Function App
- Part 2 — Entra App Registration
- Part 3 — Federated Identity Credentials (main branch + production environment + pull request)
- Part 4 — RBAC Contributor role assignment
- Part 5 — GitHub Variables
- Part 6 — GitHub production environment with optional required reviewers
- Part 7 — Verification steps

---

## Triggering a deployment

**Automatic:** Push any commit to the `main` branch.  The workflow fires
automatically, waits for environment approval (if configured), then deploys.

**Manual:** Go to your repository → **Actions** → **Deploy Azure Function
(passwordless FIC)** → **Run workflow** → select the `main` branch →
**Run workflow**.

---

## Verifying it worked

### 1 — Check the Actions run

Open the workflow run in the **Actions** tab. The **Login to Azure** step should
show `Federated credentials login completed` with no client-secret fields.

### 2 — Check Entra sign-in logs

1. Open [portal.azure.com](https://portal.azure.com) → **Microsoft Entra ID**
   → **Monitoring** → **Sign-in logs**.
2. Filter by **Application** → type `github-actions-fic-demo`.
3. Open the sign-in entry and confirm:
   - **Authentication requirement**: Federated credentials
   - **Status**: Success
   - No password or certificate in the Authentication details tab.

### 3 — Call the deployed function

Replace `<app-name>` with the value of `AZURE_FUNCTION_APP_NAME`:

```
GET https://<app-name>.azurewebsites.net/api/HelloFIC
GET https://<app-name>.azurewebsites.net/api/HelloFIC?name=YourName
POST https://<app-name>.azurewebsites.net/api/HelloFIC
     Content-Type: application/json
     {"name": "YourName"}
```

A successful response looks like:

```json
{
  "message": "Hello, YourName! This function was deployed via GitHub Actions using Federated Identity Credentials.",
  "deployed_via": "GitHub Actions + azure/login@v2 (OIDC / Federated Identity Credential)",
  "runtime": "Python 3.11.x",
  "timestamp": "2025-04-13T10:00:00.000000+00:00",
  "auth_method": "OpenID Connect (OIDC) — no client secret stored anywhere",
  "secrets_used": 0
}
```

---

## Troubleshooting

### Error 1 — `AADSTS70021: No matching federated identity record found`

**Symptom:** The `azure/login` step fails with this error code.

**Cause:** The subject identifier in the JWT GitHub issued does not match any
Federated Credential on the App Registration.  Azure performs an exact-string
match — if any part of the subject differs from what was configured, the lookup
fails.

The most common mismatches:

| Situation | Subject GitHub sends | Credential needed |
|---|---|---|
| Push to `main` | `repo:org/repo:ref:refs/heads/main` | Branch → `main` |
| Workflow uses `environment: production` | `repo:org/repo:environment:production` | **Environment → `production`** |
| Pull request | `repo:org/repo:pull_request` | Pull request |

**Fix:**
1. Go to your App Registration → **Certificates & secrets** →
   **Federated credentials**.
2. Check whether a credential with the matching **Subject identifier** exists.
3. If the workflow job sets `environment: production` (as this repo does),
   you need a dedicated credential with **Entity type = Environment** and
   **GitHub environment name = production**.  The branch credential alone is
   not enough.  Follow Part 3.2 of [infra/README.md](infra/README.md) to add it.
4. Ensure the org and repo name in every credential match your GitHub
   repository exactly (case-sensitive).
5. If the run was triggered by a pull request, add a separate PR credential
   (see infra/README.md Part 3.3).

---

### Error 2 — `AuthorizationFailed: does not have authorization to perform action`

**Symptom:** The `azure/functions-action` deploy step fails with a 403.  Login
succeeds but deployment does not.

**Cause:** The App Registration's service principal has not been assigned a
role on the Resource Group (or was assigned on the wrong scope).

**Fix:**
1. Go to **Resource groups** → `rg-fic-demo` → **Access control (IAM)** →
   **Role assignments** tab.
2. Confirm the App Registration (`github-actions-fic-demo`) appears with the
   **Contributor** role.
3. If it is missing, follow Part 4 of [infra/README.md](infra/README.md) to
   assign it.  RBAC changes can take 1–2 minutes to propagate.

---

### Error 3 — `Error: The value of 'AZURE_CLIENT_ID' is not set`

**Symptom:** The workflow fails early because a variable is missing or named
incorrectly.

**Cause:** The GitHub Variable name does not match what the workflow YAML
references, or the variable was added as a **Secret** instead of a **Variable**.

**Fix:**
1. Go to **Settings** → **Secrets and variables** → **Actions** in your
   GitHub repository.
2. Click the **Variables** tab (not Secrets) and confirm all four variables
   are present: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
   `AZURE_FUNCTION_APP_NAME`.
3. Variable names are case-sensitive. The YAML uses `vars.AZURE_CLIENT_ID`
   (uppercase); ensure the portal entries match exactly.
4. If you added them as Secrets by mistake, delete them from the Secrets tab
   and re-add them on the Variables tab.
