import { useEffect, useState } from 'react'
import './App.css'

const MATERIALES = ['oro', 'plata']
const FILTROS_VACIOS = { categoria: '', material: '', q: '', precioMax: '' }

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

function Tarjeta({ producto }) {
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
    </li>
  )
}

function App() {
  const [filtros, setFiltros] = useState(FILTROS_VACIOS)
  const [categorias, setCategorias] = useState([])
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
      {!resultado.error && !cargando && resultado.productos.length === 0 && (
        <p className="estado">No hay joyas con esos filtros.</p>
      )}

      <ul className="rejilla">
        {resultado.productos.map((p) => (
          <Tarjeta key={p.id} producto={p} />
        ))}
      </ul>
    </main>
  )
}

export default App