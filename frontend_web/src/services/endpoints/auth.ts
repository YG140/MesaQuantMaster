import { apiRequest } from "../apiClient";
import type { TokenResponse, User } from "../../types/api";

export async function registerUser(payload: {
  name: string;
  email: string;
  password: string;
}) {
  return apiRequest<User>("/auth/register", {
    method: "POST",
    body: payload,
  });
}

export async function loginUser(email: string, password: string) {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"}/auth/login`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as {
      detail?: string | { message?: string; code?: string };
    } | null;
    const detail = payload?.detail;
    const error = new Error(
      typeof detail === "object" ? detail.message : detail ?? "Usuário ou senha inválidos.",
    ) as Error & { code?: string };
    error.code = typeof detail === "object" ? detail.code : undefined;
    throw error;
  }
  return (await response.json()) as TokenResponse;
}

export const resendVerification = (email: string) =>
  apiRequest<{ message: string }>("/auth/resend-verification", {
    method: "POST", body: { email },
  });

export const forgotPassword = (email: string) =>
  apiRequest<{ message: string }>("/auth/forgot-password", {
    method: "POST", body: { email },
  });

export const verifyEmail = (token: string) =>
  apiRequest<{ message: string }>("/auth/verify-email", {
    method: "POST", body: { token },
  });

export const resetPassword = (token: string, password: string) =>
  apiRequest<{ message: string }>("/auth/reset-password", {
    method: "POST", body: { token, password },
  });

export function getCurrentUser(token: string) {
  return apiRequest<User>("/users/me", { token });
}
