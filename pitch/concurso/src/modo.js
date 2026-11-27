// Modo de la presentación. Con ?export las láminas se pintan ya en su estado final.
const params = new URLSearchParams(window.location.search);

export const EXPORT = params.has("export");

/** Props de motion para una entrada con retardo; en exportación no anima. */
export function entra(delay = 0, desde = { opacity: 0 }) {
  if (EXPORT) return { initial: false };
  return {
    initial: desde,
    animate: { opacity: 1, x: 0, y: 0, scaleX: 1, scaleY: 1 },
    transition: { delay, duration: 0.6, ease: [0.2, 0.8, 0.2, 1] },
  };
}
