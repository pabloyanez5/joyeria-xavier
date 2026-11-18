import Icono from './Icono.jsx'

// Switch del modo oscuro (JOY-88). Se usa en el menú lateral y en el acceso.
export default function InterruptorTema({ tema, onAlternar }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={tema === 'oscuro'}
      className="interruptor-tema"
      onClick={onAlternar}
    >
      <Icono nombre="luna" />
      Modo oscuro
      <span className="interruptor" aria-hidden="true">
        <span />
      </span>
    </button>
  )
}
