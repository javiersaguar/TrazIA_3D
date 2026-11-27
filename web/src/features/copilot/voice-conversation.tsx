"use client";

import { ArrowLeft, LoaderCircle, Mic, MicOff } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { CopilotMark } from "@/components/brand/copilot-mark";
import { Button, Icon } from "@/components/ui/primitives";
import { askCopilot, type CopilotAnswer, type CopilotScope } from "@/lib/api/client";
import { DictationSetup, SILENCIO_FIN_TURNO_MS, useCopilotDictation } from "./dictation";
import { isChangeRequest } from "./intent";
import { useLocalSpeech } from "./voice";
import styles from "./voice-conversation.module.css";

const VoiceAvatar = dynamic(() => import("./voice-avatar"), {
  ssr: false,
  loading: () => <CopilotMark className={styles.placeholder} />,
});

/** Respuesta a una orden dictada: `leaving` indica que se abre el editor y la sesión de voz termina. */
export type VoiceDesignReply = { reply: string; leaving: boolean };

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

const captions: Record<AvatarState, string> = {
  idle: "Micrófono en pausa",
  listening: "Te escucho",
  thinking: "Consultando las fuentes",
  speaking: "Respondiendo",
};

const pause = `${SILENCIO_FIN_TURNO_MS / 1000} segundos`;

export function VoiceConversation({ scope, revision, path, onDesign, onTurn, turnCount, onClose, children }: {
  scope: CopilotScope;
  revision: "A" | "B";
  path?: string;
  onDesign?: (text: string) => Promise<VoiceDesignReply>;
  /** Cada turno respondido pasa al hilo del chat, que sigue ahí al volver a texto. */
  onTurn: (text: string, answer: CopilotAnswer) => void;
  turnCount: number;
  onClose: () => void;
  /** Hilo del chat con los turnos ya respondidos. */
  children?: ReactNode;
}) {
  const [responding, setResponding] = useState(false);
  const [error, setError] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const session = useRef<AbortController | null>(null);
  const dictatingDesign = useRef(false);
  const rearm = useRef<number | undefined>(undefined);
  const end = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const { voice, playing, speak, stop } = useLocalSpeech();
  // Las voces del navegador cargan después del primer render y el turno se resuelve más tarde:
  // la respuesta usa siempre la voz disponible en ese momento.
  const speech = useRef({ voice, speak });
  useEffect(() => { speech.current = { voice, speak }; }, [voice, speak]);

  useEffect(() => () => {
    session.current?.abort();
    window.clearTimeout(rearm.current);
  }, []);

  async function respond(text: string, startNextTurn: () => Promise<void>) {
    const turn = new AbortController();
    session.current = turn;
    setResponding(true);
    setAsked(text);
    const listenAgain = () => {
      rearm.current = window.setTimeout(() => {
        if (turn.signal.aborted) return;
        session.current = null;
        setResponding(false);
        void startNextTurn();
      }, 240);
    };
    try {
      const result = await askCopilot(scope, text, path, turn.signal, revision);
      if (turn.signal.aborted) return;
      const reply = result.abstained
        ? result.reason || "No encontré evidencia suficiente para responder."
        : result.statements.map(statement => statement.text).join("\n") || "No encontré una respuesta respaldada.";
      setAsked(null);
      onTurn(text, result);
      const { voice, speak } = speech.current;
      if (!voice) {
        // Sin voz en español la respuesta queda escrita y se vuelve a escuchar.
        listenAgain();
        return;
      }
      if (!speak(reply, ok => {
        if (turn.signal.aborted) return;
        if (ok) listenAgain();
        else {
          session.current = null;
          setResponding(false);
          setError("No se pudo leer la respuesta en voz alta; queda escrita en el chat.");
        }
      })) listenAgain();
    } catch (cause) {
      if (turn.signal.aborted) return;
      session.current = null;
      setResponding(false);
      setAsked(null);
      setError(cause instanceof Error ? cause.message : "No se pudo consultar el Copiloto.");
    }
  }

  /** Una orden de cambio no pasa por el Copiloto: se prepara y, si está completa, se abre el editor. */
  async function change(text: string, design: (text: string) => Promise<VoiceDesignReply>, startNextTurn: () => Promise<void>) {
    const turn = new AbortController();
    session.current = turn;
    setResponding(true);
    setAsked(text);
    setPreparing(true);
    dictatingDesign.current = false;
    try {
      const { reply, leaving } = await design(text);
      if (turn.signal.aborted) return;
      setAsked(null);
      setPreparing(false);
      if (leaving) {
        // La página cambia al editor: la confirmación se dice fuera del ciclo de vida del componente.
        stop();
        const { voice } = speech.current;
        if (voice && typeof SpeechSynthesisUtterance !== "undefined") {
          const said = new SpeechSynthesisUtterance(reply);
          said.voice = voice;
          said.lang = voice.lang;
          window.speechSynthesis.speak(said);
        }
        session.current = null;
        return;
      }
      // Falta un dato: se pregunta en voz alta y se vuelve a escuchar como orden.
      dictatingDesign.current = true;
      const again = () => {
        rearm.current = window.setTimeout(() => {
          if (turn.signal.aborted) return;
          session.current = null;
          setResponding(false);
          void startNextTurn();
        }, 240);
      };
      if (!speech.current.speak(reply, ok => { if (!turn.signal.aborted && ok) again(); else if (!turn.signal.aborted) setResponding(false); })) again();
    } catch (cause) {
      if (turn.signal.aborted) return;
      session.current = null;
      setResponding(false);
      setAsked(null);
      setPreparing(false);
      setError(cause instanceof Error ? cause.message : "No se pudo preparar el cambio.");
    }
  }

  const dictation = useCopilotDictation(scope, (text, startNextTurn) => {
    if (onDesign && (dictatingDesign.current || isChangeRequest(text))) {
      if (text.length > 2000) return false;
      void change(text, onDesign, startNextTurn);
      return true;
    }
    void respond(text, startNextTurn);
    return true;
  }, true);

  function hold() {
    session.current?.abort();
    session.current = null;
    window.clearTimeout(rearm.current);
    stop();
    dictation.discard();
    setResponding(false);
    setAsked(null);
    setPreparing(false);
  }

  function listen(design = false) {
    dictatingDesign.current = design;
    setError("");
    void dictation.start();
  }

  // Al entrar en modo voz se empieza a escuchar sin pulsar nada más.
  // El temporizador se cancela si el efecto se limpia antes (montaje doble en desarrollo), para
  // no dejar una grabación a medias que el desmontaje ya ha cancelado.
  useEffect(() => {
    if (!dictation.available) return;
    const timer = window.setTimeout(() => {
      if (started.current) return;
      started.current = true;
      listen();
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dictation.available]);

  const listening = dictation.phase === "recording";
  const transcribing = dictation.phase === "sending";
  const pending = responding || transcribing;
  const permission = dictation.phase === "permission";
  const active = pending || permission || listening;
  const state: AvatarState = playing ? "speaking" : pending ? "thinking" : listening ? "listening" : "idle";
  const status = permission ? "Esperando permiso del micrófono"
    : transcribing ? "Transcribiendo lo que has dicho" : captions[state];
  const live = (listening || transcribing) ? dictation.transcript : "";

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [turnCount, asked, live, listening]);

  return <div className="space-y-4">
    <section className={styles.session} aria-label="Conversación por voz" data-compact={turnCount > 0 || Boolean(asked)}>
      <div className={styles.stage} data-state={state}>
        <VoiceAvatar state={state} />
      </div>
      <p className={styles.status} role="status"><span aria-hidden="true" />{status}</p>
      {error || dictation.error ? <p role="alert" className="px-3 text-center text-xs text-warning">{error || dictation.error}</p> : null}
      <p className="px-3 text-center text-xs text-muted">
        {listening ? `Habla con normalidad: respondo cuando hagas una pausa de ${pause}.`
          : onDesign ? "Pregunta por una cota o pide un cambio («sube la boquilla N1 200 mm»): el cambio se prepara y se abre en el editor para confirmarlo."
            : "Pregunta por una cota o por los documentos de la revisión."}
      </p>
      {!voice ? <p className="px-3 text-center text-xs text-muted">El navegador no tiene voz en español: las respuestas quedan escritas en el chat.</p> : null}
      <div className="flex flex-wrap items-center justify-center gap-2 px-3">
        {playing ? <Button type="button" size="sm" onClick={() => { hold(); listen(); }}>
          <Icon icon={Mic} size={14} /> Interrumpir y hablar
        </Button> : null}
        {active ? <Button type="button" size="sm" onClick={hold}>
          <Icon icon={MicOff} size={14} /> Pausar
        </Button> : <Button type="button" variant="primary" size="sm" onClick={() => listen()} disabled={!dictation.available}>
          <Icon icon={Mic} size={14} /> Hablar
        </Button>}
        {onDesign && !active && !playing && dictation.available ? <Button type="button" size="sm" onClick={() => listen(true)}>
          <Icon icon={Mic} size={14} /> Dictar un cambio
        </Button> : null}
        <DictationSetup dictation={dictation} />
      </div>
      <Button className="mx-auto" type="button" variant="ghost" size="sm" onClick={() => { hold(); onClose(); }}>
        <Icon icon={ArrowLeft} size={14} /> Volver a texto
      </Button>
    </section>
    {children}
    {asked ? <div className="space-y-3">
      <p className={styles.said}><span className="sr-only">Tú: </span>{asked}</p>
      <p role="status" className="flex items-center gap-2 text-muted">
        <Icon icon={LoaderCircle} size={15} className="motion-safe:animate-spin text-accent-text" /> {preparing ? "Preparando el cambio…" : "Consultando las fuentes…"}
      </p>
    </div> : null}
    {listening || transcribing ? <p className={styles.live} aria-live="polite" data-empty={!live}>
      <span className="sr-only">Transcripción en curso: </span>
      {live || (transcribing ? "Transcribiendo…" : "Te escucho…")}
    </p> : null}
    <div ref={end} />
  </div>;
}
