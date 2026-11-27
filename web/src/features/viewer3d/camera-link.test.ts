import { describe, expect, it } from "vitest";
import { CameraLink, validPose, type CameraPose } from "./camera-link";
describe("cámaras de la comparación A | B", () => {
  it("propaga la pose al otro visor sin bucle y libera la suscripción", () => {
    const channel = new CameraLink(),
      a = Symbol(),
      b = Symbol(),
      seen: CameraPose[] = [];
    const pose: CameraPose = { eye: [2, 3, 4], target: [0, 2, 0], zoom: 80 };
    channel.subscribe(a, (p) => {
      seen.push(p);
      channel.publish(a, p);
    });
    const unsubscribe = channel.subscribe(b, (p) => {
      seen.push(p);
      channel.publish(b, p);
    });
    channel.publish(a, pose);
    expect(seen).toEqual([pose]);
    unsubscribe();
    channel.publish(a, pose);
    expect(seen).toHaveLength(1);
  });
});
describe("poses de cámara", () => {
  it("descarta cámaras degeneradas o con zoom no finito", () => {
    expect(validPose({ eye: [0, 0, 0], target: [0, 0, 0], zoom: 50 })).toBe(false);
    const pose = { eye: [1, 2, 3], target: [0, 0, 0], zoom: 50 };
    expect(validPose(pose)).toBe(true);
    expect(validPose({ ...pose, zoom: Infinity })).toBe(false);
  });
});
