import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { WorkspaceShell } from "@/components/shell/workspace-shell";
import { AccountProvider } from "@/lib/accounts";
import { serverAccount } from "@/lib/account-server";
import { accountsEnabled } from "@/lib/api/config";
import { GuestWorkspace } from "@/components/shell/guest-workspace";

export default async function AppLayout({ children }: { children: ReactNode }) {
  if (!accountsEnabled) return <WorkspaceShell>{children}</WorkspaceShell>;
  const account = await serverAccount();
  if (!account) redirect("/#acceso-usuario");
  return (
    <AccountProvider account={account}>
      {account.role === "guest" ? <GuestWorkspace>{children}</GuestWorkspace> : <WorkspaceShell>{children}</WorkspaceShell>}
    </AccountProvider>
  );
}
