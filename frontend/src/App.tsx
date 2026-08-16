import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { Shell } from "./components/Shell";
import { t } from "./i18n";
import { DepartmentsAdmin } from "./features/admin/DepartmentsAdmin";
import { UsersAdmin } from "./features/admin/UsersAdmin";
import { ContractorDetail } from "./features/contractors/ContractorDetail";
import { ContractorDuplicates } from "./features/contractors/ContractorDuplicates";
import { ContractorsList } from "./features/contractors/ContractorsList";
import { ContractDetail } from "./features/contracts/ContractDetail";
import { ContractsList } from "./features/contracts/ContractsList";
import { MinorDetail } from "./features/minors/MinorDetail";
import { MinorsList } from "./features/minors/MinorsList";
import { TasksPage } from "./features/tasks/TasksPage";
import { ConfigAdmin } from "./features/config/ConfigAdmin";
import { ServiceAccountsAdmin } from "./features/service_accounts/ServiceAccountsAdmin";
import { WebhooksAdmin } from "./features/webhooks/WebhooksAdmin";
import { Dashboard } from "./routes/Dashboard";
import { Login } from "./routes/Login";
import { NotFound } from "./routes/NotFound";
import { Setup } from "./routes/Setup";
import { AuditLogAdmin } from "./features/audit/AuditLogAdmin";
import { SyncAdmin } from "./features/sync/SyncAdmin";
import { SuperSearch } from "./features/search/SuperSearch";
import { FavoritesPage } from "./features/favorites/FavoritesPage";
import { RiskAudit } from "./features/audit/RiskAudit";
import { CpvSearch } from "./features/cpv/CpvSearch";
import { AnnualPlan } from "./features/plan/AnnualPlan";
import { AiAdmin } from "./features/ai/AiAdmin";
import { Analyst } from "./features/analyst/Analyst";
import { DocGenerator } from "./features/docgen/DocGenerator";
import { AdminHub } from "./features/admin/AdminHub";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-ink"
      >
        {t("app.skipToContent")}
      </a>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/setup" element={<Setup />} />
            <Route
              element={
                <RequireAuth>
                  <Shell />
                </RequireAuth>
              }
            >
              <Route path="/" element={<Dashboard />} />
              <Route path="/contracts" element={<ContractsList />} />
              <Route path="/contracts/:id" element={<ContractDetail />} />
              <Route path="/minor-contracts" element={<MinorsList />} />
              <Route path="/minor-contracts/:id" element={<MinorDetail />} />
              <Route path="/tasks" element={<TasksPage />} />
              <Route path="/contractors" element={<ContractorsList />} />
              <Route path="/contractors/duplicates" element={<ContractorDuplicates />} />
              <Route path="/contractors/:id" element={<ContractorDetail />} />
              <Route path="/search" element={<SuperSearch />} />
              <Route path="/favorites" element={<FavoritesPage />} />
              <Route path="/audit" element={<RiskAudit />} />
              <Route path="/cpv" element={<CpvSearch />} />
              <Route path="/plan" element={<AnnualPlan />} />
              <Route path="/admin/ai" element={<AiAdmin />} />
              <Route path="/analyst" element={<Analyst />} />
              <Route path="/generator" element={<DocGenerator />} />
              <Route path="/admin" element={<AdminHub />} />
              <Route path="/admin/users" element={<UsersAdmin />} />
              <Route path="/admin/departments" element={<DepartmentsAdmin />} />
              <Route path="/admin/webhooks" element={<WebhooksAdmin />} />
              <Route path="/admin/service-accounts" element={<ServiceAccountsAdmin />} />
              <Route path="/admin/config" element={<ConfigAdmin />} />
              <Route path="/admin/audit-log" element={<AuditLogAdmin />} />
              <Route path="/admin/sync" element={<SyncAdmin />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
