import type { VercelRequest, VercelResponse } from '@vercel/node';
import { requireAppAuth } from '../../lib/authApp';
import { env, json } from '../../lib/util';

const TEN_MINUTES = 10 * 60 * 1000;

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return json(res, 405, { error: 'method_not_allowed' });
  }

  if (!requireAppAuth(req, res)) {
    return;
  }

  const sessionIdParam = req.query.sessionId;
  const sessionId = Array.isArray(sessionIdParam) ? sessionIdParam[0] : sessionIdParam;

  if (!sessionId) {
    return json(res, 400, { error: 'invalid_request', message: 'sessionId is required' });
  }

  const expiresAt = new Date(Date.now() + TEN_MINUTES).toISOString();

  return json(res, 200, {
    endpoint: env('NEXT_PUBLIC_SUPABASE_URL'),
    apikey: env('NEXT_PUBLIC_SUPABASE_ANON_KEY'),
    topic: `remote:${sessionId}`,
    signedToken: null,
    expires_at: expiresAt,
  });
}
