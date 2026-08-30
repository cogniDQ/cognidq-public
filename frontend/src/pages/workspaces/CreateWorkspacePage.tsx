/**
 * CreateWorkspacePage — workspace creation page at /workspaces/new.
 *
 * Route is protected by ProtectedRoute in App.tsx.
 * Only workspace_administrator actors should navigate here; others will
 * see the API return 403 when they submit the form.
 */
import CreateWorkspaceForm from '../../components/workspaces/create/CreateWorkspaceForm';

export default function CreateWorkspacePage() {
  return (
    <div className="max-w-2xl" data-testid="create-workspace-page">
      {/* Page heading */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white tracking-tight">
          Create Workspace
        </h1>
        <p className="mt-1 text-sm text-gray-400">
          Add a new workspace to your tenant. Fields marked with{' '}
          <span className="text-red-400">*</span> are required.
        </p>
      </div>

      <div className="rounded-2xl border border-dark-800/60 bg-dark-900/60 p-6 backdrop-blur-sm">
        <CreateWorkspaceForm />
      </div>
    </div>
  );
}
