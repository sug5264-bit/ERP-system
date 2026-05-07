import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";

// Resolution order: env var > app.json extra > localhost fallback.
const API_BASE: string =
  (process.env.EXPO_PUBLIC_API_BASE as string | undefined) ||
  ((Constants.expoConfig?.extra as any)?.apiBase as string | undefined) ||
  "http://localhost:8000";

const TOKEN_KEY = "wellgreen_token";

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function setToken(token: string) {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}

export async function clearToken() {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) throw new Error("로그인 실패");
  const data = await res.json();
  await setToken(data.access_token);
  return data.access_token;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
