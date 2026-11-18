import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter'
import '@fontsource/eb-garamond/400.css'
import '@fontsource/eb-garamond/500.css'
import './index.css'
import App from './App.jsx'
import Panel from './Panel.jsx'

// /panel es el panel interno del asesor; cualquier otra ruta es el catálogo público.
const esPanel = window.location.pathname.startsWith('/panel')

createRoot(document.getElementById('root')).render(
  <StrictMode>{esPanel ? <Panel /> : <App />}</StrictMode>,
)
