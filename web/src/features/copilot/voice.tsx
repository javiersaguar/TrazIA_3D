"use client";

import { useQuery } from "@tanstack/react-query";
import { Square, Volume2 } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Button, Icon } from "@/components/ui/primitives";
import { copilotVoiceAvailable, transcribeCopilot, type CopilotScope } from "@/lib/api/client";

const clipSeconds = 20;
// En conversación el turno lo cierra el silencio; se deja más margen para frases largas.
const conversationClipSeconds = 40;
const turnEndSilenceMs = 3000;
// Transcripción parcial para ver el texto mientras se habla. Cada vez se manda todo el audio
// del turno (un webm parcial no se puede trocear); el intervalo respeta el límite de Groq.
const partialEveryMs = 3500;
const maxAudioBytes = 512 * 1024;
const formats = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"];

const subscribeMediaSupport = () => () => {};
const serverMediaType = () => "";
function browserMediaType() {
  if (typeof navigator.mediaDevices?.getUserMedia !== "function" || typeof MediaRecorder === "undefined") return "";
  return formats.find(format => MediaRecorder.isTypeSupported(format)) ?? "";
}

type Capture = {
  request: AbortController;
  stream?: MediaStream;
  recorder?: MediaRecorder;
  timer?: number;
  partials?: number;
  heard?: boolean;
  stopMeter?: () => void;
};
type Phase = "idle" | "permission" | "recording" | "sending";

function release(capture: Capture) {
  window.clearTimeout(capture.timer);
  window.clearInterval(capture.partials);
  capture.stopMeter?.();
  capture.stopMeter = undefined;
  capture.stream?.getTracks().forEach(track => track.stop());
}

function cancel(capture: Capture) {
  capture.request.abort();
  if (capture.recorder) {
    capture.recorder.ondataavailable = null;
    capture.recorder.onstop = null;
    capture.recorder.onerror = null;
    if (capture.recorder.state !== "inactive") capture.recorder.stop();
  }
  release(capture);
}

function detectTurnEnd(stream: MediaStream, onEnd: () => void, onIdle: () => void, onVoice: () => void) {
  if (typeof AudioContext === "undefined") return undefined;
  const context = new AudioContext();
  const analyser = context.createAnalyser();
  const muted = context.createGain();
  analyser.fftSize = 1024;
  muted.gain.value = 0;
  context.createMediaStreamSource(stream).connect(analyser);
  analyser.connect(muted).connect(context.destination);
  void context.resume().catch(() => {});

  const samples = new Float32Array(analyser.fftSize);
  const started = performance.now();
  let voicedFrames = 0;
  let lastVoice = 0;
  const timer = window.setInterval(() => {
    if (context.state !== "running") return;
    analyser.getFloatTimeDomainData(samples);
    let energy = 0;
    for (const sample of samples) energy += sample * sample;
    const now = performance.now();
    if (Math.sqrt(energy / samples.length) > 0.018) {
      voicedFrames += 1;
      if (voicedFrames >= 3) {
        lastVoice = now;
        onVoice();
      }
    } else {
      voicedFrames = 0;
      if (lastVoice && now - lastVoice >= turnEndSilenceMs) onEnd();
      else if (!lastVoice && now - started >= 8000) onIdle();
    }
  }, 50);
  return () => {
    window.clearInterval(timer);
    void context.close().catch(() => {});
  };
}

export function useDictation(
  scope: CopilotScope,
  onTranscript: (text: string, startNextTurn: () => Promise<void>) => boolean,
  autoTurn = false,
) {
  const mediaType = useSyncExternalStore(subscribeMediaSupport, browserMediaType, serverMediaType);
  const [phase, setPhase] = useState<Phase>("idle");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState("");
  const active = useRef<Capture | null>(null);
  // La grabación termina varios renders después de empezar: siempre se avisa al callback vigente.
  const callback = useRef(onTranscript);
  useEffect(() => { callback.current = onTranscript; }, [onTranscript]);
  const supported = scope.kind === "revision" || scope.kind === "process";
  const { data: available } = useQuery({
    queryKey: ["copilot-voice", scope.kind, scope.id],
    queryFn: ({ signal }) => copilotVoiceAvailable(scope, signal),
    enabled: supported && Boolean(mediaType),
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => () => {
    if (active.current) cancel(active.current);
    active.current = null;
  }, []);

  const finish = (capture: Capture) => {
    if (capture.recorder?.state === "recording") capture.recorder.stop();
    release(capture);
  };

  async function start(): Promise<void> {
    if (!available || active.current) return;
    const capture: Capture = { request: new AbortController() };
    const { signal } = capture.request;
    active.current = capture;
    setPhase("permission");
    setError("");
    setTranscript("");
    try {
      capture.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (cause) {
      if (signal.aborted) return;
      active.current = null;
      setPhase("idle");
      setError(cause instanceof DOMException && cause.name === "NotAllowedError"
        ? "Permite el acceso al micrófono para dictar."
        : "No se pudo acceder al micrófono.");
      return;
    }
    if (signal.aborted) {
      release(capture);
      return;
    }
    try {
      const recorder = new MediaRecorder(capture.stream, { mimeType: mediaType, audioBitsPerSecond: 48_000 });
      const chunks: Blob[] = [];
      capture.recorder = recorder;
      recorder.ondataavailable = event => chunks.push(event.data);
      recorder.onerror = () => {
        cancel(capture);
        active.current = null;
        setPhase("idle");
        setError("No se pudo completar la grabación.");
      };
      recorder.onstop = async () => {
        release(capture);
        if (signal.aborted) return;
        setPhase("sending");
        try {
          const audio = new Blob(chunks, { type: recorder.mimeType || mediaType });
          if (!audio.size) throw new Error("La grabación está vacía.");
          if (audio.size > maxAudioBytes) throw new Error("La grabación es demasiado grande. Prueba un clip más corto.");
          const text = await transcribeCopilot(scope, audio, signal);
          if (!signal.aborted && !callback.current(text, start)) throw new Error("El dictado no cabe en el mensaje. Deja espacio y vuelve a intentarlo.");
        } catch (cause) {
          if (!signal.aborted) setError(cause instanceof Error ? cause.message : "No se pudo transcribir el audio.");
        } finally {
          if (!signal.aborted) {
            active.current = null;
            setPhase("idle");
            setTranscript("");
          }
        }
      };
      recorder.start(autoTurn ? 1000 : undefined);
      capture.timer = window.setTimeout(() => finish(capture), (autoTurn ? conversationClipSeconds : clipSeconds) * 1000);
      if (autoTurn) {
        capture.stopMeter = detectTurnEnd(capture.stream, () => finish(capture), () => {
          cancel(capture);
          active.current = null;
          setPhase("idle");
          setError("No he oído voz. Pulsa Hablar para reanudar.");
        }, () => { capture.heard = true; });
        let sent = 0;
        let waiting = false;
        capture.partials = window.setInterval(async () => {
          if (waiting || !capture.heard || chunks.length === sent || recorder.state !== "recording") return;
          waiting = true;
          sent = chunks.length;
          try {
            const text = await transcribeCopilot(scope, new Blob(chunks, { type: recorder.mimeType || mediaType }), signal);
            if (!signal.aborted && recorder.state === "recording") setTranscript(text.trim());
          } catch {
            // Un parcial fallido no corta el turno: la transcripción final se pide igual.
            window.clearInterval(capture.partials);
          } finally {
            waiting = false;
          }
        }, partialEveryMs);
      }
      setPhase("recording");
    } catch {
      cancel(capture);
      active.current = null;
      setPhase("idle");
      setError("No se pudo iniciar la grabación.");
    }
  }

  return {
    available: available === true || phase !== "idle",
    phase,
    transcript,
    error,
    start,
    stop: () => { if (active.current) finish(active.current); },
    discard: () => {
      setTranscript("");
      if (!active.current) return;
      cancel(active.current);
      active.current = null;
      setPhase("idle");
    },
  };
}

export function useLocalSpeech() {
  const [voice, setVoice] = useState<SpeechSynthesisVoice>();
  const [playing, setPlaying] = useState(false);
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  useEffect(() => {
    const synthesis = window.speechSynthesis;
    if (!synthesis || typeof SpeechSynthesisUtterance === "undefined") return;
    const refresh = () => {
      // Primero una voz local de España; si no hay, cualquier voz en español del navegador.
      const voices = synthesis.getVoices().filter(item => /^es(?:[-_]|$)/i.test(item.lang));
      const rank = (item: SpeechSynthesisVoice) =>
        (item.localService ? 0 : 2) + (item.lang.toLowerCase().replace("_", "-") === "es-es" ? 0 : 1);
      setVoice([...voices].sort((x, y) => rank(x) - rank(y))[0]);
    };
    refresh();
    synthesis.addEventListener("voiceschanged", refresh);
    return () => {
      synthesis.removeEventListener("voiceschanged", refresh);
      if (utterance.current) {
        utterance.current.onstart = null;
        utterance.current.onend = null;
        utterance.current.onerror = null;
        utterance.current = null;
        synthesis.cancel();
      }
    };
  }, []);

  function stop() {
    const speech = utterance.current;
    if (!speech) return;
    speech.onstart = speech.onend = speech.onerror = null;
    utterance.current = null;
    window.speechSynthesis.cancel();
    setPlaying(false);
  }

  function speak(text: string, complete?: (ok: boolean) => void) {
    if (!voice || !text) return false;
    stop();
    const speech = new SpeechSynthesisUtterance(text);
    speech.voice = voice;
    speech.lang = voice.lang;
    speech.onstart = () => setPlaying(true);
    const finish = (ok: boolean) => {
      utterance.current = null;
      setPlaying(false);
      complete?.(ok);
    };
    speech.onend = () => finish(true);
    speech.onerror = () => finish(false);
    utterance.current = speech;
    window.speechSynthesis.speak(speech);
    return true;
  }

  return { voice, playing, stop, speak };
}

export function ReadAnswer({ text }: { text: string }) {
  const { voice, playing, speak, stop } = useLocalSpeech();
  if (!voice || !text) return null;
  const toggle = () => { if (playing) stop(); else speak(text); };
  return <Button type="button" size="sm" onClick={toggle}>
    <Icon icon={playing ? Square : Volume2} size={14} /> {playing ? "Detener lectura" : "Escuchar respuesta"}
  </Button>;
}
