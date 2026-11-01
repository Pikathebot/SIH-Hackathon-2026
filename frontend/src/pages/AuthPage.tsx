import React, { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { AlertOctagon, Globe2, Loader2, LogIn, UserPlus } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const MIN_PASSWORD = 10;

/** Sign-in and registration share one layout; `mode` picks the form. */
export const AuthPage: React.FC<{ mode: 'login' | 'register' }> = ({ mode }) => {
  const { status, login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isRegister = mode === 'register';
  const from = (location.state as { from?: string } | null)?.from || '/';

  if (status === 'authenticated') return <Navigate to={from} replace />;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (isRegister && password.length < MIN_PASSWORD) {
      setError(`Use at least ${MIN_PASSWORD} characters for your password.`);
      return;
    }
    if (isRegister && password !== confirm) {
      setError('The passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      await (isRegister ? register(email.trim(), password) : login(email.trim(), password));
      navigate(from, { replace: true });
    } catch (err: any) {
      setError(err?.message || 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const inputClass =
    'w-full px-3.5 py-2.5 bg-background border border-grid-hairline rounded-xl text-sm text-text-primary ' +
    'placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-colors';

  return (
    <div className="min-h-screen flex items-center justify-center bg-background text-text-primary font-body px-4 py-10">
      <div className="w-full max-w-sm flex flex-col gap-6">
        <div className="flex flex-col items-center text-center gap-3">
          <div className="p-3 bg-primary/10 rounded-2xl text-primary">
            <Globe2 className="w-8 h-8" />
          </div>
          <div>
            <h1 className="font-headline text-xl font-bold tracking-tight">SatQuery AI</h1>
            <p className="text-sm text-text-muted mt-1">
              {isRegister ? 'Create an account to save your analyses.' : 'Sign in to your analyses.'}
            </p>
          </div>
        </div>

        <form
          onSubmit={onSubmit}
          className="bg-surface-panel border border-grid-hairline rounded-2xl shadow-sm p-6 flex flex-col gap-4"
          noValidate
        >
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-text-muted">Email</span>
            <input
              type="email"
              autoComplete="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              placeholder="you@example.com"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-text-muted">Password</span>
            <input
              type="password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
            />
            {isRegister && (
              <span className="text-[11px] text-text-muted">At least {MIN_PASSWORD} characters.</span>
            )}
          </label>

          {isRegister && (
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-text-muted">Confirm password</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className={inputClass}
              />
            </label>
          )}

          {error && (
            <div role="alert" className="flex items-start gap-2 text-xs text-red-delta bg-red-delta/10 border border-red-delta/30 rounded-xl px-3 py-2.5">
              <AlertOctagon className="w-4 h-4 flex-shrink-0 mt-px" />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={busy || !email || !password}
            className="flex items-center justify-center gap-2 py-2.5 bg-primary-container text-on-primary-container hover:bg-primary disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold rounded-xl transition-all shadow-sm cursor-pointer"
          >
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : isRegister ? (
              <UserPlus className="w-4 h-4" />
            ) : (
              <LogIn className="w-4 h-4" />
            )}
            <span>{isRegister ? 'Create account' : 'Sign in'}</span>
          </button>
        </form>

        <p className="text-center text-xs text-text-muted">
          {isRegister ? 'Already have an account? ' : 'New to SatQuery? '}
          <Link
            to={isRegister ? '/login' : '/register'}
            state={location.state}
            className="text-primary font-semibold hover:underline"
          >
            {isRegister ? 'Sign in' : 'Create an account'}
          </Link>
        </p>
      </div>
    </div>
  );
};
