// Shared framer-motion config so card focus, the hero, and the modal all move
// with the same calm Apple-TV spring instead of ad-hoc easeOut/cubic-beziers.
import type { Transition, Variants } from "framer-motion";

/** The one spring. Use for focus/hover lifts, modal, hero entrances. */
export const springy: Transition = {
  type: "spring",
  stiffness: 380,
  damping: 30,
};

/** Slightly softer spring for larger surfaces (modal panel, hero). */
export const softSpring: Transition = {
  type: "spring",
  stiffness: 260,
  damping: 28,
};

/** Card poster focus transform (lift + scale). */
export const cardTransition: Transition = springy;

/** Fade + rise entrance used by modals / panels. */
export const riseIn: Variants = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 24 },
};

/** Simple crossfade. */
export const fade: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1 },
  exit: { opacity: 0 },
};
