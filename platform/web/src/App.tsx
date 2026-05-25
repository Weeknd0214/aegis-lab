import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import { ToastProvider } from "./components/Toast";
import { AuthCallbackPage } from "./pages/AuthCallback";
import { LoginPage } from "./pages/Login";
import { LabelingPage } from "./pages/Labeling";
import { CatalogPage } from "./pages/Catalog";
import { AuditDetailPage, AuditPage } from "./pages/Audit";
import { JobsPage } from "./pages/Jobs";
import { TrainingPage } from "./pages/Training";
import { LogsPage } from "./pages/Logs";

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/auth/callback" element={<AuthCallbackPage />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <Layout />
                </RequireAuth>
              }
            >
              <Route index element={<Navigate to="/labeling" replace />} />
              <Route path="labeling" element={<LabelingPage />} />
              <Route path="catalog" element={<CatalogPage />} />
              <Route path="audit" element={<AuditPage />} />
              <Route path="audit/:id" element={<AuditDetailPage />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route path="uploads" element={<Navigate to="/labeling" replace />} />
              <Route path="training" element={<TrainingPage />} />
              <Route path="iterate" element={<Navigate to="/training" replace />} />
              <Route path="logs" element={<LogsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
}
