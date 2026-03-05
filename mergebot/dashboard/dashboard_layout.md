<!-- marker:MERGEBOT_DASHBOARD -->

_This dashboard is your real-time view of all active pull or merge requests (PR/MR) and Mergebot automation in this project._

_Last updated: **{{ last_updated }}**_

---

## 🧩 **Active Pull/Merge Requests (PR/MR)**

{{ active_mrs_table }}

> **Impact Score:** _0–10 (lower = more confident for auto-merge)_

---

### 🔁 **Request a Rerun**

_Check a box below to ask Mergebot to reanalyze any PR/MR. The bot will process checked items and uncheck them after rerun._

{{ rerun_checklist }}

---

## ✅ **Recent Actions**

{{ action_log }}

---

## 🔒 **Active Session**
<!-- marker:MERGEBOT_SESSION_LOCK -->
{{ locks_section }}
<!-- marker:MERGEBOT_SESSION_LOCK -->

---

## 📨 **Review Triggers**
<!-- marker:MERGEBOT_REVIEW_TRIGGERS -->
{{ review_triggers_section }}
<!-- marker:MERGEBOT_REVIEW_TRIGGERS -->

---

## 📊 **Analytics**

{{ analytics_table }}

> **Total Tokens Used:** The sum of all LLM tokens processed by Mergebot for this dashboard run (across all crews and PR/MR analyses). Per-crew breakdown is also shown.

---

<details>
<summary><strong>ℹ️ How to Use</strong> (click to expand)</summary>

- **Want a rerun?** Check the box above
- **Full analysis?** Click "View Report" for any PR/MR to see a detailed, per-agent breakdown in the PR/MR thread.

</details>

Powered by [Mergebot](https://github.com/thehapyone/mergebot)

<!-- marker:MERGEBOT_DASHBOARD -->
