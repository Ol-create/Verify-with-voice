// Response shapes from the TrueVoice admin API (app/routes/admin/schemas.py).

export type CompanyStatus = "pending" | "active" | "suspended";

export interface AdminProfile {
  id: string;
  email: string;
  last_login_at: string | null;
}

export interface AdminToken {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface CompanySummary {
  id: string;
  name: string;
  email: string | null;
  status: CompanyStatus;
  created_at: string | null;
  user_count: number;
  active_key_count: number;
}

export interface CompanyPage {
  items: CompanySummary[];
  total: number;
  page: number;
  page_size: number;
}
