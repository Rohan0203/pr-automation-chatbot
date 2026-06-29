### 📢 **Mandatory – Read and Align Before Raising PR**
#### ⚠️⚠️⚠️Champions own review/merge for federated objects, MIW will only review non‑federated or escalations⚠️⚠️⚠️
#### ⚠️⚠️⚠️Mandatory Labels on PR: ENV | Wave | Enterprise/Function | Subgroup | Team⚠️⚠️⚠️
#### ⚠️⚠️⚠️If you still wish to get review done by MIW, attach label `REVIEW_OWNERSHIP:MIW`⚠️⚠️⚠️
#### ⚠️⚠️⚠️Ensure logically scoped and correctly grouped objects - Read [PR Submission Guide](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/PR-Submission-Guide.aspx)⚠️⚠️⚠️
#### 💡💡💡Understand how to raise PR in [Video Guide](https://cargillonline.sharepoint.com/sites/Minerva-FullTeam/_layouts/15/stream.aspx?id=%2Fsites%2FMinerva%2DFullTeam%2FShared%20Documents%2FInformation%20Warehouse%2FMIW%5FVideo%5FSeries%5FGuide%5FRaising%5F%26%5FReviewing%5FPRs%2FVideo11%20%2D%20Prerequisites%20%E2%80%93%20Raising%20and%20Reviewing%20a%20PR%2Emp4&referrer=StreamWebApp%2EWeb&referrerScenario=AddressBarCopied%2Eview%2Edb820636%2D38bc%2D4ede%2Da679%2Dceec6b69c21f)💡💡💡
#### 💡💡💡Learn to review [pipeline run logs](https://cargillonline.sharepoint.com/:v:/r/sites/Minerva-FullTeam/Shared%20Documents/Information%20Warehouse/MIW_Video_Series_Guide_Raising_%26_Reviewing_PRs/Video17%20-%20Viewing%20PR%20Logs%20Through%20Datadog.mov?csf=1&web=1&e=1OitzT)💡💡💡
#### 💡💡💡Link to [MIW's Full Video Guide](https://cargillonline.sharepoint.com/:f:/r/sites/Minerva-FullTeam/Shared%20Documents/Information%20Warehouse/MIW_Video_Series_Guide_Raising_%26_Reviewing_PRs?csf=1&web=1&e=tgKjNK)💡💡💡


### Request Intake Template

#### 1. What is the objective of this request?  
Please describe the use case or business purpose.  
> _e.g., Provisioning a new resource to support ingestion of customer transaction data for reporting and analytics._

---

#### 2. What is the data flow or usage pattern (batch / streaming / hybrid / ad-hoc)?  
> _e.g., Batch ingestion of daily files from an upstream ERP system, transformed and consumed by BI dashboards._

---

#### 3. What is the priority and timeline for this request? Are you aware of MIW’s SLA of 72 hours?  
> _e.g., High priority; needed before quarter-end reporting. Yes, aware of the SLA and aligned with project timelines._

---

#### 4. Has the intake request been approved and is it in “Ready for Design” state? Have you followed MIW naming conventions?  
> _e.g., Yes, approved on 12-Sep and currently in RfD state. Naming conventions followed: `<domain>_<purpose>_<env>`._

---

#### 5. What are the compute and access requirements (size recommendations, entitlements/roles, access mode)?  
> _e.g., Medium compute sizing recommended by MIW; AD group `finance_analytics_team` created; access will be both programmatic and console-based._

---

#### 6. Are there any dependencies, risks, or special considerations we should know before approving this request?  
> _e.g., Dependency on upstream file delivery from vendor; risk of delay if vendor onboarding slips._
