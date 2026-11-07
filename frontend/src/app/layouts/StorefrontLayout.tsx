import { Outlet } from "react-router-dom";
import { Header } from "../../components/Header";
import { ToastContainer } from "../../components/ToastContainer";

export function StorefrontLayout() {
  return (
    <div className="app">
      <Header />
      <main className="app__main">
        <Outlet />
      </main>
      <ToastContainer />
    </div>
  );
}
