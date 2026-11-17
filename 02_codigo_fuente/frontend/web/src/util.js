const formatoHora = new Intl.DateTimeFormat('es-EC', {
  dateStyle: 'short',
  timeStyle: 'medium',
})

export function hora(valor) {
  return valor ? formatoHora.format(new Date(valor)) : '—'
}

// Devuelve el JSON de la respuesta o lanza un Error con el mensaje que mandó la API.
export async function leer(respuesta) {
  if (respuesta.ok) return respuesta.json()
  let detalle = `Error ${respuesta.status}`
  try {
    const cuerpo = await respuesta.json()
    if (typeof cuerpo.detail === 'string') detalle = cuerpo.detail
    else if (Array.isArray(cuerpo.detail)) detalle = 'Revisa los datos del formulario'
  } catch {
    // se deja el mensaje genérico
  }
  throw new Error(detalle)
}
