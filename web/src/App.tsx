import { useAuth } from './auth/AuthContext';
import { SignIn } from './auth/SignIn';
import { LoadingScreen } from './auth/LoadingScreen';
import { Dashboard } from './dashboard/Dashboard';

// No sign-out button: sessions are stateless JWTs with no server-side
// revocation, so a client "sign out" would be misleading (see the R1/R3
// plan) — sessions simply expire after 1 hour.

function App() {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <SignIn />;
  }

  return <Dashboard />;
}

export default App;
