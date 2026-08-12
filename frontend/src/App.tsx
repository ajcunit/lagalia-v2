import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { Shell } from "./components/Shell";
import { t } from "./i18n";
import { DepartmentsAdmin } from "./features/admin/DepartmentsAdmin";
import { UsersAdmin } from "./features/admin/UsersAdmin";
import { ContractDetail } from "./features/contracts/ContractDetail";
import { ContractsList } from "./features/contracts/ContractsList";
import { Dashboard } from "./routes/Dashboard";
import { Login } from "./routes/Login";
import { NotFound } from "./routes/NotFound";
import { Setup } from "./routes/Setup";
import { UnderConstruction } from "./routes/UnderConstruction";

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
              <Route path="/search" element={<UnderConstruction />} />
              <Route path="/admin/users" element={<UsersAdmin />} />
              <Route path="/admin/departments" element={<DepartmentsAdmin />} />
              <Route path="/admin/config" element={<UnderConstruction />} />
              <Route path="/admin/audit-log" element={<UnderConstruction />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
