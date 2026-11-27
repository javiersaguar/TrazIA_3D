import { describe, expect, it } from "vitest";
import { isChangeRequest, speakableOption, spokenOption } from "./intent";

describe("isChangeRequest", () => {
  it("manda las órdenes de cambio al editor", () => {
    expect(isChangeRequest("Sube la boquilla N1 200 mm")).toBe(true);
    expect(isChangeRequest("por favor, cambia el diámetro a 2000")).toBe(true);
    expect(isChangeRequest("Quiero que quites la boquilla M2")).toBe(true);
  });

  it.each([
    "Quiero que la boquilla de elevación sea de 2300mm, cámbiala",
    "Quiero que la elevación mida dos mil trescientos milímetros",
    "¿Puedes mover la boquilla K3A a 2,3 metros?",
    "Deja la altura del techo a ciento veinte centímetros",
    "Fija el origen X a -1,2 metros",
    "Quita la escalera L2",
    "Añade la plataforma P5",
    "No cambies la proyección",
    "más o menos quiero que cambies la elevación de la boquilla N3 por el valor de 650 milímetros",
    "perfecto podemos cambiar ese valor de 660 milímetros por 650 milímetros",
    "hacer un cambio de ese valor a 650",
    "vale, sube N3 hasta 650 mm",
    "vamos a bajar la boquilla N3 a 650 mm",
    "¿Podrías cambiar la elevación de N3 a 650 mm?",
  ])("clasifica la orden %s también tras dictarla", text => {
    expect(isChangeRequest(text)).toBe(true);
  });

  it.each([
    "¿De dónde sale el valor seleccionado?",
    "¿Qué cambia respecto a la revisión anterior?",
    "¿Puedes decirme cuánto mide el compresor?",
    "Qué pasaría si bajo la boquilla",
    "vale, ¿cuál es la elevación de N3?",
    "perfecto, ¿cómo cambio la elevación?",
    "¿recibes mis mensajes?",
  ])("clasifica la consulta %s sin crear borrador", text => {
    expect(isChangeRequest(text)).toBe(false);
  });

  it("deja las preguntas al Copiloto", () => {
    expect(isChangeRequest("¿Cuál es el diámetro?")).toBe(false);
    expect(isChangeRequest("qué cambia respecto a la revisión anterior")).toBe(false);
    expect(isChangeRequest("ponte en el modelo")).toBe(false);
  });
});

describe("opciones dictadas", () => {
  const sides = ["lado +Y", "lado -Y"];
  it("pide las opciones con palabras que el dictado reconoce", () => {
    expect(sides.map(speakableOption)).toEqual(["lado positivo", "lado negativo"]);
    expect(speakableOption("N3")).toBe("N3");
  });

  it.each([
    ["lado positivo", "lado +Y"],
    ["el lado negativo", "lado -Y"],
    ["al primero lado y", "lado +Y"],
    ["el segundo", "lado -Y"],
    ["lado guión y", "lado -Y"],
    ["lado menos y", "lado -Y"],
    ["lado más y", "lado +Y"],
    ["lado + y", "lado +Y"],
  ])("entiende «%s» como %s", (said, option) => {
    expect(spokenOption(said, sides)).toBe(option);
  });

  it("no elige si la respuesta no decide", () => {
    expect(spokenOption("lado y", sides)).toBeNull();
    expect(spokenOption("no sé", sides)).toBeNull();
    expect(spokenOption("la segunda", ["N1", "N2", "N3"])).toBe("N2");
    expect(spokenOption("n3", ["N1", "N2", "N3"])).toBe("N3");
  });
});
