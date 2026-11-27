import "server-only";
import { cookies } from "next/headers";
import type { Account } from "./accounts";

export async function serverAccount(): Promise<Account | null> {
  const token = (await cookies()).get("trazia_session")?.value;
  const origin = process.env.TRAZIA_API_ORIGIN?.trim().replace(/\/+$/, "");
  if (!origin || !token || !/^[A-Za-z0-9_-]{43}$/.test(token)) return null;
  try {
    const response = await fetch(`${origin}/auth/session`, {
      headers: { Cookie: `trazia_session=${token}` },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(4000),
    });
    return response.ok ? await response.json() as Account : null;
  } catch {
    return null;
  }
}
