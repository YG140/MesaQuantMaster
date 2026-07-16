import { Navigate, Outlet, useLocation } from "react-router-dom";
import { LoadingState } from "../../components/feedback/LoadingState";
import { useAuth } from "./useAuth";

export function ProtectedRoute() {
  const auth = useAuth();
  const location = useLocation();

  if (auth.isRestoring) {
    return <LoadingState label="Validando sessao..." />;
  }

  if (!auth.isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
