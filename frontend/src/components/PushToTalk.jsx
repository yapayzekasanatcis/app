import { useRef, useState } from "react";
import { Mic, Square, Loader2 } from "lucide-react";
import { voiceApi, chatApi } from "@/lib/api";
import { toast } from "sonner";

/**
 * Push-to-talk button: records audio while held, releases to send to STT -> chat -> TTS playback.
 * Props: onState(state), onReply(text)
 */
export const PushToTalk = ({ onState, onReply }) => {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const mediaRef = useRef(null);
  const chunksRef = useRef([]);
  const audioRef = useRef(null);

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setBusy(true);
        onState?.("thinking");
        try {
          const { text } = await voiceApi.stt(blob);
          if (!text?.trim()) {
            toast.info("Ses algılanamadı");
            onState?.("idle");
            return;
          }
          toast.message("Bora Bey", { description: text });
          const { answer } = await chatApi.send(text);
          onReply?.({ question: text, answer });
          onState?.("speaking");
          try {
            const audioBlob = await voiceApi.tts(answer);
            const url = URL.createObjectURL(audioBlob);
            if (audioRef.current) audioRef.current.pause();
            audioRef.current = new Audio(url);
            audioRef.current.onended = () => onState?.("idle");
            audioRef.current.play();
          } catch (err) {
            console.error("TTS failed", err);
            onState?.("idle");
          }
        } catch (e) {
          toast.error("NOVA yanıt veremedi", { description: e?.response?.data?.detail || e.message });
          onState?.("idle");
        } finally {
          setBusy(false);
        }
      };
      mr.start();
      mediaRef.current = mr;
      setRecording(true);
      onState?.("listening");
    } catch (e) {
      toast.error("Mikrofona erişilemedi", { description: "Lütfen mikrofon izni verin." });
      onState?.("idle");
    }
  };

  const stop = () => {
    if (mediaRef.current && mediaRef.current.state !== "inactive") {
      mediaRef.current.stop();
    }
    setRecording(false);
  };

  const toggle = () => (recording ? stop() : start());

  return (
    <button
      onClick={toggle}
      disabled={busy && !recording}
      data-testid="push-to-talk-button"
      className={`group relative inline-flex items-center justify-center h-16 w-16 md:h-20 md:w-20 rounded-full
        ${recording ? "bg-red-500/90" : "bg-[color:var(--nova-amber)]"}
        text-black shadow-[0_0_40px_-5px_rgba(245,158,11,0.6)]
        hover:scale-105 active:scale-95 transition-transform disabled:opacity-60`}
      aria-label="Bas konuş"
    >
      {busy ? (
        <Loader2 className="h-7 w-7 animate-spin" />
      ) : recording ? (
        <Square className="h-7 w-7" fill="currentColor" />
      ) : (
        <Mic className="h-7 w-7" />
      )}
      {recording && (
        <span className="absolute -inset-2 rounded-full border border-red-400/70 animate-ping" />
      )}
    </button>
  );
};

export default PushToTalk;
