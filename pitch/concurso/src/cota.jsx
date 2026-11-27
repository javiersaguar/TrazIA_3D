import { animate, motion } from "motion/react";
import { useEffect, useState } from "react";
import { EXPORT } from "./modo.js";

const formato = (n, decimales = 0) =>
  new Intl.NumberFormat("es-ES", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
    useGrouping: "always",
  }).format(n);

/** Número que cuenta hasta su valor, como si se midiera. */
export function Cuenta({ valor, desde = 0, decimales = 0, delay = 0, duracion = 1.4 }) {
  const [n, setN] = useState(EXPORT ? valor : desde);
  useEffect(() => {
    if (EXPORT) return undefined;
    const ctl = animate(desde, valor, {
      delay,
      duration: duracion,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: setN,
    });
    return () => ctl.stop();
  }, [valor, desde, delay, duracion]);
  return <>{formato(n, decimales)}</>;
}

const ease = [0.2, 0.8, 0.2, 1];

/**
 * Cota horizontal: líneas de referencia en los extremos, línea de cota con flechas y el valor encima.
 * Es el único gesto llamativo de cada lámina: se traza desde el centro y luego aparece la medida.
 */
export function Cota({ ancho, alto = 150, color = "var(--cota)", delay = 0, children, className, style }) {
  const y = alto - 22;
  const f = 16; // longitud de la flecha
  const draw = (d = 0) =>
    EXPORT ? { initial: false } : { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { delay: delay + d, duration: 0.5, ease } };
  return (
    <div className={className} style={{ position: "relative", width: ancho, height: alto, ...style }}>
      <svg width={ancho} height={alto} style={{ position: "absolute", inset: 0, overflow: "visible" }} aria-hidden>
        <motion.line x1={1} y1={alto} x2={1} y2={alto * 0.18} stroke={color} strokeWidth={1.5} {...draw(0)} />
        <motion.line x1={ancho - 1} y1={alto} x2={ancho - 1} y2={alto * 0.18} stroke={color} strokeWidth={1.5} {...draw(0)} />
        <motion.g
          style={{ transformOrigin: `${ancho / 2}px ${y}px` }}
          {...(EXPORT ? { initial: false } : { initial: { scaleX: 0 }, animate: { scaleX: 1 }, transition: { delay: delay + 0.25, duration: 0.7, ease } })}
        >
          <line x1={f} y1={y} x2={ancho - f} y2={y} stroke={color} strokeWidth={2} />
          <path d={`M1 ${y} L${f + 1} ${y - 5.5} L${f + 1} ${y + 5.5} Z`} fill={color} />
          <path d={`M${ancho - 1} ${y} L${ancho - f - 1} ${y - 5.5} L${ancho - f - 1} ${y + 5.5} Z`} fill={color} />
        </motion.g>
      </svg>
      <motion.div
        style={{ position: "absolute", left: 0, right: 0, bottom: 34, display: "flex", justifyContent: "center" }}
        {...(EXPORT ? { initial: false } : { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { delay: delay + 0.55, duration: 0.4 } })}
      >
        {children}
      </motion.div>
    </div>
  );
}
