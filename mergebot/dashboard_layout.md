# 🛠️ Mergebot Project Dashboard
<!-- marker:MERGEBOT_DASHBOARD -->

_This dashboard is your real-time view of all active merge requests and Mergebot automation in this project._

_Last updated: **{{ last_updated }}**_

---

## 🧩 **Active Merge Requests**

{{ active_mrs_table }}

> **Legend:** 🟢=Ready, 🔴=Blocked, 🟡=Needs review  
> **Impact Score:** _0–10 (lower = more confident for auto-merge)_

---

### 🔁 **Request a Rerun**

_Check a box below to ask Mergebot to reanalyze any MR. The bot will process checked items and uncheck them after rerun._

{{ rerun_checklist }}

---

## ✅ **Recent Actions**

{{ action_log }}

---

## 📊 **Analytics (Past 7 Days)**

{{ analytics_table }}

---

<details>
<summary><strong>ℹ️ How to Use</strong> (click to expand)</summary>

- **Want a rerun?** Check the box above
- **Full analysis?** Click "View Report" for any MR to see a detailed, per-agent breakdown in the MR-thread.

</details>

Powered by [Mergebot](https://github.com/your-org/mergebot)

<!-- marker:MERGEBOT_DASHBOARD -->
