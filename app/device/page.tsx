'use client';

import { FormEvent, useMemo, useState, useTransition } from 'react';
import { createClient, SupabaseClient } from '@supabase/supabase-js';

function useSupabase(): SupabaseClient | null {
  return useMemo(() => {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!url || !anonKey) {
      console.error('Missing Supabase environment variables');
      return null;
    }
    return createClient(url, anonKey);
  }, []);
}

export default function DeviceBindingPage() {
  const supabase = useSupabase();
  const [code, setCode] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatus(null);
    setError(null);

    if (!code.trim()) {
      setError('请输入设备验证码');
      return;
    }

    startTransition(async () => {
      try {
        let accessToken: string | null = null;
        if (supabase) {
          const { data } = await supabase.auth.getSession();
          accessToken = data?.session?.access_token ?? null;
        }

        if (!accessToken) {
          setError('请先登录账号再进行绑定。');
          return;
        }

        const response = await fetch('/api/device/approve', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ device_code: code.trim() }),
        });

        const data = await response.json();

        if (!response.ok) {
          setError(data?.message || data?.error || '绑定失败，请重试');
          return;
        }

        setStatus('设备绑定成功，可以返回客户端继续操作。');
        setCode('');
      } catch (err) {
        console.error(err);
        setError('网络错误，请稍后再试');
      }
    });
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4 py-16 text-white">
      <div className="w-full max-w-md rounded-lg bg-slate-900 p-6 shadow-xl ring-1 ring-slate-700/60">
        <h1 className="text-2xl font-semibold">绑定远程设备</h1>
        <p className="mt-2 text-sm text-slate-300">
          登录成功后，在下方输入客户端展示的设备验证码，即可完成绑定。
        </p>
        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <label className="block text-sm font-medium text-slate-200">
            设备验证码
            <input
              className="mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-base text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
              placeholder="例如：ABCD-1234"
              value={code}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
            />
          </label>
          <button
            type="submit"
            disabled={isPending}
            className="w-full rounded-md bg-sky-500 px-4 py-2 text-center text-base font-semibold text-white shadow-lg hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isPending ? '绑定中…' : '确认绑定'}
          </button>
        </form>
        {status && <p className="mt-4 rounded-md bg-emerald-500/10 p-3 text-sm text-emerald-300">{status}</p>}
        {error && <p className="mt-4 rounded-md bg-rose-500/10 p-3 text-sm text-rose-300">{error}</p>}
      </div>
    </main>
  );
}
