"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { apiUrl } from "@/lib/api";
import { ADMIN_COOKIE } from "@/lib/constants";
import type { AdminToken } from "@/lib/types";

export interface LoginState {
  error: string | null;
  email: string;
}

/** Only same-site paths, so ?next= can't send someone to another website after login. */
function safeNext(next: FormDataEntryValue | null): string {
  const path = typeof next === "string" ? next : "";
  return path.startsWith("/") && !path.startsWith("//") && !path.startsWith("/\\") ? path : "/";
}

export async function login(_prev: LoginState, form: FormData): Promise<LoginState> {
  const email = String(form.get("email") ?? "").trim();
  const password = String(form.get("password") ?? "");
  if (!email || !password) return { error: "Enter your email and password.", email };

  let res: Response;
  try {
    res = await fetch(apiUrl("/admin/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch {
    return { error: "Can't reach the TrueVoice API. Try again shortly.", email };
  }

  if (res.status === 401) return { error: "Invalid email or password.", email };
  if (res.status === 429) return { error: "Too many sign-in attempts. Wait a minute and try again.", email };
  if (!res.ok) return { error: `Sign-in failed (${res.status}). Try again shortly.`, email };

  const token = (await res.json()) as AdminToken;
  (await cookies()).set(ADMIN_COOKIE, token.access_token, {
    httpOnly: true, // page scripts can't read it
    secure: process.env.NODE_ENV === "production", // HTTPS only once deployed
    sameSite: "strict",
    path: "/",
    maxAge: token.expires_in, // the cookie disappears when the token expires
  });
  redirect(safeNext(form.get("next")));
}

export async function logout() {
  (await cookies()).delete(ADMIN_COOKIE);
  redirect("/login");
}
