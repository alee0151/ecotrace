import { useState, useEffect } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router';
import { Sidebar, PageId } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { EmailGateModal } from './components/EmailGateModal';
import { warmIucnCache } from '../lib/api';

const titles: Record<string, { title: string; subtitle: string }> = {
  search: { title: 'Search', subtitle: 'Resolve a product, brand, or company' },
  overview: { title: 'Company Overview', subtitle: 'BHP Group Limited · ABN 49 004 028 077' },
  analyse: { title: 'Analyse', subtitle: 'Spatial risk & evidence exploration' },
  knowledge: { title: 'Knowledge Graph', subtitle: 'Claims, sources & provenance' },
  watchlist: { title: 'Watchlist', subtitle: 'Track biodiversity risk changes' },
  spatial: { title: 'Spatial Analysis', subtitle: 'Biodiversity risk dashboard' },
};

const PROTECTED_PAGES = ['/app/overview', '/app/analyse', '/app/knowledge', '/app/watchlist', '/app/spatial'];

export function Root() {
  const location = useLocation();
  const navigate = useNavigate();
  const [emailVerified, setEmailVerified] = useState(() => localStorage.getItem('ecotrace_email_verified') === 'true');
  const [lastUnprotectedRoute, setLastUnprotectedRoute] = useState<string>('/app/search');

  const currentPath = location.pathname;
  const pageKey = currentPath.replace('/app/', '');
  const meta = titles[pageKey] || { title: 'EcoTrace', subtitle: '' };
  
  const requiresVerification = PROTECTED_PAGES.includes(currentPath) && !emailVerified;

  useEffect(() => {
    warmIucnCache().catch((error) => {
      console.debug('IUCN cache warmup request failed', error);
    });
  }, []);

  useEffect(() => {
    if (localStorage.getItem('ecotrace_email_verified') === 'true') {
      setEmailVerified(true);
    }
  }, [currentPath]);

  // Track the last unprotected route
  useEffect(() => {
    if (!PROTECTED_PAGES.includes(currentPath) || emailVerified) {
      setLastUnprotectedRoute(currentPath);
    }
  }, [currentPath, emailVerified]);

  const handleCloseGate = () => {
    navigate(lastUnprotectedRoute);
  };

  const handleVerified = (email: string) => {
    localStorage.setItem('ecotrace_email_verified', 'true');
    localStorage.setItem('ecotrace_verified_email', email);
    setEmailVerified(true);
  };

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 flex">
      <Sidebar active={pageKey as PageId} />
      <div className="flex-1 min-w-0 relative flex flex-col">
        <TopBar title={meta.title} subtitle={meta.subtitle} />
        
        <div className={`flex-1 ${requiresVerification ? "h-[calc(100vh-64px)] overflow-hidden" : "overflow-y-auto"}`}>
          <Outlet />
        </div>
        
        {requiresVerification && (
          <EmailGateModal 
            pageName={meta.title} 
            returnTo={currentPath}
            onVerify={handleVerified} 
            onClose={handleCloseGate}
          />
        )}
      </div>
    </div>
  );
}
