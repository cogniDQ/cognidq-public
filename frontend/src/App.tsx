import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import AdminGuard from './components/admin/AdminGuard'
import AdminLayout from './components/admin/AdminLayout'
import TenantListPage from './pages/admin/tenants/TenantListPage'
import PlatformWelcome from './pages/admin/PlatformWelcome'
import CreateTenantPage from './pages/admin/tenants/CreateTenantPage'
import TenantDetailPage from './pages/admin/tenants/TenantDetailPage'
import EditTenantPage from './pages/admin/tenants/EditTenantPage'
import TenantAuditLogPage from './pages/admin/tenants/TenantAuditLogPage'
import ProvisionTenantPage from './pages/admin/tenants/ProvisionTenantPage'
import CeleryObservabilityPage from './pages/admin/CeleryObservabilityPage'
import Home from './pages/Home'
import DQHub from './pages/DQHub'
import HubEntryResolver from './components/HubEntryResolver'
import WorkspaceOverview from './pages/WorkspaceOverview'
import Glossary from './pages/Glossary'
import RuleFlowBuilder from './pages/RuleFlowBuilder'
import FlowsList from './pages/FlowsList'
import FlowExecutionResults from './pages/FlowExecutionResults'
import FlowExecutions from './pages/FlowExecutions'
import RolesPermissions from './pages/RolesPermissions'
import Login from './pages/auth/Login'
import Register from './pages/auth/Register'
import ForgotPassword from './pages/auth/ForgotPassword'
import Profile from './pages/Profile'
import Settings from './pages/Settings'
import Reports from './pages/Reports'
import WorkspaceListPage from './pages/workspaces/WorkspaceListPage'
import CreateWorkspacePage from './pages/workspaces/CreateWorkspacePage'
import WorkspaceDetailPage from './pages/workspaces/WorkspaceDetailPage'
import WorkspaceSettingsPage from './pages/workspaces/WorkspaceSettingsPage'
import DataSourceListPage from './pages/data-sources/DataSourceListPage'
import CreateDataSourcePage from './pages/data-sources/CreateDataSourcePage'
import DataSourceDetailPage from './pages/data-sources/DataSourceDetailPage'
import EditDataSourcePage from './pages/data-sources/EditDataSourcePage'
import ConnectionListPage from './pages/connections/ConnectionListPage'
import CreateConnectionPage from './pages/connections/CreateConnectionPage'
import ConnectionDetailPage from './pages/connections/ConnectionDetailPage'
import EditConnectionPage from './pages/connections/EditConnectionPage'
import DatasetListPage from './pages/datasets/DatasetListPage'
import CreateDatasetPage from './pages/datasets/CreateDatasetPage'
import DatasetDetailPage from './pages/datasets/DatasetDetailPage'
import EditDatasetPage from './pages/datasets/EditDatasetPage'
import IssuesPage from './pages/workspaces/IssuesPage'
import IssueDetailPage from './pages/workspaces/IssueDetailPage'
import PermissionAuditPage from './pages/workspaces/PermissionAuditPage'
import WorkspaceMembersPage from './pages/workspaces/WorkspaceMembersPage'
import IncidentsPage from './pages/workspaces/IncidentsPage'
import AlertsPage from './pages/workspaces/AlertsPage'
import NotificationEventsPage from './pages/workspaces/NotificationEventsPage'
import AnomaliesPage from './pages/workspaces/AnomaliesPage'
import AuditLogPage from './pages/workspaces/AuditLogPage'
import QualityReportsPage from './pages/workspaces/QualityReportsPage'
import NLRuleBuilder from './pages/NLRuleBuilder'
import RulesPage from './pages/RulesPage'
import MetricsOverview from './pages/MetricsOverview'
import NotFoundPage from './pages/NotFoundPage'
import WorkspaceRedirect from './components/WorkspaceRedirect'
import AdminRedirect from './components/AdminRedirect'
import PermissionGate from './components/PermissionGate'
import WorkspaceAccessGuard from './components/WorkspaceAccessGuard'
import ForbiddenPage from './pages/admin/ForbiddenPage'
import RequestDemoPage from './pages/public/RequestDemoPage'
import TrustPage from './pages/public/TrustPage'
import SecurityPage from './pages/public/SecurityPage'
import PrivacyPage from './pages/public/PrivacyPage'
import StatusPage from './pages/public/StatusPage'
import ContactPage from './pages/public/ContactPage'
import OnboardingWizardPage from './pages/OnboardingWizardPage'
import MarketingKit from './pages/marketing/MarketingKit'
import MarketingAssetPage from './pages/marketing/MarketingAssetPage'
import AdminDemoRequestsPage from './pages/admin/sandbox/AdminDemoRequestsPage'
import AdminSandboxesPage from './pages/admin/sandbox/AdminSandboxesPage'
import TrialExpiredPage from './pages/sandbox/TrialExpiredPage'
import TenantAdminGuard from './components/tenant/TenantAdminGuard'
import TenantAdminRedirect from './components/tenant/TenantAdminRedirect'
import TenantConnectionsRedirect from './components/TenantConnectionsRedirect'
import TenantAdminDashboard from './pages/tenant/TenantAdminDashboard'
import TenantMembersPage from './pages/tenant/TenantMembersPage'
import TenantAssignmentsPage from './pages/tenant/TenantAssignmentsPage'
import AcceptInvitationPage from './pages/auth/AcceptInvitationPage'
import SetPasswordPage from './pages/auth/SetPasswordPage'

function App() {
  return (
    <Router>
      <AuthProvider>
          <Routes>
            {/* Section 1: Public / Auth */}
            <Route path="/auth/login" element={<Login />} />
            <Route path="/auth/register" element={<Register />} />
            <Route path="/auth/forgot-password" element={<ForgotPassword />} />
            <Route path="/auth/accept-invitation" element={<AcceptInvitationPage />} />
            <Route path="/auth/set-password" element={<SetPasswordPage />} />
            <Route path="/request-demo" element={<RequestDemoPage />} />
            <Route path="/trial-expired" element={<TrialExpiredPage />} />

            <Route path="/trust" element={<Layout><TrustPage /></Layout>} />
            <Route path="/security" element={<Layout><SecurityPage /></Layout>} />
            <Route path="/privacy" element={<Layout><PrivacyPage /></Layout>} />
            <Route path="/status" element={<Layout><StatusPage /></Layout>} />
            <Route path="/contact" element={<Layout><ContactPage /></Layout>} />

            <Route path="/onboarding" element={
              <ProtectedRoute>
                <Layout>
                  <OnboardingWizardPage />
                </Layout>
              </ProtectedRoute>
            } />

            <Route path="/" element={
              <Layout>
                <Home />
              </Layout>
            } />

            {/* Marketing graphics kit (public) */}
            <Route path="/marketing" element={
              <Layout>
                <MarketingKit />
              </Layout>
            } />
            <Route path="/marketing/:slug" element={
              <Layout>
                <MarketingAssetPage />
              </Layout>
            } />

            {/* Section 2: Platform Admin */}
            <Route path="/admin" element={
              <AdminGuard>
                <AdminLayout>
                  <PlatformWelcome />
                </AdminLayout>
              </AdminGuard>
            } />
            <Route path="/admin/tenants" element={
              <AdminGuard>
                <AdminLayout>
                  <TenantListPage />
                </AdminLayout>
              </AdminGuard>
            } />
            <Route path="/admin/celery" element={
              <AdminGuard>
                <AdminLayout>
                  <CeleryObservabilityPage />
                </AdminLayout>
              </AdminGuard>
            } />
            <Route path="/admin/tenants/new" element={
              <AdminGuard>
                <AdminLayout>
                  <CreateTenantPage />
                </AdminLayout>
              </AdminGuard>
            } />
            <Route path="/admin/tenants/:tenant_id/provision" element={
              <AdminGuard>
                <AdminLayout>
                  <ProvisionTenantPage />
                </AdminLayout>
              </AdminGuard>
            } />
            <Route path="/admin/tenants/:tenant_id/edit" element={
              <AdminGuard>
                <AdminLayout>
                  <EditTenantPage />
                </AdminLayout>
              </AdminGuard>
            } />
            <Route path="/admin/tenants/:tenant_id" element={
              <AdminGuard>
                <AdminLayout>
                  <TenantDetailPage />
                </AdminLayout>
              </AdminGuard>
            } />
            <Route path="/admin/tenants/:tenant_id/audit-logs" element={
              <AdminGuard>
                <AdminLayout>
                  <TenantAuditLogPage />
                </AdminLayout>
              </AdminGuard>
            } />
            <Route path="/admin/demo-requests" element={
              <AdminGuard>
                <AdminLayout>
                  <AdminDemoRequestsPage />
                </AdminLayout>
              </AdminGuard>
            } />
            <Route path="/admin/sandboxes" element={
              <AdminGuard>
                <AdminLayout>
                  <AdminSandboxesPage />
                </AdminLayout>
              </AdminGuard>
            } />

            {/* Section 2b: Tenant Admin — legacy redirects to unified /hub/t/:tenantId/* shell */}
            <Route path="/tenant-admin" element={<TenantAdminRedirect />} />
            <Route path="/tenant-admin/members" element={<TenantAdminRedirect suffix="/members" />} />
            <Route path="/tenant-admin/assignments" element={<TenantAdminRedirect suffix="/assignments" />} />

            {/* Section 3: DQ Hub */}
            <Route path="/hub/*" element={
              <ProtectedRoute>
                <DQHub />
              </ProtectedRoute>
            }>
              <Route index element={<HubEntryResolver />} />

              {/* Hub-level pages */}
              <Route path="workspaces" element={<WorkspaceListPage />} />
              <Route path="metrics" element={<MetricsOverview />} />

              {/* Context-based workspace pages — P02 adds workspace_id param */}
              <Route path="flows" element={<FlowsList />} />
              <Route path="flow-builder" element={<RuleFlowBuilder />} />
              <Route path="executions" element={<FlowExecutions />} />
              <Route path="executions/:executionId" element={<FlowExecutionResults />} />
              <Route path="reports" element={<Reports />} />
              <Route path="roles" element={<RolesPermissions />} />

              {/* Workspace-parameterized routes — guarded by WorkspaceAccessGuard (F131 P03) */}
              <Route path="ws/:workspace_id" element={<WorkspaceAccessGuard />}>
                <Route path="overview" element={<WorkspaceOverview />} />
                <Route path="flows" element={<FlowsList />} />
                <Route path="flow-builder" element={<RuleFlowBuilder />} />
                <Route path="executions" element={<FlowExecutions />} />
                <Route path="executions/:executionId" element={<FlowExecutionResults />} />
                <Route path="flow-reports" element={<Reports />} />
                <Route path="roles" element={<RolesPermissions />} />
                <Route path="permission-audit" element={
                  <PermissionGate permission="view_audit_logs">
                    <PermissionAuditPage />
                  </PermissionGate>
                } />
                <Route path="notification-log" element={<NotificationEventsPage />} />
                <Route path="members" element={<WorkspaceMembersPage />} />
                <Route path="incidents" element={<IncidentsPage />} />
                <Route path="alerts" element={<AlertsPage />} />
                <Route path="anomalies" element={<AnomaliesPage />} />
                <Route path="notification-events" element={<NotificationEventsPage />} />
                <Route path="activity-log" element={<AuditLogPage />} />
                <Route path="quality-reports" element={<QualityReportsPage />} />
                <Route path="issues" element={<IssuesPage />} />
                <Route path="issues/:issue_id" element={<IssueDetailPage />} />
                <Route path="audit" element={<PermissionAuditPage />} />
                <Route path="settings" element={<WorkspaceSettingsPage />} />
                <Route path="data-sources" element={<DataSourceListPage />} />
                <Route path="data-sources/new" element={<CreateDataSourcePage />} />
                <Route path="data-sources/:data_source_id" element={<DataSourceDetailPage />} />
                <Route path="data-sources/:data_source_id/edit" element={<EditDataSourcePage />} />
                <Route path="datasets" element={<DatasetListPage />} />
                <Route path="datasets/new" element={<CreateDatasetPage />} />
                <Route path="datasets/:dataset_id" element={<DatasetDetailPage />} />
                <Route path="datasets/:dataset_id/edit" element={<EditDatasetPage />} />
                <Route path="glossary" element={<Glossary />} />
                <Route path="nl-rule-builder" element={<NLRuleBuilder />} />
                <Route path="rules" element={<RulesPage />} />
              </Route>

              {/* Legacy flat connections routes — redirect to hub root (workspace required) */}
              <Route path="connections" element={<Navigate replace to="/hub" />} />
              <Route path="connections/*" element={<Navigate replace to="/hub" />} />

              {/* Legacy flat glossary route — redirect to hub root */}
              <Route path="glossary" element={<Navigate replace to="/hub" />} />

              {/* Profile & Settings */}
              <Route path="profile" element={<Profile />} />
              <Route path="settings" element={<Settings />} />

              {/* Workspace Management */}
              <Route path="workspaces/new" element={<CreateWorkspacePage />} />
              <Route path="workspaces/:workspace_id" element={<WorkspaceDetailPage />} />
              <Route path="workspaces/:workspace_id/settings" element={<WorkspaceSettingsPage />} />

              {/* Tenant-scoped routes — unified shell for tenant_admin (and platform_admin preview) */}
              <Route path="t/:tenant_id" element={<TenantAdminGuard><TenantAdminDashboard /></TenantAdminGuard>} />
              <Route path="t/:tenant_id/members" element={<TenantAdminGuard><TenantMembersPage /></TenantAdminGuard>} />
              <Route path="t/:tenant_id/assignments" element={<TenantAdminGuard><TenantAssignmentsPage /></TenantAdminGuard>} />
              {/* Connections are tenant-scoped resources managed by tenant_admin */}
              <Route path="t/:tenant_id/connections" element={<TenantAdminGuard><ConnectionListPage /></TenantAdminGuard>} />
              <Route path="t/:tenant_id/connections/new" element={<TenantAdminGuard><CreateConnectionPage /></TenantAdminGuard>} />
              <Route path="t/:tenant_id/connections/:connection_id" element={<TenantAdminGuard><ConnectionDetailPage /></TenantAdminGuard>} />
              <Route path="t/:tenant_id/connections/:connection_id/edit" element={<TenantAdminGuard><EditConnectionPage /></TenantAdminGuard>} />

              {/* Tenant-scoped workspace routes — alias of /hub/ws/:workspace_id/* with tenant context in URL */}
              <Route path="t/:tenant_id/ws/:workspace_id" element={<WorkspaceAccessGuard />}>
                <Route path="overview" element={<WorkspaceOverview />} />
                <Route path="flows" element={<FlowsList />} />
                <Route path="flow-builder" element={<RuleFlowBuilder />} />
                <Route path="executions" element={<FlowExecutions />} />
                <Route path="executions/:executionId" element={<FlowExecutionResults />} />
                <Route path="flow-reports" element={<Reports />} />
                <Route path="roles" element={<RolesPermissions />} />
                <Route path="permission-audit" element={
                  <PermissionGate permission="view_audit_logs">
                    <PermissionAuditPage />
                  </PermissionGate>
                } />
                <Route path="notification-log" element={<NotificationEventsPage />} />
                <Route path="members" element={<WorkspaceMembersPage />} />
                <Route path="incidents" element={<IncidentsPage />} />
                <Route path="alerts" element={<AlertsPage />} />
                <Route path="anomalies" element={<AnomaliesPage />} />
                <Route path="notification-events" element={<NotificationEventsPage />} />
                <Route path="activity-log" element={<AuditLogPage />} />
                <Route path="quality-reports" element={<QualityReportsPage />} />
                <Route path="issues" element={<IssuesPage />} />
                <Route path="issues/:issue_id" element={<IssueDetailPage />} />
                <Route path="audit" element={<PermissionAuditPage />} />
                <Route path="settings" element={<WorkspaceSettingsPage />} />
                <Route path="data-sources" element={<DataSourceListPage />} />
                <Route path="data-sources/new" element={<CreateDataSourcePage />} />
                <Route path="data-sources/:data_source_id" element={<DataSourceDetailPage />} />
                <Route path="data-sources/:data_source_id/edit" element={<EditDataSourcePage />} />
                <Route path="datasets" element={<DatasetListPage />} />
                <Route path="datasets/new" element={<CreateDatasetPage />} />
                <Route path="datasets/:dataset_id" element={<DatasetDetailPage />} />
                <Route path="datasets/:dataset_id/edit" element={<EditDatasetPage />} />
                <Route path="glossary" element={<Glossary />} />
                <Route path="nl-rule-builder" element={<NLRuleBuilder />} />
                <Route path="rules" element={<RulesPage />} />
              </Route>
            </Route>

            {/* Section 4: Redirects */}
            <Route path="/login" element={<Navigate to="/auth/login" replace />} />
            <Route path="/register" element={<Navigate to="/auth/register" replace />} />
            <Route path="/profile" element={<Navigate to="/hub/profile" replace />} />
            <Route path="/settings" element={<Navigate to="/hub/settings" replace />} />
            {/* F132 P04: platform_admin no longer has Workspaces in nav (hidden by useNavigationMenu).
                These legacy redirects remain for direct-link compatibility only. */}
            <Route path="/workspaces" element={<Navigate to="/hub/workspaces" replace />} />
            <Route path="/workspaces/new" element={<Navigate to="/hub/workspaces/new" replace />} />
            <Route path="/workspaces/:id/data-sources/*" element={<WorkspaceRedirect base="/hub/ws" suffix="/data-sources" />} />
            {/* F130 — redirect old workspace data-sources hub path to tenant connections */}
            <Route path="/hub/ws/:id/data-sources" element={<Navigate replace to="/hub/connections" />} />
            {/* F132 — /new sub-route must come before the /* wildcard */}
            <Route path="/hub/ws/:id/data-sources/new" element={<Navigate replace to="/hub/connections/new" />} />
            <Route path="/hub/ws/:id/data-sources/*" element={<Navigate replace to="/hub/connections" />} />
            {/* /hub/ws/:id/glossary is now a first-class workspace route — no redirect needed */}
            {/* F132 — legacy flat-path redirect */}
            <Route path="/hub/datasources" element={<Navigate replace to="/hub/connections" />} />
            {/* Connections moved to Tenant Administration — redirect old workspace-scoped URLs */}
            <Route path="/hub/ws/:id/connections/*" element={<Navigate replace to="/hub/connections" />} />
            <Route path="/hub/ws/:id/connections" element={<Navigate replace to="/hub/connections" />} />
            <Route path="/hub/t/:tenant_id/ws/:id/connections/*" element={<TenantConnectionsRedirect />} />
            <Route path="/hub/t/:tenant_id/ws/:id/connections" element={<TenantConnectionsRedirect />} />
            <Route path="/hub/connections" element={<TenantConnectionsRedirect />} />
            <Route path="/hub/connections/new" element={<TenantConnectionsRedirect suffix="/new" />} />
            <Route path="/hub/connections/:connection_id" element={<TenantConnectionsRedirect />} />
            <Route path="/hub/connections/:connection_id/edit" element={<TenantConnectionsRedirect />} />
            <Route path="/workspaces/:id/datasets/*" element={<WorkspaceRedirect base="/hub/ws" suffix="/datasets" />} />
            <Route path="/workspaces/:id/issues/*" element={<WorkspaceRedirect base="/hub/ws" suffix="/issues" />} />
            <Route path="/workspaces/:id/audit" element={<WorkspaceRedirect base="/hub/ws" suffix="/permission-audit" />} />
            <Route path="/hub/admin/*" element={<AdminRedirect />} />
            <Route path="/hub/ws/:id/audit" element={<WorkspaceRedirect base="/hub/ws" suffix="/permission-audit" />} />
            <Route path="/hub/ws/:id/notification-events" element={<WorkspaceRedirect base="/hub/ws" suffix="/notification-log" />} />

            {/* Section 5: Explicit error pages + 404 catch-all */}
            <Route path="/404" element={<NotFoundPage />} />
            <Route path="/forbidden" element={<ForbiddenPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
      </AuthProvider>
    </Router>
  )
}

export default App
