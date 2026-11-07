import { Outlet } from "react-router-dom";
import { AppProviders } from "./providers";

export function RootProviders() {
  return (
    <AppProviders>
      <Outlet />
    </AppProviders>
  );
}
