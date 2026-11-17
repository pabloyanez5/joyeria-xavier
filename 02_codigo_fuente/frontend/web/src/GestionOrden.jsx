import { useState } from 'react'
import { pedir } from './sesion.js'
import { leer } from './util.js'

const SE_PUEDE_MODIFICAR = ['por_verificar', 'en_cola', 'en_produccion']
const CERRADAS = ['entregada', 'cancelada']
// Datos que el asesor puede corregir, en el orden del formulario de la orden.
const CAMPOS = [
  { clave: 'descripcion', titulo: 'Descripción', tipo: 'textarea' },
  { clave: 'peso_gramos', titulo: 'Peso (g)', tipo: 'number', paso: '0.01' },
  { clave: 'total', titulo: 'Total (USD)', tipo: 'number', paso: '0.01' },
  { clave: 'fecha_entrega_taller', titulo: 'Entrega al taller', tipo: 'date' },
  { clave: 'fecha_entrega_cliente', titulo: 'Entrega al cliente', tipo: 'date' },
  { clave: 'foto_referencia_url', titulo: 'Foto de referencia (enlace)', tipo: 'url' },
]

function valoresDe(orden) {
  return Object.fromEntries(CAMPOS.map(({ clave }) => [clave, orden[clave] ?? '']))
}

// JOY-23: el asesor corrige una orden, la devuelve una etapa o la cancela. Siempre con motivo;
// el cambio queda en el historial con su nombre y nada se borra.
export default function GestionOrden({ orden, avisar, nombreEtapa, onHecho }) {
  const [modo, setModo] = useState(null) // modificar | retroceder | cancelar
  const [motivo, setMotivo] = useState('')
  const [campos, setCampos] = useState({})
  const [error, setError] = useState(null)
  const [enviando, setEnviando] = useState(false)

  const modificable = SE_PUEDE_MODIFICAR.includes(orden.etapa_actual)
  const cancelable = !CERRADAS.includes(orden.etapa_actual)
  if (!modificable && !cancelable && !orden.etapa_anterior) return null

  function abrir(nuevo) {
    setModo(nuevo)
    setMotivo('')
    setError(null)
    setCampos(nuevo === 'modificar' ? valoresDe(orden) : {})
  }

  async function enviar(e) {
    e.preventDefault()
    setEnviando(true)
    setError(null)
    let ruta = `/api/ordenes/${orden.id}/${modo}`
    let metodo = 'POST'
    let cuerpo = { motivo }
    if (modo === 'modificar') {
      ruta = `/api/ordenes/${orden.id}`
      metodo = 'PATCH'
      const originales = valoresDe(orden)
      for (const [clave, valor] of Object.entries(campos)) {
        const limpio = String(valor).trim()
        if (limpio !== String(originales[clave])) cuerpo[clave] = limpio
      }
    } else if (modo === 'cancelar') {
      cuerpo = { motivo, avisar_al_cliente: avisar }
    }
    try {
      const r = await pedir(ruta, {
        method: metodo,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo),
      }).then(leer)
      setModo(null)
      onHecho(modo, r)
    } catch (fallo) {
      setError(fallo.message)
    } finally {
      setEnviando(false)
    }
  }

  if (modo === null) {
    return (
      <div className="gestion-acciones">
        {modificable && (
          <button type="button" onClick={() => abrir('modificar')}>
            Modificar
          </button>
        )}
        {orden.etapa_anterior && (
          <button type="button" onClick={() => abrir('retroceder')}>
            Devolver a {nombreEtapa(orden.etapa_anterior).toLowerCase()}
          </button>
        )}
        {cancelable && (
          <button type="button" className="peligro" onClick={() => abrir('cancelar')}>
            Cancelar orden
          </button>
        )}
      </div>
    )
  }

  return (
    <form className="gestion" onSubmit={enviar}>
      {modo === 'modificar' &&
        CAMPOS.map(({ clave, titulo, tipo, paso }) => (
          <label key={clave}>
            {titulo}
            {tipo === 'textarea' ? (
              <textarea
                rows={3}
                maxLength={1000}
                value={campos[clave]}
                onChange={(e) => setCampos((c) => ({ ...c, [clave]: e.target.value }))}
              />
            ) : (
              <input
                type={tipo}
                step={paso}
                min={tipo === 'number' ? '0.01' : undefined}
                value={campos[clave]}
                onChange={(e) => setCampos((c) => ({ ...c, [clave]: e.target.value }))}
              />
            )}
          </label>
        ))}
      {modo === 'retroceder' && (
        <p className="nota">
          La orden vuelve a «{nombreEtapa(orden.etapa_anterior)}». Úsalo para corregir un avance hecho por
          error; al cliente no se le avisa.
        </p>
      )}
      {modo === 'cancelar' && (
        <p className="nota">
          La orden sale del taller. No se borra: queda cancelada con su historial
          {avisar ? ' y el cliente recibe un aviso.' : '. El cliente no recibe aviso.'}
        </p>
      )}
      <label>
        Motivo (queda en el historial)
        <textarea rows={2} maxLength={500} value={motivo} onChange={(e) => setMotivo(e.target.value)} required />
      </label>
      {error && <p className="estado error">{error}</p>}
      <div className="gestion-acciones">
        <button type="submit" className={`boton ${modo === 'cancelar' ? 'peligro' : 'primario'}`} disabled={enviando}>
          {enviando
            ? 'Guardando…'
            : { modificar: 'Guardar cambios', retroceder: 'Devolver la orden', cancelar: 'Confirmar cancelación' }[modo]}
        </button>
        <button type="button" onClick={() => setModo(null)} disabled={enviando}>
          Volver
        </button>
      </div>
    </form>
  )
}
