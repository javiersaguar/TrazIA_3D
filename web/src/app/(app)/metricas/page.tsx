import { AdminOnly } from "@/components/shell/admin-only";
import { MetricsDashboard } from "@/features/admin/metrics";

export const metadata = { title: "Métricas" };

export default function Page() {
  return (
    <AdminOnly>
      <MetricsDashboard />
    </AdminOnly>
  );
}
