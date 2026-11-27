/** Nombre con el que se firman las acciones de revisión: la cuenta en sesión, si la hay. */
let enSesion = "";

export function setSessionActor(name: string | null | undefined) {
  enSesion = name?.trim() ?? "";
}

/** Sin cuentas (demo local) o como invitado no hay persona: queda «Revisor local». */
export function sessionActor(fallback = "Revisor local") {
  return enSesion.length >= 2 ? enSesion : fallback;
}
