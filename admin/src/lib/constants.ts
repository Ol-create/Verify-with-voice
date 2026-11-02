// Shared by middleware (edge runtime) and server code, so no server-only imports here.

/** httpOnly cookie that holds the admin's API token. The browser's JavaScript can't read it. */
export const ADMIN_COOKIE = "tv_admin_session";
