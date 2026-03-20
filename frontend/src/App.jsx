import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { NotificationProvider } from './context/NotificationContext'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { AppLayout } from './components/layout/AppLayout'

import { LoginForm } from './components/auth/LoginForm'
import { ProjectList } from './components/projects/ProjectList'
import { ProjectDetail } from './components/projects/ProjectDetail'
import { ApprovalList } from './components/approvals/ApprovalList'
import { AuditLog } from './components/audit/AuditLog'
import { UserManagement } from './components/auth/UserManagement'

function AuthenticatedLayout({ children, requiredRole }) {
  return (
    <ProtectedRoute requiredRole={requiredRole}>
      <AppLayout>{children}</AppLayout>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <NotificationProvider>
          <Routes>
            <Route path="/login" element={<LoginForm />} />

            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Navigate to="/projects" replace />
                </ProtectedRoute>
              }
            />

            <Route
              path="/projects"
              element={
                <AuthenticatedLayout>
                  <ProjectList />
                </AuthenticatedLayout>
              }
            />

            <Route
              path="/projects/:projectId"
              element={
                <AuthenticatedLayout>
                  <ProjectDetail />
                </AuthenticatedLayout>
              }
            />

            <Route
              path="/approvals"
              element={
                <AuthenticatedLayout requiredRole="editor">
                  <ApprovalList />
                </AuthenticatedLayout>
              }
            />

            <Route
              path="/users"
              element={
                <AuthenticatedLayout requiredRole="admin">
                  <UserManagement />
                </AuthenticatedLayout>
              }
            />

            <Route
              path="/audit"
              element={
                <AuthenticatedLayout requiredRole="admin">
                  <AuditLog />
                </AuthenticatedLayout>
              }
            />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </NotificationProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
