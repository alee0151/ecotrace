import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { confirmEmailVerification } from '../../lib/api';

export function VerifyEmail() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [state, setState] = useState<'loading' | 'verified' | 'error'>('loading');
  const [message, setMessage] = useState('Verifying your email...');

  useEffect(() => {
    const token = params.get('token');
    const fallbackReturnTo = params.get('return_to') || '/app/search';
    if (!token) {
      setState('error');
      setMessage('Verification token is missing.');
      return;
    }

    confirmEmailVerification(token)
      .then((result) => {
        const email = result.verification.email;
        const returnTo = result.verification.return_to || fallbackReturnTo;
        localStorage.setItem('seeco_email_verified', 'true');
        localStorage.setItem('seeco_verified_email', email);
        setState('verified');
        setMessage(`Verified ${email}. Redirecting...`);
        window.setTimeout(() => navigate(returnTo, { replace: true }), 1200);
      })
      .catch((error: Error) => {
        setState('error');
        setMessage(error.message || 'Verification link is invalid or expired.');
      });
  }, [navigate, params]);

  const Icon = state === 'loading' ? Loader2 : state === 'verified' ? CheckCircle2 : XCircle;

  return (
    <div className="min-h-[calc(100vh-64px)] flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-xl border border-stone-200 bg-white p-6 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100">
          <Icon className={`${state === 'loading' ? 'animate-spin' : ''} text-emerald-700`} size={28} />
        </div>
        <div className="text-[20px] text-stone-900">Email verification</div>
        <div className="mt-2 text-[13px] leading-relaxed text-stone-600">{message}</div>
        {state === 'error' && (
          <button
            onClick={() => navigate('/app/search', { replace: true })}
            className="mt-5 h-10 rounded-lg bg-stone-900 px-4 text-[13px] text-white hover:bg-stone-800"
          >
            Back to search
          </button>
        )}
      </div>
    </div>
  );
}
