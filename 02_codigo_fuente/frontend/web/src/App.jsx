import { useEffect, useState } from 'react'
import './App.css'

const MATERIALES = ['oro', 'plata']
const FILTROS_VACIOS = { categoria: '', material: '', q: '', precioMax: '' }
const PERSONALIZADO = '__personalizado__'
const MENSAJE_SIN_RESULTADOS =
  'Hola, no encontré en el catálogo la joya que busco. ¿Me pueden ayudar?'

const formatoDolar = new Intl.NumberFormat('es-EC', {
  style: 'currency',
  currency: 'USD',
})

function dinero(valor) {
  return formatoDolar.format(Number(valor))
}

function construirConsulta({ categoria, material, q, precioMax }) {
  const params = new URLSearchParams()
  if (categoria) params.set('categoria', categoria)
  if (material) params.set('material', material)
  if (q.trim()) params.set('q', q.trim())
  if (precioMax) params.set('precio_max', precioMax)
  const texto = params.toString()
  return texto ? `?${texto}` : ''
}

function ContactoAsesor({ titulo, mensaje }) {
  const [canales, setCanales] = useState([])
  const [canal, setCanal] = useState('whatsapp')

  useEffect(() => {
    const control = new AbortController()
    fetch(`/api/contacto?mensaje=${encodeURIComponent(mensaje)}`, {
      signal: control.signal,
    })
      .then((r) => (r.ok ? r.json() : []))
      .then(setCanales)
      .catch(() => {})
    return () => control.abort()
  }, [mensaje])

  const elegido = canales.find((c) => c.canal === canal) ?? canales[0]

  return (
    <div className="contacto">
      <p>{titulo}</p>
      {elegido && (
        <>
          <label>
            Canal preferido
            <select
              value={elegido.canal}
              onChange={(e) => setCanal(e.target.value)}
            >
              {canales.map((c) => (
                <option key={c.canal} value={c.canal}>
                  {c.nombre}
                </option>
              ))}
            </select>
          </label>
          <a
            className="boton primario"
            href={elegido.enlace}
            target="_blank"
            rel="noreferrer"
          >
            Contactar a un asesor por {elegido.nombre}
          </a>
        </>
      )}
    </div>
  )
}

function Configurador({ productoId, onCerrar }) {
  const [detalle, setDetalle] = useState({ producto: null, error: null })
  const [seleccion, setSeleccion] = useState(null)
  const [cotizacion, setCotizacion] = useState({
    clave: null,
    datos: null,
    error: null,
    ms: null,
  })

  const combos = detalle.producto?.precios ?? []
  const materiales = [...new Set(combos.map((c) => c.material))]
  const todosQuilatajes = [
    ...new Set(combos.map((c) => c.quilataje).filter(Boolean)),
  ].sort()
  const quilatajesDe = (m) =>
    combos.filter((c) => c.material === m).map((c) => c.quilataje).filter(Boolean)

  const material = seleccion?.material ?? null
  const quilataje = seleccion?.quilataje ?? null
  const clave = `${material}|${quilataje ?? ''}`
  const noEstandar = material === PERSONALIZADO || quilataje === PERSONALIZADO

  useEffect(() => {
    fetch(`/api/productos/${productoId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Error ${r.status} al cargar la joya`)
        return r.json()
      })
      .then((producto) => {
        setDetalle({ producto, error: null })
        const primero = producto.precios[0]
        if (primero) {
          setSeleccion({
            material: primero.material,
            quilataje: primero.quilataje,
          })
        }
      })
      .catch((e) => setDetalle({ producto: null, error: e.message }))
  }, [productoId])

  useEffect(() => {
    if (material === null || material === PERSONALIZADO) return undefined
    if (quilataje === PERSONALIZADO) return undefined
    const control = new AbortController()
    const inicio = performance.now()
    const params = new URLSearchParams({ material })
    if (quilataje) params.set('quilataje', quilataje)
    fetch(`/api/productos/${productoId}/cotizacion?${params}`, {
      signal: control.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error('Combinación no disponible')
        return r.json()
      })
      .then((datos) =>
        setCotizacion({
          clave,
          datos,
          error: null,
          ms: Math.round(performance.now() - inicio),
        }),
      )
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setCotizacion({ clave, datos: null, error: e.message, ms: null })
        }
      })
    return () => control.abort()
  }, [productoId, material, quilataje, clave])

  function cambiarMaterial(e) {
    const m = e.target.value
    setSeleccion({
      material: m,
      quilataje: m === PERSONALIZADO ? null : (quilatajesDe(m)[0] ?? null),
    })
  }

  function cambiarQuilataje(e) {
    setSeleccion((s) => ({ ...s, quilataje: e.target.value }))
  }

  const cotizando =
    material !== null && !noEstandar && cotizacion.clave !== clave
  const disponibles = material ? quilatajesDe(material) : []

  return (
    <div className="fondo-modal" onClick={onCerrar}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Configurar joya"
        onClick={(e) => e.stopPropagation()}
      >
        {detalle.error && <p className="estado error">{detalle.error}</p>}
        {!detalle.error && !detalle.producto && <p className="estado">Cargando…</p>}
        {detalle.producto && (
          <>
            <span className="categoria">{detalle.producto.categoria}</span>
            <h2>{detalle.producto.nombre}</h2>
            <p className="descripcion">{detalle.producto.descripcion}</p>

            <div className="selectores">
              <label>
                Material
                <select value={material ?? ''} onChange={cambiarMaterial}>
                  {materiales.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                  <option value={PERSONALIZADO}>Otro (personalizado)</option>
                </select>
              </label>
              <label>
                Quilataje
                <select
                  value={quilataje ?? ''}
                  onChange={cambiarQuilataje}
                  disabled={disponibles.length === 0}
                >
                  {disponibles.length === 0 && <option value="">No aplica</option>}
                  {todosQuilatajes.map((q) => (
                    <option key={q} value={q} disabled={!disponibles.includes(q)}>
                      {q}
                      {disponibles.includes(q) ? '' : ' (no disponible)'}
                    </option>
                  ))}
                  {disponibles.length > 0 && (
                    <option value={PERSONALIZADO}>Otro (personalizado)</option>
                  )}
                </select>
              </label>
            </div>

            {noEstandar ? (
              <ContactoAsesor
                titulo="Esta combinación no se puede cotizar automáticamente. Un asesor te ayuda."
                mensaje={`Hola, quiero cotizar "${detalle.producto.nombre}" con un material o quilataje distinto a los del catálogo.`}
              />
            ) : (
              <div className="resultado" aria-live="polite">
                {cotizando && <span className="estado">Calculando…</span>}
                {!cotizando && cotizacion.error && (
                  <span className="estado error">{cotizacion.error}</span>
                )}
                {!cotizando && cotizacion.datos && (
                  <>
                    <span className="precio-grande">
                      {dinero(cotizacion.datos.precio)}
                    </span>
                    <span className="nota">
                      Precio referencial · respondió en {cotizacion.ms} ms
                    </span>
                  </>
                )}
              </div>
            )}
          </>
        )}
        <button type="button" className="boton" onClick={onCerrar}>
          Cerrar
        </button>
      </div>
    </div>
  )
}

function Tarjeta({ producto, onConfigurar }) {
  return (
    <li className="tarjeta">
      <span className="categoria">{producto.categoria}</span>
      <h2>{producto.nombre}</h2>
      <p className="descripcion">{producto.descripcion}</p>
      <ul className="opciones">
        {producto.precios.map((p) => (
          <li key={`${p.material}-${p.quilataje}`}>
            {p.material} {p.quilataje ?? ''} · {dinero(p.precio)}
          </li>
        ))}
      </ul>
      {producto.precio_desde && (
        <span className="desde">Desde {dinero(producto.precio_desde)}</span>
      )}
      <button
        type="button"
        className="boton primario"
        onClick={() => onConfigurar(producto.id)}
      >
        Configurar y cotizar
      </button>
    </li>
  )
}

function App() {
  const [filtros, setFiltros] = useState(FILTROS_VACIOS)
  const [categorias, setCategorias] = useState([])
  const [configurando, setConfigurando] = useState(null)
  const [resultado, setResultado] = useState({
    consulta: null,
    productos: [],
    error: null,
  })

  const consulta = construirConsulta(filtros)
  const cargando = resultado.consulta !== consulta

  useEffect(() => {
    fetch('/api/productos/categorias')
      .then((r) => (r.ok ? r.json() : []))
      .then(setCategorias)
      .catch(() => setCategorias([]))
  }, [])

  useEffect(() => {
    const control = new AbortController()
    fetch(`/api/productos${consulta}`, { signal: control.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`Error ${r.status} al consultar el catálogo`)
        return r.json()
      })
      .then((productos) => setResultado({ consulta, productos, error: null }))
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setResultado({ consulta, productos: [], error: e.message })
        }
      })
    return () => control.abort()
  }, [consulta])

  function cambiar(campo) {
    return (e) => setFiltros((f) => ({ ...f, [campo]: e.target.value }))
  }

  const sinResultados =
    !resultado.error && !cargando && resultado.productos.length === 0

  return (
    <main className="pagina">
      <header className="encabezado">
        <h1>Joyería Xavier</h1>
        <p>Catálogo de joyas</p>
      </header>

      <section className="filtros" aria-label="Filtros">
        <label>
          Buscar
          <input
            type="search"
            value={filtros.q}
            onChange={cambiar('q')}
            placeholder="Nombre de la joya"
          />
        </label>
        <label>
          Categoría
          <select value={filtros.categoria} onChange={cambiar('categoria')}>
            <option value="">Todas</option>
            {categorias.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label>
          Material
          <select value={filtros.material} onChange={cambiar('material')}>
            <option value="">Todos</option>
            {MATERIALES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label>
          Precio máximo (USD)
          <input
            type="number"
            min="0"
            value={filtros.precioMax}
            onChange={cambiar('precioMax')}
            placeholder="Ej. 500"
          />
        </label>
        <button type="button" onClick={() => setFiltros(FILTROS_VACIOS)}>
          Limpiar filtros
        </button>
      </section>

      {resultado.error && <p className="estado error">{resultado.error}</p>}
      {!resultado.error && cargando && <p className="estado">Cargando…</p>}
      {sinResultados && (
        <ContactoAsesor
          titulo="No hay joyas con esos filtros. Un asesor puede ayudarte a encontrar lo que buscas."
          mensaje={MENSAJE_SIN_RESULTADOS}
        />
      )}

      <ul className="rejilla">
        {resultado.productos.map((p) => (
          <Tarjeta key={p.id} producto={p} onConfigurar={setConfigurando} />
        ))}
      </ul>

      {configurando !== null && (
        <Configurador
          key={configurando}
          productoId={configurando}
          onCerrar={() => setConfigurando(null)}
        />
      )}
    </main>
  )
}

export default App