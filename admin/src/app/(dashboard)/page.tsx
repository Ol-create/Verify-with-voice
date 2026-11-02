import type { Metadata } from "next";

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { CompanyPage, CompanyStatus } from "@/lib/types";

export const metadata: Metadata = { title: "Dashboard · TrueVoice Admin" };

async function companyCount(status?: CompanyStatus): Promise<number> {
  const params = new URLSearchParams({ page_size: "1" });
  if (status) params.set("status", status);
  return (await apiFetch<CompanyPage>(`/admin/companies?${params}`)).total;
}

export default async function DashboardPage() {
  const [total, active, pending, suspended] = await Promise.all([
    companyCount(),
    companyCount("active"),
    companyCount("pending"),
    companyCount("suspended"),
  ]);

  const tiles = [
    { label: "Companies", value: total },
    { label: "Active", value: active },
    { label: "Pending", value: pending },
    { label: "Suspended", value: suspended },
  ];

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {tiles.map((tile) => (
          <Card key={tile.label}>
            <CardHeader>
              <CardDescription>{tile.label}</CardDescription>
              <CardTitle className="text-3xl tabular-nums">{tile.value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}
