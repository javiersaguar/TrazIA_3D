"use client";

import { Ellipsis, Headphones, Mic, Square } from "lucide-react";
import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { Button, Icon } from "@/components/ui/primitives";
import type { CopilotScope } from "@/lib/api/client";
import { useDictation } from "./voice";

type LanguageStatus = "available" | "downloadable" | "downloading" | "unavailable";
// La instalación del paquete requiere una acción explícita del usuario.
type Recognition = {
  processLocally: boolean;
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onspeechstart: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
};
type LocalSpeech = {
  new (): Recognition;
  available?: (options: typeof spanish) => Promise<LanguageStatus>;
  install?: (options: typeof spanish) => Promise<boolean>;
};
const locale = "es-ES";
const spanish = { langs: [locale], processLocally: true as const };

const noSubscription = () => () => {};
/** Silencio tras la última palabra que cierra un turno de conversación. */
export const SILENCIO_FIN_TURNO_MS = 3000;
// Sin voz, Chrome corta el reconocimiento cada pocos segundos; se reanuda unas veces.
const REINTENTOS_SIN_VOZ = 4;

function speech() {
  const browser = window as Window & { SpeechRecognition?: LocalSpeech; webkitSpeechRecognition?: LocalSpeech };
  return browser.SpeechRecognition ?? browser.webkitSpeechRecognition;
}

async function languageStatus() {
  try {
    const browser = speech();
    const status = await browser?.available?.(spanish);
    if (status === "available") return status;
    return browser?.install ? status ?? "unavailable" : "unavailable";
  } catch {
    return "unavailable";
  }
}

function useLocalDictation(onTranscript: (text: string, next: () => Promise<void>) => boolean, conversation = false) {
  const active = useRef<Recognition | null>(null);
  const callback = useRef(onTranscript);
  const quiet = useRef<number | undefined>(undefined);
  // Frases ya reconocidas del turno en curso (conversación).
  const heard = useRef("");
  const [language, setLanguage] = useState<LanguageStatus | null>(null);
  const supported = useSyncExternalStore(noSubscription, () => Boolean(speech()), () => false);
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { callback.current = onTranscript; }, [onTranscript]);
  useEffect(() => {
    let mounted = true;
    void languageStatus().then(status => {
      if (mounted) setLanguage(status);
    });
    return () => {
      mounted = false;
      window.clearTimeout(quiet.current);
      const current = active.current;
      active.current = null;
      current?.abort();
    };
  }, []);

  useEffect(() => {
    if (language !== "downloading") return;
    let mounted = true;
    let timer: number;
    const deadline = Date.now() + 30_000;
    async function checkDownload() {
      const status = await languageStatus();
      if (!mounted) return;
      if (status === "available") setLanguage(status);
      else if (Date.now() < deadline) timer = window.setTimeout(checkDownload, 2_000);
    }
    timer = window.setTimeout(checkDownload, 2_000);
    return () => {
      mounted = false;
      window.clearTimeout(timer);
    };
  }, [language]);

  function deliver(text: string) {
    window.clearTimeout(quiet.current);
    heard.current = "";
    setListening(false);
    setTranscript("");
    if (!text) setError("No he oído voz. Vuelve a pulsar el micrófono.");
    else if (!callback.current(text, () => start())) setError("El dictado no cabe en el mensaje.");
  }

  // El turno se cierra tras SILENCIO_FIN_TURNO_MS sin voz nueva desde la última frase.
  function armTurnEnd() {
    window.clearTimeout(quiet.current);
    quiet.current = window.setTimeout(() => {
      const current = active.current;
      active.current = null;
      current?.abort();
      deliver(heard.current);
    }, SILENCIO_FIN_TURNO_MS);
  }

  function listen(retries: number) {
    const browser = speech();
    if (!browser || language !== "available" || active.current) return;
    try {
      const recognition = new browser();
      if (!("processLocally" in recognition)) throw new Error("Dictado local no disponible.");
      recognition.processLocally = true;
      recognition.lang = locale;
      // El mismo modo que el dictado: una frase por sesión, sin texto provisional. En conversación
      // se encadenan frases y el silencio decide cuándo se envía el turno.
      recognition.continuous = false;
      recognition.interimResults = false;
      let text = "";
      let failed = false;
      recognition.onresult = event => {
        text = Array.from(event.results, alternatives => alternatives[0]?.transcript ?? "")
          .join(" ").replace(/\s+/g, " ").trim();
      };
      // Mientras se habla no corre el reloj del silencio.
      recognition.onspeechstart = () => {
        if (conversation && active.current === recognition) window.clearTimeout(quiet.current);
      };
      recognition.onerror = event => {
        if (active.current !== recognition) return;
        if (conversation && (event.error === "no-speech" || event.error === "aborted")) return;
        failed = true;
        setError(event.error === "not-allowed" ? "Permite el acceso al micrófono para hablar con el Copiloto."
          : event.error === "no-speech" ? "No he oído voz. Vuelve a pulsar el micrófono."
            : event.error === "network" ? "El servicio de voz del navegador no responde. Comprueba la conexión."
              : "No se pudo reconocer la voz. Comprueba el micrófono y vuelve a intentarlo.");
      };
      recognition.onend = () => {
        if (active.current !== recognition) return;
        active.current = null;
        if (failed) {
          window.clearTimeout(quiet.current);
          heard.current = "";
          setListening(false);
          setTranscript("");
          return;
        }
        if (!conversation) {
          deliver(text);
          return;
        }
        if (text) {
          heard.current = `${heard.current} ${text}`.trim();
          setTranscript(heard.current);
        }
        if (heard.current) {
          armTurnEnd();
          listen(0);
        } else if (retries < REINTENTOS_SIN_VOZ) {
          // Aún no ha hablado nadie: se sigue escuchando sin cortar el turno.
          listen(retries + 1);
        } else deliver("");
      };
      active.current = recognition;
      recognition.start();
      setListening(true);
    } catch {
      active.current = null;
      window.clearTimeout(quiet.current);
      heard.current = "";
      setListening(false);
      setError("El navegador no pudo iniciar el reconocimiento de voz.");
    }
  }

  async function start() {
    if (active.current) return;
    heard.current = "";
    setError("");
    setTranscript("");
    listen(0);
  }

  async function install() {
    if (language !== "downloadable") return;
    setLanguage("downloading");
    setError("");
    try {
      const installed = await speech()?.install?.(spanish);
      if (!installed) throw new Error("Paquete no disponible");
      setLanguage("available");
    } catch {
      setLanguage(await languageStatus());
      setError("No se pudo instalar el dictado en español. Puedes reintentarlo o escribir.");
    }
  }

  async function check() {
    setError("");
    setLanguage(await languageStatus());
  }

  return {
    available: supported && language === "available",
    language,
    install,
    check,
    phase: listening ? "recording" as const : "idle" as const,
    transcript,
    error,
    start: () => start(),
    stop: () => active.current?.stop(),
    discard: () => {
      window.clearTimeout(quiet.current);
      heard.current = "";
      const current = active.current;
      active.current = null;
      current?.abort();
      setListening(false);
      setTranscript("");
    },
  };
}

export function useCopilotDictation(
  scope: CopilotScope,
  onTranscript: (text: string, next: () => Promise<void>) => boolean,
  autoTurn = false,
) {
  const cloud = useDictation(scope, onTranscript, autoTurn);
  const local = useLocalDictation(onTranscript, autoTurn);
  const cloudActive = cloud.phase !== "idle" || (local.phase === "idle" && cloud.available);
  return {
    ...(cloudActive ? cloud : local),
    local: !cloudActive,
    language: local.language,
    install: local.install,
    check: local.check,
    error: cloudActive ? cloud.error : local.error || cloud.error,
  };
}

type Dictation = ReturnType<typeof useCopilotDictation>;

export function DictationSetup({ dictation, disabled }: { dictation: Dictation; disabled?: boolean }) {
  if (dictation.available || dictation.phase !== "idle" || dictation.language === null) return null;
  if (dictation.language === "downloadable") return <Button type="button" size="sm" variant="ghost"
    disabled={disabled} onClick={() => void dictation.install()}>Instalar dictado en español</Button>;
  return <div className="flex w-full flex-wrap items-center gap-x-2">
    <p role="status" className="text-xs text-muted">{dictation.language === "downloading"
      ? "El navegador está descargando el paquete de español."
      : "Dictado en español no disponible en este navegador."}</p>
    <Button type="button" size="sm" variant="ghost" disabled={disabled}
      onClick={() => void dictation.check()}>Comprobar dictado</Button>
  </div>;
}

export function DictationControls({ dictation, disabled, onStart, onDesign, onConversation }: {
  dictation: Dictation;
  disabled: boolean;
  onStart: () => void;
  onDesign?: () => void;
  onConversation: () => void;
}) {
  const { phase } = dictation;
  const options = useRef<HTMLDetailsElement>(null);
  const privacy = useId();
  const note = !dictation.local ? "Solo datos sintéticos. El audio se envía a Groq al transcribir."
    : dictation.available ? "El audio se transcribe en este dispositivo."
      : "El dictado requiere el paquete de español del navegador.";
  const recordingDisabled = disabled || phase !== "idle" || !dictation.available;
  function run(action: () => void) {
    if (options.current) options.current.open = false;
    action();
  }
  return <div className="flex max-w-full flex-wrap items-center gap-x-1 gap-y-1">
      <span className="sr-only" id={privacy}>{note}</span>
      <Button type="button" size="sm" variant="ghost" disabled={recordingDisabled} onClick={onStart}
        aria-describedby={privacy} title={note}>
        <Icon icon={Mic} size={16} /> Dictar
      </Button>
      <Button type="button" size="sm" variant="ghost" disabled={disabled || phase !== "idle"} onClick={onConversation}>
        <Icon icon={Headphones} size={16} /> Hablar por voz
      </Button>
      {onDesign ? (
        <details ref={options} className="relative">
          <summary className="grid min-h-9 min-w-8 cursor-pointer list-none place-items-center rounded-lg text-muted hover:bg-surface-raised hover:text-text">
            <Icon icon={Ellipsis} size={17} />
            <span className="sr-only">Opciones de voz</span>
          </summary>
          <div className="absolute bottom-full left-0 z-10 mb-2 grid w-56 gap-0.5 rounded-xl border border-border bg-surface p-1.5 shadow-[var(--shadow-pop)]">
            <Button type="button" variant="ghost" size="sm" disabled={recordingDisabled} className="!justify-start"
              onClick={() => run(onDesign)}><Icon icon={Mic} size={15} /> Dictar un cambio</Button>
            <p className="border-t border-border px-2 py-1.5 text-xs leading-snug text-muted">{note}</p>
          </div>
        </details>
      ) : null}
      {phase === "recording" ? <Button type="button" size="sm" onClick={dictation.stop}>
        <Icon icon={Square} size={14} /> {dictation.local ? "Terminar dictado" : "Transcribir"}
      </Button> : null}
      {phase !== "idle" ? <Button type="button" size="sm" variant="ghost" onClick={dictation.discard}>Cancelar dictado</Button> : null}
    {phase !== "idle" ? <p role="status" className="w-full text-xs text-muted">
      {phase === "permission" ? "Esperando permiso del micrófono…" : phase === "sending" ? "Transcribiendo con Groq…"
        : dictation.local ? "Escuchando…" : "Grabando…"}
    </p> : null}
    {dictation.available && !dictation.local && phase === "idle" ? <p className="w-full text-xs text-muted">Audio de demo · Groq</p> : null}
    <DictationSetup dictation={dictation} disabled={disabled} />
    {dictation.error ? <p role="alert" className="w-full text-xs text-warning">{dictation.error}</p> : null}
  </div>;
}
