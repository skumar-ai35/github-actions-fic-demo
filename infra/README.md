# Infrastructure Setup — Azure Portal (Manual, No CLI)

This guide walks you through every Azure and GitHub click needed before the
GitHub Actions workflow can deploy passwordlessly using Federated Identity
Credentials (FIC / OIDC).

**Estimated time:** 20–30 minutes  
**Tools required:** A browser — no Azure CLI, no PowerShell, no Bicep.

---

## Part 1 — Create Azure Resources

### 1.1 Create a Resource Group

1. Open [portal.azure.com](https://portal.azure.com) and sign in.
2. In the top search bar type **Resource groups** and click the service.
3. Click **+ Create**.
4. Fill in:
   | Field | Value |
   |---|---|
   | Subscription | *(your subscription)* |
   | Resource group name | `rg-fic-demo` |
   | Region | e.g. `East US 2` |
5. Click **Review + create** → **Create**.

---

### 1.2 Create a Storage Account

Azure Functions requires a Storage Account for internal bookkeeping (logs,
deployment artifacts, durable task state).

1. Search for **Storage accounts** in the portal search bar → click the service.
2. Click **+ Create**.
3. Fill in:
   | Field | Value |
   |---|---|
   | Subscription | *(your subscription)* |
   | Resource group | `rg-fic-demo` |
   | Storage account name | e.g. `stficdemo<random4digits>` *(must be globally unique, 3–24 lowercase letters/numbers)* |
   | Region | Same as the Resource Group |
   | Performance | Standard |
   | Redundancy | LRS (Locally-redundant storage) is fine for demos |
4. Leave all other tabs at their defaults.
5. Click **Review** → **Create**.

---

### 1.3 Create the Function App

1. Search for **Function App** → click the service.
2. Click **+ Create** → choose **Consumption** (the "Serverless" tile).
3. **Basics** tab:
   | Field | Value |
   |---|---|
   | Subscription | *(your subscription)* |
   | Resource group | `rg-fic-demo` |
   | Function App name | e.g. `func-fic-demo` *(globally unique)* |
   | Runtime stack | **Python** |
   | Version | **3.11** |
   | Region | Same as above |
   | Operating System | **Linux** *(required for Python)* |
4. **Storage** tab → select the storage account created in 1.2.
5. Leave Monitoring, Networking, Deployment tabs at defaults.
6. Click **Review + create** → **Create**.
7. Once deployment finishes, click **Go to resource** and note:
   - The **Function App name** (you'll add it as a GitHub Variable later).
   - The **default domain** shown on the Overview blade, e.g.
     `func-fic-demo.azurewebsites.net` — you'll use this to test the function.

---

## Part 2 — Create an Entra App Registration

The App Registration is the identity that GitHub Actions will impersonate.
It has no password — access is granted purely via a Federated Credential.

1. Search for **Microsoft Entra ID** → click the service.
2. In the left-hand menu, click **App registrations** → **+ New registration**.
3. Fill in:
   | Field | Value |
   |---|---|
   | Name | `github-actions-fic-demo` |
   | Supported account types | **Accounts in this organizational directory only** (single tenant) |
   | Redirect URI | Leave blank |
4. Click **Register**.
5. On the **Overview** page that opens, copy and save these three values —
   you will need them in Part 5:
   - **Application (client) ID** → this is `AZURE_CLIENT_ID`
   - **Directory (tenant) ID** → this is `AZURE_TENANT_ID`
   - **Object ID** → used when assigning RBAC (Part 4)

> **No client secret needed.** Do NOT create a client secret or certificate.
> The Federated Credential you add in Part 3 replaces them entirely.

---

## Part 3 — Add Federated Identity Credentials

Federated Credentials tell Azure: "trust tokens issued by GitHub Actions for
this specific repository and ref, and treat them as proof that the App
Registration authenticated successfully."

### 3.1 Add the credential for the `main` branch

1. From the App Registration, click **Certificates & secrets** in the left menu.
2. Click the **Federated credentials** tab.
3. Click **+ Add credential**.
4. In the **Federated credential scenario** dropdown, select  
   **GitHub Actions deploying Azure resources**.
5. Fill in the GitHub fields:
   | Field | Value |
   |---|---|
   | Organization | Your GitHub username or org, e.g. `myorg` |
   | Repository | The repo name, e.g. `github-actions-fic-demo` |
   | Entity type | **Branch** |
   | GitHub branch name | `main` |
   | Name | `github-main-branch` *(any unique name)* |
   | Description | `Allows GitHub Actions on main to deploy` |
6. Observe the three **auto-populated** read-only fields before saving:
   - **Issuer**: `https://token.actions.githubusercontent.com`  
     This is GitHub's OIDC provider URL.  Azure will only trust tokens
     whose `iss` claim matches this value exactly.
   - **Subject identifier**: `repo:myorg/github-actions-fic-demo:ref:refs/heads/main`  
     Encodes the exact repository and ref that is permitted.  A token
     from a different repo or branch will be rejected.
   - **Audience**: `api://AzureADTokenExchange`  
     The `aud` claim GitHub puts in the JWT.  Azure requires this value
     to prevent token replay attacks across different services.
7. Click **Add**.

### 3.2 Add a credential for the `production` environment (required)

The workflow YAML contains `environment: production`.  When a job targets a
named GitHub Environment, GitHub changes the JWT subject claim from the branch
form to the environment form:

```
# Without environment:
repo:myorg/github-actions-fic-demo:ref:refs/heads/main

# With environment: production:
repo:myorg/github-actions-fic-demo:environment:production
```

These two strings are **different**, so the `main` branch credential created in
3.1 will **not** match and Azure will reject the token with
`AADSTS70021: No matching federated identity record found`.

Add a separate credential for the environment:

1. From the App Registration, click **Certificates & secrets** →
   **Federated credentials** → **+ Add credential**.
2. Select **GitHub Actions deploying Azure resources**.
3. Fill in the GitHub fields:
   | Field | Value |
   |---|---|
   | Organization | Your GitHub username or org, e.g. `myorg` |
   | Repository | `github-actions-fic-demo` |
   | Entity type | **Environment** |
   | GitHub environment name | `production` |
   | Name | `github-environment-production` |
   | Description | `Allows GitHub Actions running in the production environment` |
4. Confirm the auto-populated **Subject identifier** reads:  
   `repo:myorg/github-actions-fic-demo:environment:production`
5. Click **Add**.

> **Why is this separate from the branch credential?**  
> Azure performs an exact-string match on the subject claim.  A single
> credential cannot cover both the branch form and the environment form.
> Each distinct subject pattern needs its own Federated Credential entry.

### 3.3 Add a credential for Pull Requests (optional but recommended)

Repeat the steps from 3.1 with:
| Field | Value |
|---|---|
| Entity type | **Pull request** |
| Name | `github-pull-request` |
| Description | `Allows GitHub Actions on PRs to run (read-only)` |

> **Why add a PR credential?**  
> If you ever add a workflow trigger for `pull_request` events, without this
> credential the OIDC login step would fail — PRs generate a subject of
> `repo:myorg/repo:pull_request` (no branch suffix), which does not match
> the `main` branch credential.  Adding it now avoids confusion later.

---

## Part 4 — Assign the Contributor RBAC Role

The App Registration needs permission to create/update resources inside the
Resource Group.  The **Contributor** role is the minimum required for
`azure/functions-action` to deploy.

1. Navigate to **Resource groups** → `rg-fic-demo`.
2. In the left menu click **Access control (IAM)**.
3. Click **+ Add** → **Add role assignment**.
4. **Role** tab: search for and select **Contributor** → click **Next**.
5. **Members** tab:
   - Assign access to: **User, group, or service principal**
   - Click **+ Select members**
   - In the search box paste the **Application (client) ID** you copied in
     Part 2 (searching by name is unreliable; client ID is unambiguous)
   - Select the app registration from the results
   - Click **Select**
6. Click **Review + assign** → **Review + assign** again to confirm.

> **Scope note:** Assigning Contributor at the Resource Group level (not the
> subscription) follows the principle of least privilege — the service principal
> can only modify resources inside `rg-fic-demo`.

---

## Part 5 — Add GitHub Variables

GitHub **Variables** (not Secrets) are used for non-sensitive configuration.
The three Azure IDs are not sensitive — they are visible in Azure portal URLs,
ARM templates, and Entra sign-in logs.  Using Variables instead of Secrets:
- Makes the values visible in workflow logs (easier debugging)
- Avoids the "secret masking" that can corrupt GUIDs containing common substrings
- Signals to future maintainers that these values are not credentials

### 5.1 Add repository-level variables

1. In your GitHub repository, go to **Settings** → **Secrets and variables** →
   **Actions**.
2. Click the **Variables** tab (NOT the Secrets tab).
3. Click **New repository variable** for each of the following:

   | Name | Value |
   |---|---|
   | `AZURE_CLIENT_ID` | Application (client) ID from Part 2 |
   | `AZURE_TENANT_ID` | Directory (tenant) ID from Part 2 |
   | `AZURE_SUBSCRIPTION_ID` | Your Azure Subscription ID *(find it in portal.azure.com → Subscriptions)* |
   | `AZURE_FUNCTION_APP_NAME` | The Function App name from Part 1.3, e.g. `func-fic-demo` |

> **Important:** The workflow references these as `${{ vars.AZURE_CLIENT_ID }}`
> (not `secrets.`).  If you accidentally add them as Secrets the `azure/login`
> action will still work, but the values will be masked in logs.

---

## Part 6 — Create the GitHub Production Environment

Tying the workflow to an environment enables protection rules and deployment
history.

1. In your GitHub repository, go to **Settings** → **Environments**.
2. Click **New environment**.
3. Name it `production` (must match the `environment: production` in the
   workflow YAML exactly).
4. Click **Configure environment**.
5. (Optional but recommended) Under **Deployment protection rules**:
   - Enable **Required reviewers**
   - Add yourself or your team as a reviewer
   - This means every push to `main` will pause for manual approval before
     the Azure deployment step runs
6. Click **Save protection rules**.

---

## Part 7 — Verify the Setup

### 7.1 Trigger the workflow

- Push any commit to the `main` branch, or
- Go to **Actions** → select the workflow → **Run workflow** → **Run workflow**

### 7.2 Watch the Actions run

1. Click into the running workflow.
2. Expand the **Login to Azure (OIDC / FIC — no secret)** step.
3. You should see output like:
   ```
   Federated credentials login completed
   ```
   If you see an error instead, see the Troubleshooting section in the
   main README.

### 7.3 Confirm in Entra sign-in logs

1. Go to **Microsoft Entra ID** → **Monitoring** → **Sign-in logs**.
2. Filter by **Application** = `github-actions-fic-demo`.
3. You should see a successful sign-in with:
   - **Authentication requirement**: Federated credentials
   - **Client app**: Service principal
4. Click the entry and check the **Authentication details** tab to confirm
   no password or certificate was used.

### 7.4 Test the deployed function

Once the workflow shows a green tick, call the function:

```
https://<your-function-app-name>.azurewebsites.net/api/HelloFIC
```

With a name parameter:

```
https://<your-function-app-name>.azurewebsites.net/api/HelloFIC?name=YourName
```

You should receive a JSON response confirming zero secrets were used.

---

## Common Issues

See the **Troubleshooting** section in the root [README.md](../README.md) for
the top three FIC errors and how to fix them.
