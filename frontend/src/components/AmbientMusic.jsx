import { useEffect, useRef, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";
import { toast } from "sonner";

export default function AmbientMusic({ novaState }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !playing) return;

    audio.volume = novaState === "speaking" ? 0.05 : 0.14;
  }, [novaState, playing]);


  const toggle = async () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (playing) {
      audio.pause();
      setPlaying(false);
      return;
    }

    try {
      audio.volume = 0.14;
      await audio.play();
      setPlaying(true);
    } catch {
      toast.info("NOVA ortam müziği henüz eklenmedi.");
    }
  };

  return (
    <>
      <audio
        ref={audioRef}
        src="/nova-ambient.mp3"
        loop
        preload="none"
        onEnded={() => setPlaying(false)}
      />

      <button
        type="button"
        onClick={toggle}
        className="fixed bottom-5 right-5 lg:right-[410px] z-30 h-10 px-3 rounded-full
                   nova-glass text-[color:var(--nova-text-2)]
                   hover:text-[color:var(--nova-amber)] transition-colors
                   flex items-center gap-2 text-xs"
        title={playing ? "Ortam müziğini kapat" : "Ortam müziğini aç"}
      >
        {playing ? (
          <Volume2 className="h-4 w-4 text-[color:var(--nova-amber)]" />
        ) : (
          <VolumeX className="h-4 w-4" />
        )}
        <span className="hidden sm:inline">
          {playing ? "Atmosfer açık" : "Atmosfer"}
        </span>
      </button>
    </>
  );
}
