import type { Metadata } from "next";

import { display } from "@/features/landing/fonts";
import { LANDING_REFERENCE } from "@/features/landing/landing-reference";
import { LandingPage } from "@/features/landing/landing-page";
import { serverAccount } from "@/lib/account-server";
import { accountsEnabled } from "@/lib/api/config";

export const metadata: Metadata = {
  title: { absolute: "TrazIA-3D · del plano al modelo 3D" },
};

export default async function Home() {
  const account = accountsEnabled ? await serverAccount() : null;
  return <LandingPage fontClassName={display.variable} account={account} model={LANDING_REFERENCE} />;
}
