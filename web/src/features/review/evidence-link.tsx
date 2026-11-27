"use client";

import { useEffect, useRef } from "react";
import styles from "./review.module.css";

/** Une la evidencia visible del PDF con el anclaje proyectado del componente IFC. */
export function EvidenceLink({
  path,
  elementId,
}: {
  path: string | null;
  elementId: string | null;
}) {
  const svg = useRef<SVGSVGElement>(null),
    line = useRef<SVGPathElement>(null);
  useEffect(() => {
    const root = svg.current?.parentElement,
      node = line.current;
    if (!root || !node || !path || !elementId) return;
    let frame = 0;
    const draw = () => {
      frame = 0;
      const bounds = root.getBoundingClientRect();
      const get = (selector: string) => {
        const el = root.querySelector<HTMLElement>(selector);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const panel = el.closest("[data-panel]")?.getBoundingClientRect();
        const scroll = el
          .closest("[data-evidence-scroll]")
          ?.getBoundingClientRect();
        if (
          r.width === 0 ||
          r.height === 0 ||
          (panel && (panel.width < 1 || panel.height < 1 ||
            r.right < panel.left || r.left > panel.right ||
            r.bottom < panel.top || r.top > panel.bottom)) ||
          r.bottom < bounds.top ||
          r.top > bounds.bottom ||
          (scroll && (r.bottom < scroll.top || r.top > scroll.bottom))
        )
          return null;
        return {
          x: (r.left + r.right) / 2 - bounds.left,
          y: (r.top + r.bottom) / 2 - bounds.top,
        };
      };
      const model = get(`[data-ifc-anchor="${CSS.escape(elementId)}"]`),
        pdf = get(`[data-path="${CSS.escape(path)}"]`);
      const points = [pdf, model].filter(
        (p): p is { x: number; y: number } => !!p,
      );
      if (points.length < 2) {
        node.setAttribute("d", "");
        return;
      }
      node.setAttribute(
        "d",
        points
          .map((p, i) => (i ? `L ${p.x} ${p.y}` : `M ${p.x} ${p.y}`))
          .join(" "),
      );
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(draw);
    };
    const observer = new MutationObserver(schedule);
    observer.observe(root, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["style"],
    });
    const resize = new ResizeObserver(schedule);
    resize.observe(root);
    root.addEventListener("scroll", schedule, true);
    schedule();
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches)
      node.animate([{ opacity: 0 }, { opacity: 0.65 }], {
        duration: 240,
        easing: "ease-out",
      });
    return () => {
      observer.disconnect();
      resize.disconnect();
      root.removeEventListener("scroll", schedule, true);
      cancelAnimationFrame(frame);
    };
  }, [path, elementId]);
  return (
    <svg ref={svg} className={styles.connector} aria-hidden="true">
      <path ref={line} />
    </svg>
  );
}
