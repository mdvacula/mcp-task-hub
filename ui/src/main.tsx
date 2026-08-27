import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import App from "./App.tsx"

// Dark by default on this box; respect an explicit saved choice.
const saved = localStorage.getItem("theme")
if (saved !== "light") {
  document.documentElement.classList.add("dark")
}
const observer = new MutationObserver(() => {
  localStorage.setItem(
    "theme",
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  )
})
observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
