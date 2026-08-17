import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { getCurrentUser, loginUser, registerUser } from "../../services/endpoints/auth";
import { investorProfileEndpoints } from "../../services/endpoints/investorProfile";
import { setUnauthorizedHandler } from "../../services/apiClient";
import type { User } from "../../types/api";

const ONBOARDING_PENDING_STATUSES = new Set([
  "needs_onboarding",
  "in_progress",
  "pending_confirmation",
]);

async function postLoginDestination(token: string): Promise<string> {
  try {
    const status = await investorProfileEndpoints.status(token);
    return ONBOARDING_PENDING_STATUSES.has(status.status) ? "/onboarding" : "/";
  } catch {
    // Diagnóstico do backend indisponível não deve travar o login — a
    // aplicação normal (e o OnboardingGate) continuam protegendo as rotas.
    return "/";
  }
}

const SESSION_KEY = "mesa_quant_session";

type AuthContextValue = {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isRestoring: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { name: string; email: string; password: string }) => Promise<void>;
  logout: () => void;
  restoreSession: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);

  const clearSession = useCallback(() => {
    sessionStorage.removeItem(SESSION_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    navigate("/login", { replace: true });
  }, [clearSession, navigate]);

  const restoreSession = useCallback(async () => {
    const storedToken = sessionStorage.getItem(SESSION_KEY);
    if (!storedToken) {
      clearSession();
      setIsRestoring(false);
      return;
    }
    try {
      const currentUser = await getCurrentUser(storedToken);
      setToken(storedToken);
      setUser(currentUser);
    } catch {
      clearSession();
    } finally {
      setIsRestoring(false);
    }
  }, [clearSession]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearSession();
      navigate("/login", { replace: true });
    });
    void restoreSession();
    return () => setUnauthorizedHandler(null);
  }, [clearSession, navigate, restoreSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokenResponse = await loginUser(email, password);
      sessionStorage.setItem(SESSION_KEY, tokenResponse.access_token);
      const currentUser = await getCurrentUser(tokenResponse.access_token);
      setToken(tokenResponse.access_token);
      setUser(currentUser);
      const destination = await postLoginDestination(tokenResponse.access_token);
      navigate(destination, { replace: true });
    },
    [navigate],
  );

  const register = useCallback(
    async (payload: { name: string; email: string; password: string }) => {
      await registerUser(payload);
    },
    [],
  );

  const value = useMemo(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(token && user),
      isRestoring,
      login,
      register,
      logout,
      restoreSession,
    }),
    [isRestoring, login, logout, register, restoreSession, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
