import { useId } from "react";
import { TR_MARK_PIECES, TR_VIEWBOX, TR_WORD_LETTERS } from "../../../web/src/components/brand/tr-logo-geometry.ts";
import { FULL_VIEWBOX, LOGO_FACES, WORD_VIEWBOX } from "../../../web/src/components/brand/logo-geometry.ts";
import { MULTIPLICA_PATHS, MULTIPLICA_VIEWBOX } from "./logo-multiplica.js";

/** Logo de Técnicas Reunidas en un solo color, como se usa en la portada del producto. */
export function LogoTR({ color = "var(--logo-ink-hi)", className, style }) {
  return (
    <svg viewBox={TR_VIEWBOX} className={className} style={style} role="img" aria-label="Técnicas Reunidas">
      {[...TR_MARK_PIECES, ...TR_WORD_LETTERS].map((d, i) => (
        <path key={i} d={d} fill={color} fillRule="evenodd" />
      ))}
    </svg>
  );
}

/** Logo de Multiplica en un solo color. */
export function LogoMultiplica({ color = "var(--logo-ink-hi)", className, style }) {
  return (
    <svg viewBox={MULTIPLICA_VIEWBOX} className={className} style={style} role="img" aria-label="Multiplica">
      {MULTIPLICA_PATHS.map((d, i) => (
        <path key={i} d={d} fill={color} fillRule="evenodd" />
      ))}
    </svg>
  );
}

const inkStop = (tone) =>
  `color-mix(in oklab, var(--logo-ink-hi) ${Math.round(tone * 100)}%, var(--logo-ink-lo))`;

/** Logo completo de TrazIA 3D, con los degradados de cada cara. */
export function LogoTrazIA({ className, style }) {
  const uid = `lg${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <svg viewBox={FULL_VIEWBOX} className={className} style={style} role="img" aria-label="TrazIA 3D">
      <defs>
        {LOGO_FACES.map((f, i) =>
          f.g ? (
            <linearGradient key={i} id={`${uid}-${i}`} gradientUnits="userSpaceOnUse"
              x1={f.g[0]} y1={f.g[1]} x2={f.g[2]} y2={f.g[3]}>
              <stop offset="0" style={{ stopColor: f.ink ? inkStop(f.ink[0]) : f.stops[0] }} />
              <stop offset="1" style={{ stopColor: f.ink ? inkStop(f.ink[1]) : f.stops[1] }} />
            </linearGradient>
          ) : null,
        )}
      </defs>
      {LOGO_FACES.map((f, i) => (
        <path key={i} d={f.d} fillRule="evenodd"
          fill={f.fill === "word" ? "var(--logo-word)" : f.fill === "sky" ? "var(--logo-sky)" : `url(#${uid}-${i})`} />
      ))}
    </svg>
  );
}

/** Solo el texto «TrazIA 3D» del logo, sin la marca en volumen. */
export function WordmarkTrazIA({ className, style }) {
  return (
    <svg viewBox={WORD_VIEWBOX} className={className} style={style} role="img" aria-label="TrazIA 3D">
      {LOGO_FACES.filter((f) => f.role.startsWith("w-")).map((f, i) => (
        <path key={i} d={f.d} fillRule="evenodd" fill={f.fill === "sky" ? "var(--logo-sky)" : "var(--logo-word)"} />
      ))}
    </svg>
  );
}
