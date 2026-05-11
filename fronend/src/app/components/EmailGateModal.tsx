import { useState } from 'react';
import { Leaf, Mail, CheckCircle2, X } from 'lucide-react';
import { requestEmailVerification } from '../../lib/api';

function canUseLocalVerificationFallback() {
  if (import.meta.env.DEV) return true;
  return ['localhost', '127.0.0.1'].includes(window.location.hostname);
}

export function EmailGateModal({ 
  onVerify,
  onClose,
  pageName,
  returnTo,
}: { 
  onVerify: (email: string) => void;
  onClose: () => void;
  pageName?: string;
  returnTo: string;
}) {
  const [email, setEmail] = useState('');
  const [state, setState] = useState<'default' | 'loading' | 'sent' | 'verified'>('default');
  const [showWhy, setShowWhy] = useState(false);
  const [countdown, setCountdown] = useState(60);
  const [message, setMessage] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!email.trim()) return;
    setState('loading');
    setMessage(null);
    try {
      const result = await requestEmailVerification(email.trim(), returnTo);
      if (result.delivery === 'outbox' && canUseLocalVerificationFallback()) {
        setState('verified');
        setMessage('Local demo verification completed.');
        if (result.user_id) window.localStorage.setItem('seeco_user_id', result.user_id);
        window.setTimeout(() => onVerify(result.email || email.trim()), 400);
        return;
      }
      setState('sent');
      setMessage(
        result.delivery === 'outbox'
          ? 'Verification email saved to the local outbox for demo delivery.'
          : 'Verification link sent. Open it from your inbox to continue.'
      );
      const timer = setInterval(() => {
        setCountdown(c => {
          if (c <= 1) {
            clearInterval(timer);
            return 0;
          }
          return c - 1;
        });
      }, 1000);
    } catch (error) {
      if (canUseLocalVerificationFallback()) {
        setState('verified');
        setMessage('Local demo verification completed because the email service is unavailable.');
        window.setTimeout(() => onVerify(email.trim()), 400);
        return;
      }
      setState('default');
      setMessage(error instanceof Error ? error.message : 'Could not send verification link.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-emerald-950/30 backdrop-blur-md" />
      <div className="relative w-full max-w-[480px] bg-white rounded-[20px] shadow-2xl p-8 animate-in fade-in zoom-in duration-300">
        
        {/* Close Button */}
        {state !== 'verified' && (
          <button 
            onClick={onClose}
            className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full bg-stone-50 hover:bg-stone-100 text-stone-500 transition-all hover:scale-105 active:scale-95"
            aria-label="Close modal"
          >
            <X size={16} />
          </button>
        )}

        {state !== 'sent' && state !== 'verified' && (
          <>
            <div className="flex justify-center mb-4">
              <div className="w-12 h-12 rounded-full bg-emerald-100 flex items-center justify-center">
                <Leaf size={24} className="text-emerald-700" />
              </div>
            </div>

            <div className="text-center mb-6">
              <div className="text-[20px] text-stone-900 mb-2">
                Unlock {pageName ? `the ${pageName}` : 'Seeco Insights'}
              </div>
              <div className="text-[13px] text-stone-600 leading-relaxed">
                Enter your email to access deep biodiversity analytics, supply chain risks, and verified evidence — free and no password required.
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <input
                  type="email"
                  placeholder="your@email.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={state === 'loading'}
                  className="w-full h-12 px-4 rounded-lg border border-stone-200 text-[14px] focus:outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 disabled:bg-stone-50"
                />
              </div>

              <button
                onClick={handleSubmit}
                disabled={state === 'loading' || !email}
                className="w-full h-12 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-[14px] font-medium disabled:bg-stone-300 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2 transition-colors"
              >
                {state === 'loading' ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Sending link...
                  </>
                ) : (
                  'Send verification link'
                )}
              </button>

              {message && (
                <div className={`text-[12px] text-center ${state === 'default' ? 'text-rose-700' : 'text-emerald-700'}`}>
                  {message}
                </div>
              )}

              <div className="text-[11.5px] text-stone-500 text-center">
                We'll email you a one-click verification link. No password needed.
              </div>

              <button onClick={() => setShowWhy(!showWhy)} className="text-[12px] text-emerald-700 hover:text-emerald-800 underline w-full transition-colors">
                Why do we need your email?
              </button>

              {showWhy && (
                <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-100 text-[12px] text-stone-700 leading-relaxed animate-in slide-in-from-top-2">
                  Seeco uses your email to provide persistent access to analyst reports, save your watchlist across devices, and send alerts when biodiversity risks change.
                </div>
              )}
            </div>
          </>
        )}

        {state === 'sent' && (
          <div className="text-center animate-in fade-in slide-in-from-bottom-4 duration-300">
            <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-4">
              <Mail size={32} className="text-emerald-700" />
            </div>
            <div className="text-[18px] text-stone-900 mb-2">Check your inbox</div>
            <div className="text-[13px] text-stone-600 mb-4">
              We've sent a link to <b>{email}</b>
            </div>
            <div className="text-[12px] text-stone-500">
              Didn't get it? Check spam or{' '}
              {countdown > 0 ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-stone-100 text-stone-600 text-[11px]">
                  Resend in 0:{countdown.toString().padStart(2, '0')}
                </span>
              ) : (
                <button onClick={handleSubmit} className="text-emerald-700 hover:text-emerald-800 underline">Resend link</button>
              )}
            </div>
            {message && <div className="text-[12px] text-emerald-700 mt-3">{message}</div>}
            <div className="mt-4 flex justify-center">
               <div className="flex items-center gap-2 text-stone-400 text-[11px]">
                 <div className="w-3 h-3 border-2 border-stone-300 border-t-emerald-500 rounded-full animate-spin" />
                 Waiting for verification...
               </div>
            </div>
          </div>
        )}

        {state === 'verified' && (
          <div className="text-center animate-in zoom-in duration-300">
            <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-4">
              <CheckCircle2 size={32} className="text-emerald-700" />
            </div>
            <div className="text-[18px] text-stone-900 mb-2">You're verified!</div>
            <div className="text-[13px] text-stone-600">Redirecting you back to your workspace...</div>
          </div>
        )}
      </div>
    </div>
  );
}
