import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ADMIN_COOKIE } from "@/lib/constants";

/** A non-2xx answer from the API that pages may want to show (409, 422...). */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

export function apiUrl(path: string): URL {
  // Server-only variable: the API address never reaches the browser
  const base = process.env.TRUEVOICE_API_URL;
  if (!base) throw new Error("TRUEVOICE_API_URL is not set. See admin/.env.example.");
  return new URL(path, base);
}

export async function errorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join(", ");
  } catch {
    // not JSON
  }
  return `${res.status} ${res.statusText}`;
}

/**
 * Call the admin API as the signed-in admin. Use from Server Components and Server Actions only.
 * A missing or rejected session sends the admin to the login page.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = (await cookies()).get(ADMIN_COOKIE)?.value;
  if (!token) redirect("/login");

  const res = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (res.status === 401) redirect("/login?expired=1");
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  return (await res.json()) as T;
}
