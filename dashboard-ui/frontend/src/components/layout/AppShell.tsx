import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function AppShell() {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <main className="ml-56 min-h-screen">
        <div className="mx-auto max-w-[1200px] px-5 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
