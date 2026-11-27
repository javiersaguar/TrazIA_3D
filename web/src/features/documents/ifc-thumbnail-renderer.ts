import {
  AmbientLight, Box3, BufferAttribute, BufferGeometry, Color, DirectionalLight, Group, Mesh,
  MeshStandardMaterial, OrthographicCamera, Scene, Vector3, WebGLRenderer,
} from "three";
import { BRAND } from "@/lib/brand";
import type { IfcModel } from "@/workers/ifc-protocol";
import { loadIfcSnapshot } from "@/features/viewer3d/model-resource";

const size = 256;
const images = new Map<string, Promise<string>>();
let queue = Promise.resolve();
let renderer: WebGLRenderer | undefined;
let idle: ReturnType<typeof setTimeout> | undefined;

function imageFromIfc(model: IfcModel) {
  const box = new Box3(new Vector3(...model.bounds.min), new Vector3(...model.bounds.max));
  const center = box.getCenter(new Vector3());
  const span = box.getSize(new Vector3()).length();
  if (!model.triangles || !Number.isFinite(span) || span <= 0) throw new Error("El IFC no contiene geometría visible.");

  clearTimeout(idle);
  try {
    renderer ??= new WebGLRenderer({ alpha: true, antialias: true, preserveDrawingBuffer: true });
    renderer.setSize(size, size, false);
    const scene = new Scene();
    const group = new Group();
    scene.add(group, new AmbientLight(BRAND.text, 1.7));
    const key = new DirectionalLight(BRAND.text, 2.3);
    key.position.set(3, 7, 4);
    const rim = new DirectionalLight(BRAND.skyLight, 1.2);
    rim.position.set(-4, 2, -2);
    scene.add(key, rim);

    const camera = new OrthographicCamera(-1, 1, 1, -1, span * .001, span * 8);
    camera.position.set(1.55, 1, 2).setLength(span * 2);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();
    const corners = new Box3(box.min.clone().sub(center), box.max.clone().sub(center))
      .applyMatrix4(camera.matrixWorldInverse);
    const extent = Math.max(corners.max.x, -corners.min.x, corners.max.y, -corners.min.y) * 1.16;
    camera.left = -extent;
    camera.right = extent;
    camera.top = extent;
    camera.bottom = -extent;
    camera.updateProjectionMatrix();

    const geometries: BufferGeometry[] = [];
    const materials = new Map<string, MeshStandardMaterial>();
    try {
      for (const product of model.products) {
        for (const part of product.parts) {
          const geometry = new BufferGeometry();
          geometries.push(geometry);
          geometry.setAttribute("position", new BufferAttribute(part.positions, 3));
          geometry.setAttribute("normal", new BufferAttribute(part.normals, 3));
          geometry.setIndex(new BufferAttribute(part.indices, 1));
          const [r, g, b] = part.color;
          const colorKey = `${r},${g},${b}`;
          let material = materials.get(colorKey);
          if (!material) {
            const color = new Color(r, g, b).lerp(new Color(BRAND.steel), .58);
            material = new MeshStandardMaterial({ color, metalness: .18, roughness: .56 });
            materials.set(colorKey, material);
          }
          const mesh = new Mesh(geometry, material);
          mesh.position.set(...product.center).sub(center);
          group.add(mesh);
        }
      }
      renderer.render(scene, camera);
      return renderer.domElement.toDataURL("image/png");
    } finally {
      geometries.forEach(geometry => geometry.dispose());
      materials.forEach(material => material.dispose());
    }
  } finally {
    idle = setTimeout(() => {
      renderer?.dispose();
      renderer?.forceContextLoss();
      renderer = undefined;
    }, 1000);
  }
}

/** Una imagen por IFC, en serie para acotar el trabajo al recorrer la lista. */
export function ifcThumbnail(url: string): Promise<string> {
  const cached = images.get(url);
  if (cached) return cached;
  const image = queue.then(async () => imageFromIfc(await loadIfcSnapshot(url)));
  queue = image.then(() => undefined, () => { images.delete(url); });
  if (!url.startsWith("blob:")) {
    images.set(url, image);
    if (images.size > 48) {
      const oldest = images.keys().next().value;
      if (oldest) images.delete(oldest);
    }
  }
  return image;
}
