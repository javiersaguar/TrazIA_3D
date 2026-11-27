"use client";

import { motion, type Variants } from "motion/react";
import Link from "next/link";

import { LogoMark, LogoWordmark } from "@/components/brand/logo";
import { EASE_OUT } from "@/components/motion/reveal";
import { Spotlight } from "@/components/motion/spotlight";
import { LiveDot } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { IntroOverlay, useIntro } from "./intro";
import { LANDING_REFERENCE, type ReferenceModel } from "./landing-reference";
import { LoginCard } from "./login-card";
import { ReferenceSheet } from "./reference-sheet";
import { SignedInCard, type LandingAccount } from "./signed-in-card";
import { RotatingLine } from "./rotating-line";

const hero: Variants = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.07, delayChildren: 0.15 } },
};
const rise: Variants = {
  hidden: { opacity: 0, transform: "translateY(16px)" },
  shown: { opacity: 1, transform: "translateY(0)" , transition: { duration: 0.6, ease: EASE_OUT } },
};

/** Lleva al formulario de acceso y pone el foco en el usuario. */
function focusLogin() {
  const input = document.getElementById("acceso-usuario");
  input?.focus({ preventScroll: true });
  input?.scrollIntoView({ block: "nearest" });
}

const headerAction = "inline-flex h-9 items-center whitespace-nowrap rounded-[10px] border border-border-strong bg-surface-raised px-2.5 text-[13px] text-text transition-colors hover:border-accent/60 sm:px-3.5 sm:text-[14px]";

function LandingHeader({ introActive, signedIn }: { introActive: boolean; signedIn: boolean }) {
  return (
    <header className="z-40 shrink-0 border-b border-border/70 bg-bg/75 backdrop-blur-md">
      <div className="mx-auto flex h-16 w-full max-w-[1240px] items-center gap-2 px-4 sm:gap-4 sm:px-5 md:px-8">
        <Link href="/" aria-label="TrazIA 3D, inicio" className="mr-auto flex shrink-0 items-center gap-2 rounded-[8px] sm:gap-3">
          <span data-intro-target="mark" style={{visibility:introActive?"hidden":"visible"}} className="block size-8 sm:size-9"><LogoMark className="size-full" /></span>
          <span data-intro-target="word" style={{visibility:introActive?"hidden":"visible"}} className="block h-3 sm:h-[15px]"><LogoWordmark className="h-full w-auto" /></span>
        </Link>
        <Link href="/demo/v-101" prefetch={false} aria-label="Abrir demo V-101"
          className="inline-flex h-9 items-center gap-1.5 whitespace-nowrap rounded-[10px] px-2 text-[13px] text-muted hover:bg-surface-raised hover:text-text sm:px-3 sm:text-[14px]">
          Demo <span className="hidden font-mono sm:inline">V-101</span>
        </Link>
        {signedIn ? (
          <Link href="/documentos" className={headerAction}>
            Ir a la app
          </Link>
        ) : (
          <button
            type="button"
            onClick={focusLogin}
            className={headerAction}
          >
            Iniciar sesión
          </button>
        )}
      </div>
    </header>
  );
}

export function LandingPage({ fontClassName, account = null, model = LANDING_REFERENCE }: { fontClassName?: string; account?: LandingAccount | null; model?: ReferenceModel }) {
  const signedIn = account != null && account.role !== "guest";
  const { phase, fly, finish } = useIntro();
  const play = phase !== "assembling";
  const ready = phase === "ready";

  return (
    <div className={cn("flex min-h-dvh flex-col bg-bg text-text", fontClassName)} data-intro-phase={phase}>
      <IntroOverlay phase={phase} onFly={fly} onReady={finish} />
      <LandingHeader introActive={!ready} signedIn={signedIn} />

      <Spotlight size={680} />
      <main className="relative flex flex-1">
        <section aria-labelledby="hero-titulo" className="relative grid w-full">
          <div
            aria-hidden
            className="landing-paper pointer-events-none absolute inset-0 opacity-70 [mask-image:radial-gradient(65%_70%_at_72%_35%,#000,transparent)]"
          />
          <div className="relative mx-auto grid w-full max-w-[1240px] content-center items-center gap-8 px-5 py-6 md:px-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-12 landing-compact:py-3">
            <motion.div variants={hero} initial="hidden" animate={play ? "shown" : "hidden"} className="flex min-w-0 flex-col">
              <motion.p variants={rise} className="flex items-center gap-2.5 text-[13px] text-muted">
                <LiveDot /> Reto GA2MODEL de Técnicas Reunidas
              </motion.p>
              <motion.h1 variants={rise} id="hero-titulo" className="landing-display mt-4 text-[clamp(46px,6.4vw,88px)] leading-[0.94] text-strong landing-compact:mt-3 landing-compact:text-[clamp(34px,7vw,56px)]">
                Del plano al modelo 3D,
                <RotatingLine play={play} className="mt-3 block text-[clamp(22px,2.5vw,34px)] leading-tight text-muted landing-compact:mt-2 landing-compact:text-[clamp(18px,3vw,25px)]" />
              </motion.h1>
              <motion.p variants={rise} className="mt-[clamp(12px,2.6dvh,24px)] max-w-[50ch] text-base leading-relaxed text-muted landing-compact:mt-3 landing-compact:max-w-none landing-compact:text-sm">
                TrazIA-3D lee los planos de disposición general de recipientes, genera el modelo IFC y guarda de qué parte
                del plano sale cada dato. Cuando llega una revisión, enseña qué ha cambiado.
              </motion.p>
              <motion.div variants={rise} className="mt-[clamp(16px,3dvh,32px)] w-full max-w-[440px] landing-compact:mt-4">
                {signedIn ? <SignedInCard account={account!} /> : <LoginCard />}
              </motion.div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, transform: "translateY(18px)" }}
              animate={play ? { opacity: 1, transform: "translateY(0)" } : { opacity: 0, transform: "translateY(18px)" }}
              transition={{ duration: 0.8, delay: 0.1, ease: EASE_OUT }}
              className="min-w-0"
            >
              <ReferenceSheet play={ready} model={model} />
            </motion.div>
          </div>
        </section>
      </main>
    </div>
  );
}
