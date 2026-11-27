import {
  AmbientLight, Box3, BufferAttribute, BufferGeometry, Color, DirectionalLight, Group,
  Mesh, MeshLambertMaterial, OrthographicCamera, Scene, Vector3, WebGLRenderer,
} from "three";
import type { IfcModel } from "@/workers/ifc-protocol";
import { withIfcModel } from "./model-resource";

const WIDTH = 176;
const HEIGHT = 132;
const MAX_IMAGES = 64;
const images = new Map<string, Promise<string>>();
let queue: Promise<void> = Promise.resolve();
let renderer: WebGLRenderer | null = null;

function render(model: IfcModel): string {
  renderer ??= new WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setSize(WIDTH, HEIGHT, false);
  const scene = new Scene();
  const group = new Group();
  const modelBounds = new Box3(new Vector3(...model.bounds.min), new Vector3(...model.bounds.max));
  const center = modelBounds.getCenter(new Vector3());
  const span = modelBounds.getSize(new Vector3()).length();
  const meshes: Mesh<BufferGeometry, MeshLambertMaterial>[] = [];
  try {
    for (const product of model.products) {
      if (product.psets.TrazIA_Soldadura) continue;
      for (const part of product.parts) {
        const geometry = new BufferGeometry();
        geometry.setAttribute("position", new BufferAttribute(part.positions, 3));
        geometry.setAttribute("normal", new BufferAttribute(part.normals, 3));
        geometry.setIndex(new BufferAttribute(part.indices, 1));
        const color = new Color(part.color[0], part.color[1], part.color[2]).lerp(new Color("#a3bfd6"), .3);
        const mesh = new Mesh(geometry, new MeshLambertMaterial({ color }));
        mesh.position.fromArray(product.center).sub(center);
        meshes.push(mesh);
        group.add(mesh);
      }
    }
    if (!meshes.length || !Number.isFinite(span) || span <= 0) throw new Error("El IFC no tiene geometría para la miniatura");
    scene.add(group, new AmbientLight(0xffffff, 1.05));
    const light = new DirectionalLight(0xffffff, 2.1);
    light.position.set(4, 7, 5);
    scene.add(light);
    const camera = new OrthographicCamera(-1, 1, 1, -1, span / 100, span * 8);
    camera.position.set(1, .52, 1.2).setLength(span * 2);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();
    const projected = new Box3().setFromObject(group).applyMatrix4(camera.matrixWorldInverse);
    const size = projected.getSize(new Vector3());
    const middle = projected.getCenter(new Vector3());
    const halfHeight = Math.max(size.y, size.x * HEIGHT / WIDTH) * .57;
    const halfWidth = halfHeight * WIDTH / HEIGHT;
    camera.left = middle.x - halfWidth;
    camera.right = middle.x + halfWidth;
    camera.bottom = middle.y - halfHeight;
    camera.top = middle.y + halfHeight;
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
    return renderer.domElement.toDataURL("image/png");
  } finally {
    for (const mesh of meshes) { mesh.geometry.dispose(); mesh.material.dispose(); }
  }
}

/** Genera una imagen estática en el navegador y comparte el resultado por URL versionada. */
export function ifcThumbnail(url: string): Promise<string> {
  const cached = images.get(url);
  if (cached) return cached;
  const pending = queue.then(() => withIfcModel(url, render));
  queue = pending.then(() => {}, () => { images.delete(url); });
  images.set(url, pending);
  if (images.size > MAX_IMAGES) images.delete(images.keys().next().value!);
  return pending;
}
