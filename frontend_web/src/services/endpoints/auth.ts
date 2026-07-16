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
    throw new Error("Usuario ou senha invalidos.");
  }
  return (await response.json()) as TokenResponse;
}

export function getCurrentUser(token: string) {
  return apiRequest<User>("/users/me", { token });
}
