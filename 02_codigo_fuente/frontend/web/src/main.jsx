import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import Panel from './Panel.jsx'

// /panel es el panel interno del asesor; cualquier otra ruta es el catálogo público.
const esPanel = window.location.pathname.startsWith('/panel')

createRoot(document.getElementById('root')).render(
  <StrictMode>{esPanel ? <Panel /> : <App />}</StrictMode>,
)
