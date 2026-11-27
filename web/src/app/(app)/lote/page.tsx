import { AdminOnly } from "@/components/shell/admin-only";
import { ExportsWorkspace } from "@/features/admin/exports";

export const metadata = { title: "Lotes e informes" };

export default function Page() {
  return (
    <AdminOnly>
      <ExportsWorkspace />
    </AdminOnly>
  );
}
