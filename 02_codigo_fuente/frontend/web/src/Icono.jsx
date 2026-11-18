// Íconos de trazo del panel (JOY-88). Decorativos: el texto del botón ya dice qué hacen.
const TRAZOS = {
  chat: <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />,
  tablero: (
    <>
      <rect x="3" y="4" width="5" height="16" rx="1.5" />
      <rect x="10" y="4" width="5" height="11" rx="1.5" />
      <rect x="17" y="4" width="4" height="7" rx="1.5" />
    </>
  ),
  grafico: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  luna: <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />,
  salir: <path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11" />,
  cerrar: <path d="M6 6l12 12M18 6L6 18" />,
  buscar: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" />
    </>
  ),
  filtros: <path d="M4 6h16M7 12h10M10 18h4" />,
  mas: <path d="M12 5v14M5 12h14" />,
  calendario: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </>
  ),
  actualizar: <path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />,
}

export default function Icono({ nombre, tamano = 18 }) {
  return (
    <svg
      width={tamano}
      height={tamano}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {TRAZOS[nombre]}
    </svg>
  )
}
