// Sesión del panel (JOY-78). El token vive en sessionStorage: se borra al cerrar la pestaña
// y caduca a las 8 horas. Todas las llamadas del panel pasan por `pedir`, que lo adjunta.
const CLAVE = 'joyeria.sesion'
export const SESION_CERRADA = 'joyeria:sesion-cerrada'

export const ROL = {
  asesor: 'Asesor comercial',
  taller: 'Taller',
  direccion: 'Dirección',
  admin: 'Administrador',
}

export function sesionGuardada() {
  try {
    const sesion = JSON.parse(sessionStorage.getItem(CLAVE))
    if (!sesion?.token || !sesion?.usuario || Date.now() >= sesion.caduca) return null
    return sesion
  } catch {
    return null
  }
}

export function salir() {
  sessionStorage.removeItem(CLAVE)
  window.dispatchEvent(new Event(SESION_CERRADA))
}

export async function entrar(email, clave) {
  const respuesta = await fetch('/api/sesion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, clave }),
  })
  const cuerpo = await respuesta.json().catch(() => ({}))
  if (!respuesta.ok) {
    const porDefecto =
      respuesta.status === 429
        ? 'Demasiados intentos. Espera un momento y vuelve a probar.'
        : 'No se pudo iniciar sesión'
    throw new Error(typeof cuerpo.detail === 'string' ? cuerpo.detail : porDefecto)
  }
  const sesion = {
    token: cuerpo.token,
    usuario: cuerpo.usuario,
    caduca: Date.now() + cuerpo.expira_en * 1000,
  }
  sessionStorage.setItem(CLAVE, JSON.stringify(sesion))
  return sesion
}

// Igual que fetch, pero con el token. Si el servidor dice que la sesión ya no vale, la cierra.
export async function pedir(ruta, opciones = {}) {
  const sesion = sesionGuardada()
  const respuesta = await fetch(ruta, {
    ...opciones,
    headers: {
      ...opciones.headers,
      ...(sesion ? { Authorization: `Bearer ${sesion.token}` } : {}),
    },
  })
  if (respuesta.status === 401) salir()
  return respuesta
}

export function puede(usuario, ...roles) {
  return Boolean(usuario) && (usuario.rol === 'admin' || roles.includes(usuario.rol))
}
