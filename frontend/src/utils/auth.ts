// src/utils/auth.ts
import { decodeToken } from "./jwt";
import { API_URL } from "./env";

export function getToken(): string | null {
  return localStorage.getItem("access_token");
}

export function clearToken() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("username");
}

export function parseToken(token: string): any {
  return decodeToken(token);
}

export function setToken(token: string) {
  localStorage.setItem("access_token", token);
}

export function getUsername(): string | null {
  return localStorage.getItem("username");
}

export function getTokenExpiration(): number | null {
  const token = getToken();
  if (!token) return null;

  const decoded = parseToken(token);
  return decoded?.exp ?? null;
}

export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return null;

  try {
    const response = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) throw new Error("Failed to refresh token");

    const data = await response.json();
    if (data.access_token) {
      localStorage.setItem("access_token", data.access_token);
      return data.access_token;
    }
    return null;
  } catch (err) {
    console.error("Refresh failed:", err);
    return null;
  }
}

export async function getValidAccessToken(): Promise<string | null> {
  const token = getToken();
  if (!token) return null;

  const exp = getTokenExpiration();
  const now = Math.floor(Date.now() / 1000);

  if (exp && exp < now + 60) {
    const refreshed = await refreshAccessToken();
    if (!refreshed) {
      return null;
    }
    return getToken();
  }

  return token;
}
