import { useEffect, useState } from 'react'

// Tema del panel (JOY-88). La primera vez sigue al sistema operativo; si la persona usa el
// switch, su elección queda guardada en este navegador. El catálogo público no lo usa.
const CLAVE = 'joyeria.tema'

function preferidoDelSistema() {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro'
  } catch {
    return 'claro'
  }
}

export function temaGuardado() {
  try {
    const guardado = localStorage.getItem(CLAVE)
    if (guardado === 'claro' || guardado === 'oscuro') return guardado
  } catch {
    // navegación privada o almacenamiento bloqueado: se usa el del sistema
  }
  return preferidoDelSistema()
}

export function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema
}

export function useTema() {
  const [tema, setTema] = useState(temaGuardado)

  useEffect(() => {
    aplicarTema(tema)
    // Al salir del panel (por ejemplo, al catálogo) el sitio vuelve al tema claro.
    return () => delete document.documentElement.dataset.tema
  }, [tema])

  function alternar() {
    const nuevo = tema === 'oscuro' ? 'claro' : 'oscuro'
    try {
      localStorage.setItem(CLAVE, nuevo)
    } catch {
      // si no se puede guardar, el cambio vale solo para esta visita
    }
    setTema(nuevo)
  }

  return [tema, alternar]
}
