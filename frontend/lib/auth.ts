"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

export type Role = "admin" | "manager" | "staff" | "viewer";
export type Me = { id: number; email: string; full_name: string; role: Role };

const ROLE_ORDER: Record<Role, number> = {
  viewer: 0,
  staff: 1,
  manager: 2,
  admin: 3,
};

export function hasRole(user: Me | null, min: Role): boolean {
  if (!user) return false;
  return ROLE_ORDER[user.role] >= ROLE_ORDER[min];
}

export function useMe() {
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    api<Me>("/api/auth/me")
      .then(setMe)
      .catch(() => setMe(null));
  }, []);
  return me;
}
