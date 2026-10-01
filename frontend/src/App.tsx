// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { CatalogPage } from "./pages/CatalogPage";
import { ProductPage } from "./pages/ProductPage";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app__header">
          <h1>ShopFlow</h1>
        </header>
        <main className="app__main">
          <Routes>
            <Route path="/" element={<CatalogPage />} />
            <Route path="/products/:id" element={<ProductPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;