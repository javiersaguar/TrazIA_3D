// Graba la animación de entrada de cada hoja como un MP4 para el PowerPoint.
//
// Sin dependencias nuevas: Chrome captura la lámina en tiempo real (CDP, Page.startScreencast),
// la codifica en H.264 con WebCodecs y aquí se escribe el MP4 (ftyp + moov + mdat, una pista).
// En el .pptx, el vídeo arranca solo al entrar en la hoja y se queda en su último fotograma.
import { writeFileSync } from "node:fs";

const FPS = 30;

/** Segundos que graba cada hoja: hasta que termina su última animación, con margen. */
export const DURACION = {
  equipo: 2.5,
  portada: 6.5,
  problema: 5,
  dificil: 4,
  como: 9.5,
  pruebas: 4.5,
  benchmarks: 5.5,
  diferencia: 10.5,
};

/**
 * Graba la hoja n (1-based) entrando desde la hoja vecina, como al presentar.
 * Devuelve los fotogramas JPEG con su instante, en segundos desde la entrada.
 */
async function capturar(browser, base, n, total, segundos) {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  try {
    const desde = n === 1 ? 2 : n - 1;
    await page.goto(`${base}/?hoja=${desde}`, { waitUntil: "domcontentloaded" });
    // La hoja de partida solo tiene que estar pintada; la portada en directo no avisa del IFC.
    await page.waitForFunction(() => document.body.dataset.fuentes === "1", null, { timeout: 60_000 });
    await page.waitForTimeout(n === 1 ? 2500 : 800);
    const cdp = await page.context().newCDPSession(page);
    const frames = [];
    cdp.on("Page.screencastFrame", (f) => {
      frames.push({ t: f.metadata.timestamp, jpg: Buffer.from(f.data, "base64") });
      cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
    });
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
    await page.waitForTimeout(400);
    await page.keyboard.press(n === 1 ? "ArrowLeft" : "ArrowRight");
    // El vídeo empieza cuando la hoja nueva ya está pintada: si no, sus primeros fotogramas (y la
    // portada del vídeo en PowerPoint) serían todavía la hoja anterior.
    const hoja = String(n);
    const t0 = await page.evaluate((hoja) => new Promise((ok) => {
      const mira = () => {
        if (new URL(location.href).searchParams.get("hoja") === hoja) requestAnimationFrame(() => requestAnimationFrame(() => ok(Date.now() / 1000)));
        else requestAnimationFrame(mira);
      };
      mira();
    }), hoja);
    await page.waitForTimeout(segundos * 1000 + 300);
    await cdp.send("Page.stopScreencast");
    const tras = frames.filter((f) => f.t >= t0);
    if (!tras.length) throw new Error(`Hoja ${n}: la captura no dio fotogramas`);
    return tras.map((f) => ({ t: f.t - t0, jpg: f.jpg }));
  } finally {
    await page.close();
  }
}

/** Codifica los fotogramas en H.264 a FPS constantes dentro de Chrome (WebCodecs). */
async function codificar(browser, base, frames, segundos) {
  const n = Math.round(segundos * FPS);
  // Para cada fotograma de salida, el último capturado que ya se veía en ese instante.
  const mapa = [];
  let j = 0;
  for (let k = 0; k < n; k++) {
    const t = k / FPS;
    while (j + 1 < frames.length && frames[j + 1].t <= t) j++;
    mapa.push(j);
  }
  const page = await browser.newPage();
  try {
    await page.route(`${base}/__codifica`, (r) => r.fulfill({ contentType: "text/html", body: "<!doctype html><title>codifica</title>" }));
    await page.route(`${base}/__f/*`, (r) => {
      const i = Number(r.request().url().split("/").pop());
      r.fulfill({ contentType: "image/jpeg", body: frames[i].jpg });
    });
    await page.goto(`${base}/__codifica`);
    return await page.evaluate(async ({ mapa, fps }) => {
      const W = 1920;
      const H = 1080;
      const b64 = (u8) => {
        let s = "";
        for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
        return btoa(s);
      };
      const muestras = [];
      let desc = null;
      let fallo = null;
      const enc = new VideoEncoder({
        output: (c, meta) => {
          if (!desc && meta?.decoderConfig?.description) desc = new Uint8Array(meta.decoderConfig.description);
          const u8 = new Uint8Array(c.byteLength);
          c.copyTo(u8);
          muestras.push({ key: c.type === "key", data: b64(u8) });
        },
        error: (e) => { fallo = e; },
      });
      enc.configure({ codec: "avc1.640028", width: W, height: H, bitrate: 8_000_000, framerate: fps, latencyMode: "quality", avc: { format: "avc" } });
      const lienzo = new OffscreenCanvas(W, H);
      const ctx = lienzo.getContext("2d");
      // RGB → YUV 4:2:0, BT.709 de rango limitado: el que suponen los reproductores. Si el
      // codificador convierte por su cuenta, el fondo #0f1317 sale negro (15 → 0).
      const aYuv = (rgba) => {
        const out = new Uint8ClampedArray((W * H * 3) / 2);
        const U = W * H;
        const V = U + U / 4;
        for (let i = 0, p = 0; i < W * H; i++, p += 4) {
          out[i] = 16 + ((0.2126 * rgba[p] + 0.7152 * rgba[p + 1] + 0.0722 * rgba[p + 2]) * 219) / 255 + 0.5;
        }
        for (let y = 0; y < H; y += 2) {
          for (let x = 0; x < W; x += 2) {
            let r = 0, g = 0, b = 0;
            for (const [dx, dy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
              const p = ((y + dy) * W + x + dx) * 4;
              r += rgba[p]; g += rgba[p + 1]; b += rgba[p + 2];
            }
            r /= 4; g /= 4; b /= 4;
            const c = (y / 2) * (W / 2) + x / 2;
            out[U + c] = 128 + ((-0.1146 * r - 0.3854 * g + 0.5 * b) * 224) / 255 + 0.5;
            out[V + c] = 128 + ((0.5 * r - 0.4542 * g - 0.0458 * b) * 224) / 255 + 0.5;
          }
        }
        return out;
      };
      let yuv = null;
      let ultimo = -1;
      let portada = null;
      for (let k = 0; k < mapa.length; k++) {
        if (fallo) throw fallo;
        if (mapa[k] !== ultimo) {
          const blob = await (await fetch(`/__f/${mapa[k]}`)).blob();
          const bmp = await createImageBitmap(blob);
          ctx.drawImage(bmp, 0, 0, W, H);
          bmp.close();
          ultimo = mapa[k];
        }
        if (k === 0) {
          const png = await lienzo.convertToBlob({ type: "image/png" });
          portada = b64(new Uint8Array(await png.arrayBuffer()));
        }
        if (mapa[k] !== mapa[k - 1] || !yuv) yuv = aYuv(ctx.getImageData(0, 0, W, H).data);
        const vf = new VideoFrame(yuv, {
          format: "I420", codedWidth: W, codedHeight: H,
          timestamp: Math.round((k * 1e6) / fps), duration: Math.round(1e6 / fps),
          colorSpace: { primaries: "bt709", transfer: "bt709", matrix: "bt709", fullRange: false },
        });
        enc.encode(vf, { keyFrame: k % (fps * 2) === 0 });
        vf.close();
        while (enc.encodeQueueSize > 8) await new Promise((r) => setTimeout(r, 4));
      }
      await enc.flush();
      enc.close();
      if (fallo) throw fallo;
      return { desc: b64(desc), muestras, portada };
    }, { mapa, fps: FPS });
  } finally {
    await page.close();
  }
}

/* ---------- MP4 mínimo: una pista de vídeo H.264, sin B-frames, moov delante (faststart) ---------- */
const u32 = (v) => { const b = Buffer.alloc(4); b.writeUInt32BE(v >>> 0); return b; };
const u16 = (v) => { const b = Buffer.alloc(2); b.writeUInt16BE(v & 0xffff); return b; };
const caja = (tipo, ...partes) => {
  const cuerpo = Buffer.concat(partes);
  return Buffer.concat([u32(8 + cuerpo.length), Buffer.from(tipo, "latin1"), cuerpo]);
};
const plena = (tipo, version, flags, ...partes) => caja(tipo, Buffer.from([version, (flags >> 16) & 255, (flags >> 8) & 255, flags & 255]), ...partes);
const MATRIZ = Buffer.concat([0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000].map(u32));

function mp4({ desc, muestras, ancho = 1920, alto = 1080, fps = FPS }) {
  const escala = fps * 1000;
  const n = muestras.length;
  const durMs = Math.round((n * 1000) / fps);
  const tamanos = muestras.map((m) => m.length);
  const claves = muestras.flatMap((m, i) => (m.key ? [i + 1] : []));
  const moov = (offset) => caja("moov",
    plena("mvhd", 0, 0, u32(0), u32(0), u32(1000), u32(durMs), u32(0x00010000), u16(0x0100), Buffer.alloc(10), MATRIZ, Buffer.alloc(24), u32(2)),
    caja("trak",
      plena("tkhd", 0, 3, u32(0), u32(0), u32(1), u32(0), u32(durMs), Buffer.alloc(8), u16(0), u16(0), u16(0), u16(0), MATRIZ, u32(ancho << 16), u32(alto << 16)),
      caja("mdia",
        plena("mdhd", 0, 0, u32(0), u32(0), u32(escala), u32(n * 1000), u16(0x55c4), u16(0)),
        plena("hdlr", 0, 0, u32(0), Buffer.from("vide", "latin1"), Buffer.alloc(12), Buffer.from("VideoHandler\0", "latin1")),
        caja("minf",
          plena("vmhd", 0, 1, Buffer.alloc(8)),
          caja("dinf", plena("dref", 0, 0, u32(1), plena("url ", 0, 1))),
          caja("stbl",
            plena("stsd", 0, 0, u32(1), caja("avc1",
              Buffer.alloc(6), u16(1), u16(0), u16(0), Buffer.alloc(12), u16(ancho), u16(alto),
              u32(0x00480000), u32(0x00480000), u32(0), u16(1), Buffer.alloc(32), u16(0x18), u16(0xffff),
              caja("avcC", desc))),
            plena("stts", 0, 0, u32(1), u32(n), u32(1000)),
            plena("stss", 0, 0, u32(claves.length), ...claves.map(u32)),
            plena("stsc", 0, 0, u32(1), u32(1), u32(n), u32(1)),
            plena("stsz", 0, 0, u32(0), u32(n), ...tamanos.map(u32)),
            plena("stco", 0, 0, u32(1), u32(offset)))))));
  const ftyp = caja("ftyp", Buffer.from("isom", "latin1"), u32(512), Buffer.from("isomiso2avc1mp41", "latin1"));
  const largo = moov(0).length;
  const datos = Buffer.concat(muestras);
  return Buffer.concat([ftyp, moov(ftyp.length + largo + 8), u32(8 + datos.length), Buffer.from("mdat", "latin1"), datos]);
}

/** Graba y escribe salida/anim/hoja-NN.mp4. Devuelve la ruta, la portada (primer fotograma) y la duración. */
export async function grabarHoja({ browser, base, n, total, id, destino }) {
  const segundos = DURACION[id] ?? 5;
  const frames = await capturar(browser, base, n, total, segundos);
  const r = await codificar(browser, base, frames, segundos);
  const muestras = r.muestras.map((m) => Object.assign(Buffer.from(m.data, "base64"), { key: m.key }));
  writeFileSync(destino, mp4({ desc: Buffer.from(r.desc, "base64"), muestras }));
  return { video: destino, portada: `data:image/png;base64,${r.portada}`, ms: Math.round((muestras.length * 1000) / FPS) };
}
