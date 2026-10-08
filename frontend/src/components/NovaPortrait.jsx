import { motion } from "framer-motion";

const PORTRAIT_SRC = "/nova-portrait.webp";

export const NovaPortrait = ({
  state = "idle",
  variant = "portrait",
  width = 170,
  showLabel = true,
  testId = "nova-portrait",
  priority = false,
}) => {
  const labels = {
    idle: "Hazır",
    listening: "Dinliyor",
    thinking: "Düşünüyor",
    speaking: "Konuşuyor",
  };
  const isAvatar = variant === "avatar";

  return (
    <div className={`nova-portrait-wrap ${isAvatar ? "is-avatar" : ""}`} data-testid={`${testId}-wrap`}>
      <motion.div
        initial={{ opacity: 0, y: isAvatar ? 0 : 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: "easeOut" }}
        className={`nova-portrait-frame ${isAvatar ? "nova-avatar-frame" : ""} ${state}`}
        style={{ width }}
        data-testid={testId}
        data-state={state}
      >
        <img
          src={PORTRAIT_SRC}
          alt="NOVA resmi yönetici asistanı portresi"
          className="nova-portrait-image"
          loading={priority ? "eager" : "lazy"}
          fetchPriority={priority ? "high" : "auto"}
          decoding="async"
        />
      </motion.div>
      {showLabel && (
        <div className="text-center" data-testid={`${testId}-identity`}>
          <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">NOVA</div>
          <div className="font-serif-display text-xl text-[color:var(--nova-text)] mt-1" data-testid={`${testId}-status`}>
            {labels[state] || labels.idle}
          </div>
        </div>
      )}
    </div>
  );
};

export default NovaPortrait;