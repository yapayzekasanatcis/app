import { motion } from "framer-motion";

/**
 * NOVA avatar orb — reactive to states.
 * state: 'idle' | 'listening' | 'thinking' | 'speaking'
 */
export const NovaOrb = ({ state = "idle", size = 220, label = "NOVA Rölantide" }) => {
  const stateLabels = {
    idle: "Rölantide",
    listening: "Dinliyor",
    thinking: "Düşünüyor",
    speaking: "Konuşuyor",
  };
  return (
    <div className="flex flex-col items-center gap-6" data-testid="nova-orb-wrap">
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className={`nova-orb ${state}`}
        style={{ width: size, height: size }}
        data-testid="nova-orb"
        data-state={state}
      />
      <div className="text-center">
        <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">NOVA</div>
        <div className="font-serif-display text-xl text-[color:var(--nova-text)] mt-1">
          {stateLabels[state] || label}
        </div>
      </div>
    </div>
  );
};

export default NovaOrb;
