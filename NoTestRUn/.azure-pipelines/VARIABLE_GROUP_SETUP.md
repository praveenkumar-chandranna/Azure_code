# RCPL Salesforce - Azure DevOps Variable Group Setup

## Variable Group Name: `RCPL-Salesforce-Secrets`

Create this single Variable Group in Azure DevOps under:
**Pipelines > Library > + Variable group**

---

## Variables to Add

| Variable Name                  | Description                                      | Secret? |
|-------------------------------|--------------------------------------------------|---------|
| `SALESFORCE_JWT_SECRET_KEY`   | Full content of the connected app private key    | ✅ Yes  |
| `SANDBOX_URL`                 | Login URL for sandboxes (SIT/QA/UAT)             | No      |
| `LOGIN_URL`                   | Login URL for Production org                     | No      |
| `SALESFORCE_CONSUMER_KEY_SIT` | Connected App Consumer Key for SIT org           | ✅ Yes  |
| `SALESFORCE_CONSUMER_KEY_QA`  | Connected App Consumer Key for QA org            | ✅ Yes  |
| `SALESFORCE_CONSUMER_KEY_UAT` | Connected App Consumer Key for UAT org           | ✅ Yes  |
| `SALESFORCE_CONSUMER_KEY_PROD`| Connected App Consumer Key for PROD org          | ✅ Yes  |
| `SFDX_AUTH_SIT_USERNAME`      | Salesforce username for SIT org                  | No      |
| `SFDX_AUTH_QA_USERNAME`       | Salesforce username for QA org                   | No      |
| `SFDX_AUTH_UAT_USERNAME`      | Salesforce username for UAT org                  | No      |
| `SFDX_AUTH_PROD_USERNAME`     | Salesforce username for PROD org                 | No      |
| `GIT_USER_EMAIL`              | Email for git commits made by the pipeline       | No      |
| `GIT_USER_NAME`               | Display name for git commits made by the pipeline| No      |

---

## Typical Values

| Variable Name          | Example Value                                 |
|------------------------|-----------------------------------------------|
| `SANDBOX_URL`          | `https://test.salesforce.com`                 |
| `LOGIN_URL`            | `https://login.salesforce.com`                |
| `SFDX_AUTH_*_USERNAME` | `user@rcpl.com.sit` / `user@rcpl.com`         |

---

## Steps to Create in Azure DevOps

1. Go to **Pipelines > Library**
2. Click **+ Variable group**
3. Set **Variable group name** = `RCPL-Salesforce-Secrets`
4. Add each variable from the table above
5. For secret variables, click the **lock icon** to mark them as secret
6. Click **Save**

---

## Pipeline OAuth Token (for PR Comments)

For `PR_Validation.yml` to post comments on PRs:
1. Open the pipeline > **Edit** > **...** > **Triggers**
2. Go to **Agent job** > **Additional options**
3. Enable **"Allow scripts to access the OAuth token"**
