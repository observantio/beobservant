import { Link, useParams } from "react-router-dom";
import PageHeader from "../components/ui/PageHeader";
import { Card } from "../components/ui";

const TOPICS = {
  "accept-data": {
    title: "How to Accept Data",
    icon: "input",
    intro:
      "Connect your services to Watchdog by sending telemetry through OTLP and validating that logs, metrics, and traces are flowing.",
    steps: [
      "Create an API key on Watchdog, click here to create one now.",
      "After creating, use this sample Otelcol config to get the accept and push data to Watchdog.",
      "You can either use Ojo, our deep collection agent, or any OpenTelemetry compatible client to send data to the Otel collector. You can wish to use the host scraper on the otel collector to get started quickly with host metrics.",
      "Ensure you use the right endpoints for metrics, logs, and traces and ensure to use the right API key in the headers for authentication.",
      "Wait for a few minutes and check if the dashboard is showing any metrics sent for each API key. You can also check the logs of the otelcol to see if there are any errors in sending data to Watchdog.",
      "If there is something wrong, ensure the firewall rules allow outbound traffic to Watchdog and that the API key is correct and has the right permissions.",
    ],
  },
  "share-dashboards": {
    title: "How to Share Dashboards",
    icon: "share",
    intro:
      "Share Grafana resources safely by choosing the right workspace visibility for your use case.",
    steps: [
      "Open Grafana and create or edit a dashboard or folder.",
      "If you create a dashboard without selecting a folder, it is stored in the General folder by default.",
      "Dashboard names should be unique within a folder. If you need the same dashboard name, place it in a different folder.",
      "Select visibility: Personal Workspace, Group Shared Workspace, or Tenant Public Workspace.",
      "For group sharing, choose the target group before saving.",
      "Copy the dashboard URL and share it with your team. Access will depend on the visibility level you set.",
      "If they can see the dashboard, they can also click the 'Open in Watchdog' button to view it within the Watchdog interface with the same filters applied.",
      "If they can access the dashboard but not query it, ensure the datasource permissions are set correctly for the target users or groups in Grafana.",
    ],
  },
  "datasources-dashboards": {
    title: "Datasources and Dashboard Naming Rules",
    icon: "storage",
    intro:
      "Manage datasources and dashboards with safe naming and folder conventions to avoid conflicts.",
    steps: [
      "Open Grafana > Datasources to view existing sources before creating a new one.",
      "A default datasource named Mimir is provisioned by the system and cannot be updated or deleted.",
      "Datasource names must be unique, so you cannot create another datasource with the same name.",
      "When creating dashboards, avoid duplicate names in the same folder to prevent conflicts.",
      "If you need identical dashboard names, place them in different folders.",
      "If no folder is selected, the dashboard is created in the General folder by default.",
    ],
  },
  "folder-visibility": {
    title: "Folder Visibility in Grafana",
    icon: "folder_shared",
    intro:
      "Control who can see and contribute to folders using workspace visibility and folder-level write controls.",
    steps: [
      "Open Grafana, switch to the Folders tab, and click New Folder (or edit an existing folder).",
      "Set Visibility to Personal Workspace, Group Shared Workspace, or Tenant Public Workspace.",
      "If you choose Group Shared Workspace, select one or more Shared Groups in the selector.",
      "Enable Allow members to add dashboards if you want users with folder access to create dashboards in that folder.",
      "Save the folder. Folder edit/delete stays owner-only, while create/upload can be shared when folder writes are enabled.",
      "Use Hide/Unhide for non-owned folders if you want to suppress them in your own view without deleting them globally.",
      "Visibility depends on both folder settings and individual dashboard settings, so ensure both are configured to allow access for the intended users.",
      "If a folder is private but contains a public dashboard, the folder remains hidden and the dashboard is not accessible. Both folder and dashboard need to be shared for it to be visible and accessible to others.",
    ],
  },
  "oidc-local-sync": {
    title: "How OIDC Syncs to Local User State",
    icon: "verified_user",
    intro:
      "OIDC sign-in is completed through a secure callback flow, then Watchdog refreshes the local session user and permissions.",
    steps: [
      "From Login, click the Single Sign-On button when OIDC is enabled for the deployment.",
      "The callback validates PKCE state/nonce values before completing authentication and syncing the local session.",
      "Your email is synced one-to-one with your OIDC provider, so ensure your OIDC account email matches the email of your Watchdog user account. If you were to swtich from local password auth to OIDC, ensure your existing Watchdog user email matches the OIDC provider email for a smooth transition.",
    ],
  },
  "group-permissions": {
    title: "How Group Permissions Work",
    icon: "groups",
    intro:
      "Groups provide inherited permissions to all members and are combined with role defaults and direct user permissions.",
    steps: [
      "Open Groups Management to create a group and define its name/description.",
      "In the group permissions modal, add members and select action-level permissions by resource category.",
      "All group members inherit these permissions, so ensure group permissions are set according to the access level you want for all members.",
      "You will not be able to set permission for a group that exceeds your own permissions, so if you want to create a group with higher permissions than you currently have, ask an admin to create the group or elevate your permissions first.",
    ],
  },
  "permission-guardrails": {
    title: "Permission Guardrails and Admin Safety",
    icon: "admin_panel_settings",
    intro:
      "Role defaults, group permissions, and direct user permissions are additive, with strict safeguards to prevent privilege escalation.",
    steps: [
      "You can add permissions beyond the group defaults and role defaults, not below them. So if your role has read-only permissions, you can add write permissions for a specific resource through group or direct user permissions, but you cannot remove read permissions that come from your role.",
      "Each role has a default permission set that applies to all users with that role. Group permissions are additive on top of role permissions, and direct user permissions are additive on top of both. If you want full control start from a role with minimal permissions and then use groups to add the specific permissions you need for your team, and only use direct user permissions for rare exceptions that don't fit into a group.",
      "You can not create a user (if you have permissions to manage users) but not beyond the permissions you have. So if you have read-only permissions, you can create a user with read-only permissions or a group with read-only permissions, but you cannot create a user or group with write permissions. This ensures that no user can grant themselves or others more permissions than they currently have.",
      "A user will not be able to update it's own role (even if they have permissions to update other users' roles) to prevent privilege escalation. An admin can update the user's role if needed.",
      "Only an admin can disable another admin, but they won't be able to to delete other admin users due to security reasons. So if you need to remove an admin user, you can first disable them and then ask them to delete their own account or just leave the disabled account there since it can't be used to log in.",
    ],
  },
  "roles-permissions": {
    title: "Roles and Permissions Reference",
    icon: "admin_panel_settings",
    intro:
      "Understand default role baselines and every permission available in Watchdog, including what each permission enables.",
    steps: [
      "Use this page as the canonical reference for default role baselines (Provisioning, Viewer, User, Admin).",
      "Remember effective access is additive: Role defaults + Group permissions + Direct user permissions.",
      "Use the permission catalog to map each permission to practical product access before assigning it to users or groups.",
    ],
  },
  "query-tempo": {
    title: "How to Query Tempo",
    icon: "timeline",
    intro:
      "Use trace lookup and filtered search to investigate latency, errors, and service dependencies.",
    steps: [
      "Ensure you have the API key selected in the top right that corresponds to the data you want to query. Only one API key can be enabled at a time for logs/traces scope.",
      "Open Tempo and use Trace ID (direct lookup) when you already have a specific trace identifier.",
      "You may filter by Service Name, Operation Name, or Tags to find relevant traces when you don't have a specific trace ID.",
      "Tune Search Limit and Page Size to control result volume and browsing performance.",
      "Use List View to inspect traces and spans, then open Dependency Map to visualize service interactions.",
      "To get the dependency map, you can select a trace and click the blue hub icon on the right of the trace to open the dependency map.",
      "You can display the dependency map for mulitiple traces by selecting them and  clicking `Show Selected on Map` at the top of the trace list.",
      "You can select nodes in the dependency maps to view latency and error rate for that span",
    ],
  },
  "query-loki": {
    title: "How to Query Loki",
    icon: "view_stream",
    intro:
      "Use direct LogQL or guided builder filters to investigate log errors, traffic patterns, and noisy services.",
    steps: [
      "Ensure you have the API key selected in the top right that corresponds to the data you want to query. Only one API key can be enabled at a time for logs/traces scope.",
      "Open Loki and use Builder mode when you want guided label/value filtering, or Custom mode when you already have a LogQL query.",
      "In Builder mode, choose labels, values, and optional pattern text; in Custom mode, provide a valid LogQL query.",
      "Tune Search Limit and Page Size to control result volume and browsing performance.",
      "Use Log Volume to see activity over time and quickly spot spikes before drilling into individual streams.",
      "Use the Services and Top Terms cards as service recommendations, then apply matching values from Quick Filters for fast pivots.",
      "Use List/Table/Raw views to inspect logs, then use the in-result text filter to narrow displayed rows.",
      "Export results when you need to share data outside the UI.",
    ],
  },
  "incident-board": {
    title: "How to Use Incident Board",
    icon: "assignment",
    intro:
      "Use the Incident Board to triage alert events, assign ownership, and track resolution flow from trigger to closure.",
    steps: [
      "Open Incident Board and start in the Kanban columns (for example Unassigned, Assigned, and Resolved) to understand current workload.",
      "Prioritize by severity and recency, then assign incidents to the right owner from the incident details or quick assign actions.",
      "Incident ownership follows alert-rule ownership and access scope. If a user loses access (for example removed from a shared group), incident cards tied to that access are removed from their board immediately.",
      "Incident card visibility is inherited from the parent alert rule visibility. To change who can see an incident card, update the alert rule visibility/scope in AlertManager.",
      "Use correlation ID and shared labels to group related alerts together so you can triage incident clusters faster.",
      "Open an incident card to review labels, timeline context, assignee, and linked evidence before taking action.",
      "Update incident status as investigation progresses so the board reflects real-time ownership and progress.",
      "Use hide/unhide behavior for resolved items to keep your board clean while preserving historical records.",
      "Create or link downstream actions (for example Jira ticket workflows) when you need external tracking.",
      "Move from incident triage to RCA when needed to investigate root cause across logs, traces, and metrics.",
    ],
  },
  integrations: {
    title: "How Integrations Work",
    icon: "integration_instructions",
    intro:
      "Use Integrations to manage notification channels and Jira connections with the right scope and access controls.",
    steps: [
      "Open Integrations and choose the right scope tab: Private (Personal Workspace), Shared By Groups (Group Shared Workspace), or Shared By Organization (Tenant Public Workspace).",
      "Create channels and Jira integrations in the scope where they should be visible. Group scope requires selecting one or more shared groups.",
      "Permissions and visibility are scope-based: users can only see integrations shared to scopes they can access.",
      "Shared integrations can be used by other users for alert routing and Jira workflows, but non-owners cannot view secrets or edit protected configuration.",
      "Use hide/unhide for shared integrations you do not own to clean up your view without deleting them for other users.",
      "For Jira integration, configure a name, Jira base URL, auth mode (API token, bearer, or SSO where available), and enable the integration.",
      "After saving Jira integration, create Jira issues from incidents and sync comments using integrations visible in your current scope.",
      "If access is removed (for example group membership change), integration visibility and usability are reflected quickly based on updated permissions, and invocation will be blocked even if an alert rule was already configured to use that integration.",
    ],
  },
  "api-key-sharing": {
    title: "How API Key Sharing Works",
    icon: "vpn_key",
    intro:
      "Share API keys safely across users and groups, control default/active keys, and hide keys from your own view when needed.",
    steps: [
      "Open API Key Management and create a key with a clear name for the workload or team.",
      "Set a default API key for your active tenant scope when you want it selected automatically in querying and telemetry workflows.",
      "Only one API key can be enabled at a time. Enabling a different key automatically disables the previously enabled key used for logs and traces context.",
      "Use Share on non-default keys to grant access directly to users or to shared groups.",
      "Default API keys cannot be shared, so create a separate non-default key for sharing scenarios.",
      "Shared keys are visible and usable based on access, and permissions are enforced when sharing is updated or revoked.",
      "Use hide/unhide to remove keys from your current list view without deleting them globally.",
      "Rotate (Regenerate) or delete keys when no longer needed, and update agents or collectors that still depend on old credentials.",
      "Use generated OTLP configuration/token details carefully and store secrets securely outside the UI. You only can view API key secrets at creation time, so ensure to copy them securely when you create or rotate keys.",
    ],
  },
  auditing: {
    title: "How Auditing Works",
    icon: "policy",
    intro:
      "Use Audit & Compliance to track user actions, API activity, and configuration changes with searchable event history.",
    steps: [
      "Open Audit & Compliance and filter by time range, user, action, resource type, or search text.",
      "Use pagination controls and result limits to navigate high-volume activity safely.",
      "Select an audit row to inspect detailed metadata such as method, status, resource IDs, and request context.",
      "Use the user filter with action/resource filters to isolate activity for a specific operator during investigations.",
      "Export filtered results to CSV for compliance reporting and external review.",
      "Use targeted filters during incidents to reconstruct timelines of permission, rule, and integration changes.",
      "Audit visibility is permission-gated, so only users with audit read access can browse or export records.",
    ],
  },
  "quotas-guide": {
    title: "How Quotas Work",
    icon: "data_thresholding",
    intro:
      "Use Quotas to monitor tenant-level limits and current usage for API keys and observability backends.",
    steps: [
      "Open Quotas and select the API key scope (org/tenant scope) you want to inspect.",
      "Review API key capacity (current, max, remaining) before creating additional keys.",
      "Check Loki and Tempo quota cards to compare used versus limit and monitor remaining headroom.",
      "Use source/status badges to understand whether values come from native runtime data or upstream systems and whether data is partial.",
      "Refresh quotas after major onboarding or traffic changes to get the latest usage state.",
      "If quota status is degraded or unavailable, treat values as partial and verify upstream service health.",
      "Use quota trends to plan ingestion growth and avoid hard-limit failures. If key usage crosses your safe threshold, add new keys to distribute workload before hitting limits.",
    ],
  },
  "alert-rules": {
    title: "How to Set Alert Rules",
    icon: "notification_important",
    intro:
      "Create actionable alerts by combining scope, query conditions, routing, and grouping metadata.",
    steps: [
      "Open AlertManager and pick the right scope first (Personal Workspace, Group Shared Workspace, or Tenant Public Workspace) before saving the rule.",
      "When you share a rule, users with access to that scope can see alerts when the rule is invoked. If needed, hide non-owned rules from your own view to keep the board focused.",
      "Access changes are reflected quickly in AlertManager. If a user is removed from a group, shared rules from that group are removed from their accessible view immediately.",
      "Hidden rules are removed from your Alert Board view, but alert events can still trigger incidents and appear on the Incidents board.",
      "Use Alert Builder to create rules from metric namespaces and selectors, or switch to template-driven creation when you want a faster starting point.",
      "Set severity, evaluation window, and threshold behavior so alerts are actionable and not noisy.",
      "Set Duration (or For) to define how long the alert condition must remain true continuously before the rule is invoked.",
      "Use labels consistently across rules and configure silences with matching labels so muting applies to the right alert set.",
      "When a matching silence is active, the alert can still appear on the Alert Board for visibility, but it will not invoke notification channels and will not create incidents on the Incidents board.",
      "Add a correlation ID (or shared grouping label) to related rules so alerts can be grouped together and searched faster during triage.",
      "Attach one or more notification channels from Integrations visible to you. Shared integrations can be selected for routing, but their underlying configuration cannot be viewed or edited unless you own or manage them.",
      "Run a test trigger and confirm delivery to expected recipients.",
    ],
  },
  "rca-engine": {
    title: "How to Use RCA Engine",
    icon: "psychology_alt",
    intro:
      "Use the RCA view to correlate incidents with logs, traces, and alerts for faster root cause analysis.",
    steps: [
      "Open RCA from the left navigation and pick the incident or time window.",
      "Download the default RCA template and customize it with any additional context and ensure to use metrics relevant to your services.",
      "You can query the metrics available by creating a datasource on Watchdog and clicking the sigma icon next to the query editor to open the metric catalog. The catalog includes metrics from our default dashboards and any custom dashboards you have created.",
      "After you configure the template, upload it back to Watchdog and run the RCA job.",
      "Read the analysis report, only use the tool if you suspect an problem is there in your infrastructure, stable services will give false positives and may not be useful to analyze. If the report is inconclusive, consider adding more context to the template and re-running the job.",
    ],
  },
};

const ROLE_DEFAULTS_REFERENCE = [
  {
    role: "Provisioning",
    defaultPermissions: "None",
    notes:
      "Bootstrap role with minimal baseline access. Grant required permissions explicitly through groups or direct assignment.",
  },
  {
    role: "Viewer",
    defaultPermissions:
      "`read:alerts`, `read:silences`, `read:rules`, `read:channels`, `read:incidents`, `read:logs`, `read:traces`, `read:rca`, `read:dashboards`, `read:datasources`, `query:datasources`, `read:folders`, `read:agents`",
    notes: "Read-only operational visibility across core observability features.",
  },
  {
    role: "User",
    defaultPermissions:
      "Viewer defaults + `read:api_keys`, `create:api_keys`, `update:api_keys`, `delete:api_keys`, `create:rca`, `delete:rca`, `read:users`, `read:groups`, `update:incidents`",
    notes:
      "Operational contributor role: investigate, manage own keys, run RCA, and work incidents.",
  },
  {
    role: "Admin",
    defaultPermissions: "All permissions",
    notes:
      "Full tenant administration including user/group management, policy control, and destructive operations.",
  },
];

const PERMISSION_REFERENCE = [
  { permission: "read:audit_logs", what: "View audit and compliance logs", access: "Audit & Compliance page" },
  { permission: "read:alerts", what: "See alert rules and active alerts", access: "AlertManager, Incident Board visibility paths" },
  { permission: "create:alerts", what: "Create alert rules", access: "Alert rule creation flows" },
  { permission: "update:alerts", what: "Modify alerts", access: "Edit alert rules and rule state" },
  { permission: "write:alerts", what: "Create or modify alert rules", access: "Combined create/edit alert authoring" },
  { permission: "delete:alerts", what: "Remove alert rules", access: "Delete alert rules" },
  { permission: "read:silences", what: "See alert silences", access: "Silence list and silence state in AlertManager" },
  { permission: "create:silences", what: "Create an alert silence", access: "Silence creation flows" },
  { permission: "update:silences", what: "Edit an alert silence", access: "Silence edit/update operations" },
  { permission: "delete:silences", what: "Remove an alert silence", access: "Silence deletion" },
  { permission: "read:rules", what: "See alert rules", access: "Rule listings and rule details" },
  { permission: "create:rules", what: "Create an alert rule", access: "Rule creation" },
  { permission: "update:rules", what: "Edit an alert rule", access: "Rule edit operations" },
  { permission: "delete:rules", what: "Remove an alert rule", access: "Rule delete operations" },
  { permission: "test:rules", what: "Trigger rule test notifications", access: "Rule test trigger actions" },
  { permission: "read:metrics", what: "List metrics for rules", access: "Metric namespace/selector lookups in rule builder" },
  { permission: "read:channels", what: "See notification channels", access: "Integrations and rule notification picker" },
  { permission: "create:channels", what: "Create a notification channel", access: "Integrations channel creation" },
  { permission: "update:channels", what: "Edit a notification channel", access: "Integrations channel updates" },
  { permission: "write:channels", what: "Create or edit channels", access: "Combined channel create/update workflows" },
  { permission: "delete:channels", what: "Remove a channel", access: "Channel deletion" },
  { permission: "test:channels", what: "Send test notifications", access: "Channel test actions" },
  { permission: "read:incidents", what: "See incident history", access: "Incident Board and incident context summaries" },
  { permission: "update:incidents", what: "Modify incident details", access: "Assign/resolve/hide and incident updates" },
  { permission: "read:logs", what: "Query and view logs", access: "Loki page and log-powered diagnostics" },
  { permission: "read:traces", what: "Query and view traces", access: "Tempo page and trace/service-map exploration" },
  { permission: "read:rca", what: "View RCA analyses and reports", access: "RCA page report visibility" },
  { permission: "create:rca", what: "Start RCA analysis jobs", access: "RCA job composer/submission" },
  { permission: "delete:rca", what: "Delete your RCA reports", access: "RCA report cleanup/deletion" },
  { permission: "read:dashboards", what: "View Grafana dashboards", access: "Grafana dashboards browsing and viewing" },
  { permission: "create:dashboards", what: "Create Grafana dashboards", access: "Dashboard creation flows" },
  { permission: "update:dashboards", what: "Edit dashboards", access: "Dashboard updates" },
  { permission: "write:dashboards", what: "Create or edit dashboards", access: "Combined dashboard authoring/editing" },
  { permission: "delete:dashboards", what: "Remove dashboards", access: "Dashboard deletion" },
  { permission: "read:datasources", what: "View Grafana datasources", access: "Datasource listings/details" },
  { permission: "create:datasources", what: "Add a Grafana datasource", access: "Datasource creation" },
  { permission: "update:datasources", what: "Edit Grafana datasources", access: "Datasource updates" },
  { permission: "delete:datasources", what: "Remove Grafana datasources", access: "Datasource deletion" },
  { permission: "query:datasources", what: "Query through datasources", access: "Datasource-backed query execution" },
  { permission: "read:folders", what: "View Grafana folders", access: "Folder listings and folder-level visibility" },
  { permission: "create:folders", what: "Create Grafana folders", access: "Folder creation flows" },
  { permission: "delete:folders", what: "Delete Grafana folders", access: "Folder deletion" },
  { permission: "read:agents", what: "View OTEL agents and metrics", access: "Quotas/system agents visibility and related dashboards" },
  { permission: "read:api_keys", what: "View API keys", access: "API Key Management listings/details" },
  { permission: "create:api_keys", what: "Create API keys", access: "API key creation" },
  { permission: "update:api_keys", what: "Edit API keys", access: "API key rename/default/share/hide/rotate updates" },
  { permission: "delete:api_keys", what: "Remove API keys", access: "API key deletion" },
  { permission: "create:users", what: "Create user accounts", access: "Users page create-user flows" },
  { permission: "update:users", what: "Edit user accounts", access: "Users profile/role/status editing" },
  { permission: "delete:users", what: "Remove user accounts", access: "Users deletion actions" },
  { permission: "update:user_permissions", what: "Change a user's permissions", access: "User permission editor" },
  { permission: "manage:users", what: "Manage user accounts", access: "Broad user management controls and privileged user actions" },
  { permission: "read:users", what: "View user info", access: "User listings, assignee lookup, audit user filters" },
  { permission: "create:groups", what: "Create groups", access: "Groups creation" },
  { permission: "update:groups", what: "Edit groups", access: "Group metadata updates" },
  { permission: "delete:groups", what: "Remove groups", access: "Group deletion" },
  { permission: "update:group_permissions", what: "Change group permissions", access: "Group permission editor" },
  { permission: "update:group_members", what: "Change group members", access: "Group membership management" },
  { permission: "manage:groups", what: "Manage groups", access: "Broad group administration controls" },
  { permission: "read:groups", what: "View group info", access: "Group listings and group context selectors" },
  { permission: "manage:tenants", what: "Manage tenant settings", access: "Tenant-level administration and policy boundaries" },
];

const TOPIC_ACCESS = {
  "accept-data": [
    {
      task: "View API keys and endpoint details",
      permissions: "`read:api_keys`",
      roles: "Viewer, User, Admin (if granted)",
    },
    {
      task: "Create or rotate ingestion keys",
      permissions: "`create:api_keys`, `update:api_keys`",
      roles: "User, Admin",
    },
  ],
  "share-dashboards": [
    {
      task: "View dashboards and sharing state",
      permissions: "`read:dashboards`",
      roles: "Viewer, User, Admin",
    },
    {
      task: "Create/edit and share dashboards",
      permissions: "`create:dashboards` or `write:dashboards`",
      roles: "User, Admin",
    },
  ],
  "datasources-dashboards": [
    {
      task: "View datasources and dashboard locations",
      permissions: "`read:datasources`, `read:dashboards`",
      roles: "Viewer, User, Admin",
    },
    {
      task: "Create/update datasources and dashboards",
      permissions:
        "`create:datasources`/`update:datasources`, `create:dashboards`/`write:dashboards`",
      roles: "User, Admin",
    },
  ],
  "folder-visibility": [
    {
      task: "View folder visibility and access",
      permissions: "`read:folders`, `read:dashboards`",
      roles: "Viewer, User, Admin",
    },
    {
      task: "Create/edit shared folders",
      permissions: "`create:folders`, `update:dashboards` or `write:dashboards`",
      roles: "User, Admin",
    },
  ],
  "oidc-local-sync": [
    {
      task: "Sign in with OIDC and sync local user state",
      permissions: "No special permission beyond valid account access",
      roles: "All authenticated roles",
    },
  ],
  "group-permissions": [
    {
      task: "View groups and membership",
      permissions: "`read:groups`",
      roles: "Viewer, User, Admin (if granted)",
    },
    {
      task: "Create/manage groups and group policy",
      permissions:
        "`manage:groups` or `update:group_permissions` + `update:group_members`",
      roles: "Admin (typically), delegated group managers",
    },
  ],
  "permission-guardrails": [
    {
      task: "Update user permissions",
      permissions: "`manage:users` or `update:user_permissions`",
      roles: "Admin (typically)",
    },
    {
      task: "Update group permissions",
      permissions: "`manage:groups` or `update:group_permissions`",
      roles: "Admin (typically)",
    },
  ],
  "roles-permissions": [
    {
      task: "Review role baselines and full permission catalog",
      permissions: "Documentation access (no additional permission required)",
      roles: "All authenticated roles",
    },
  ],
  "query-tempo": [
    {
      task: "Query traces and service graph data",
      permissions: "`read:traces`",
      roles: "Viewer, User, Admin",
    },
  ],
  "query-loki": [
    {
      task: "Query logs and use quick filters/volume",
      permissions: "`read:logs`",
      roles: "Viewer, User, Admin",
    },
  ],
  "incident-board": [
    {
      task: "View incident cards and status",
      permissions: "`read:alerts` and/or `read:incidents`",
      roles: "Viewer, User, Admin",
    },
    {
      task: "Assign/update incident state",
      permissions: "`update:incidents`",
      roles: "User, Admin",
    },
  ],
  integrations: [
    {
      task: "View integrations and select channels",
      permissions: "`read:channels`",
      roles: "Viewer, User, Admin (if granted)",
    },
    {
      task: "Create/edit/test integrations",
      permissions: "`create:channels`, `update:channels`/`write:channels`, `test:channels`",
      roles: "User, Admin",
    },
  ],
  "api-key-sharing": [
    {
      task: "View shared key state",
      permissions: "`read:api_keys`",
      roles: "Viewer, User, Admin (if granted)",
    },
    {
      task: "Create/share/hide/update API keys",
      permissions: "`create:api_keys`, `update:api_keys`",
      roles: "User, Admin",
    },
  ],
  auditing: [
    {
      task: "View and export audit logs",
      permissions: "`read:audit_logs`",
      roles: "Admin (default deployment behavior)",
    },
  ],
  "quotas-guide": [
    {
      task: "View quota cards and API key capacity",
      permissions: "`read:agents`",
      roles: "User, Admin (or delegated viewers)",
    },
  ],
  "alert-rules": [
    {
      task: "View rules, alerts, and channels",
      permissions: "`read:alerts`, `read:channels`",
      roles: "Viewer, User, Admin",
    },
    {
      task: "Create/update rules and silences",
      permissions:
        "`create:alerts`/`write:alerts`, `update:alerts`, `create:silences`, `update:silences`",
      roles: "User, Admin",
    },
    {
      task: "Run rule test actions",
      permissions: "`test:rules` (and channel test flows may require `test:channels`)",
      roles: "User, Admin",
    },
  ],
  "rca-engine": [
    {
      task: "View RCA results and reports",
      permissions: "`read:rca`",
      roles: "Viewer, User, Admin",
    },
    {
      task: "Create RCA jobs",
      permissions: "`create:rca`",
      roles: "User, Admin",
    },
  ],
};

function TopicList() {
  const topicLinks = Object.entries(TOPICS).map(([slug, topic]) => ({
    slug,
    ...topic,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documentation"
        subtitle="Guides for onboarding, identity, permissions, Grafana sharing, querying, alerting, and RCA workflows."
      />
      <div className="grid gap-4 md:grid-cols-2">
        {topicLinks.map((topic) => (
          <Card
            key={topic.slug}
            className="p-5 border-sre-border/70 bg-sre-surface/60 hover:bg-sre-surface-light/60 transition-colors"
          >
            <Link to={`/docs/${topic.slug}`} className="block">
              <div className="flex items-start gap-3">
                <span className="material-icons text-sre-primary" aria-hidden>
                  {topic.icon}
                </span>
                <div>
                  <h2 className="text-base font-semibold text-sre-text">{topic.title}</h2>
                  <p className="mt-1 text-sm text-sre-text-muted">{topic.intro}</p>
                </div>
              </div>
            </Link>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function DocumentationPage() {
  const { topic } = useParams();
  const resolvedTopic = topic ? TOPICS[topic] : null;
  const accessRows = topic ? TOPIC_ACCESS[topic] || [] : [];

  if (!topic) return <TopicList />;
  if (!resolvedTopic) return <TopicList />;

  return (
    <div className="space-y-6">
      <PageHeader
        title={resolvedTopic.title}
        subtitle={resolvedTopic.intro}
      />

      <Card className="p-5 border-sre-border/70 bg-sre-surface/60">
        <ol className="space-y-3">
          {resolvedTopic.steps.map((step, idx) => (
            <li key={step} className="flex items-start gap-3 text-sre-text">
              <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-sre-border bg-sre-bg text-xs font-semibold">
                {idx + 1}
              </span>
              <span className="text-sm leading-6">{step}</span>
            </li>
          ))}
        </ol>
      </Card>
      {accessRows.length > 0 && (
        <Card className="p-5 border-sre-border/70 bg-sre-surface/60">
          <h3 className="text-sm font-semibold text-sre-text">Permissions & Roles</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-sre-border text-left text-sre-text-muted">
                  <th className="px-2 py-2 font-medium">Task</th>
                  <th className="px-2 py-2 font-medium">Required Permissions</th>
                  <th className="px-2 py-2 font-medium">Typical Roles</th>
                </tr>
              </thead>
              <tbody>
                {accessRows.map((row) => (
                  <tr key={`${row.task}-${row.permissions}`} className="border-b border-sre-border/60">
                    <td className="px-2 py-2 align-top text-sre-text">{row.task}</td>
                    <td className="px-2 py-2 align-top text-sre-text-muted">{row.permissions}</td>
                    <td className="px-2 py-2 align-top text-sre-text-muted">{row.roles}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {topic === "roles-permissions" && (
        <>
          <Card className="p-5 border-sre-border/70 bg-sre-surface/60">
            <h3 className="text-sm font-semibold text-sre-text">Default Role Baselines</h3>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-sre-border text-left text-sre-text-muted">
                    <th className="px-2 py-2 font-medium">Role</th>
                    <th className="px-2 py-2 font-medium">Default Permissions</th>
                    <th className="px-2 py-2 font-medium">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {ROLE_DEFAULTS_REFERENCE.map((row) => (
                    <tr key={row.role} className="border-b border-sre-border/60">
                      <td className="px-2 py-2 align-top text-sre-text">{row.role}</td>
                      <td className="px-2 py-2 align-top text-sre-text-muted">{row.defaultPermissions}</td>
                      <td className="px-2 py-2 align-top text-sre-text-muted">{row.notes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card className="p-5 border-sre-border/70 bg-sre-surface/60">
            <h3 className="text-sm font-semibold text-sre-text">Permission Catalog</h3>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-sre-border text-left text-sre-text-muted">
                    <th className="px-2 py-2 font-medium">Permission</th>
                    <th className="px-2 py-2 font-medium">What It Does</th>
                    <th className="px-2 py-2 font-medium">Provides Access To</th>
                  </tr>
                </thead>
                <tbody>
                  {PERMISSION_REFERENCE.map((row) => (
                    <tr key={row.permission} className="border-b border-sre-border/60">
                      <td className="px-2 py-2 align-top text-sre-text">{row.permission}</td>
                      <td className="px-2 py-2 align-top text-sre-text-muted">{row.what}</td>
                      <td className="px-2 py-2 align-top text-sre-text-muted">{row.access}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <div className="text-sm text-sre-text-muted">
        Need more detail? Open the full guide index in{" "}
        <Link to="/docs" className="text-sre-primary hover:underline">
          Documentation
        </Link>
        .
      </div>
    </div>
  );
}
