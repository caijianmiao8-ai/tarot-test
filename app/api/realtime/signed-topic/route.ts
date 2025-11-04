import { NextRequest, NextResponse } from 'next/server';
import { requireAppAuth } from '../../../../../lib/authApp';
import { env, jsonResponse } from '../../../../../lib/util';

export async function GET(req: NextRequest) {
  const auth = requireAppAuth(req);
  if (auth instanceof NextResponse) {
    return auth;
  }

  const sessionId = req.nextUrl.searchParams.get('sessionId');

  if (!sessionId) {
    return jsonResponse({ error: 'invalid_request', message: 'sessionId is required' }, { status: 400 });
  }

  const expiresAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();

  return jsonResponse({
    endpoint: env('NEXT_PUBLIC_SUPABASE_URL'),
    apikey: env('NEXT_PUBLIC_SUPABASE_ANON_KEY'),
    topic: `remote:${sessionId}`,
    signedToken: null,
    expires_at: expiresAt,
    todo: 'Issue limited JWT scoped to topic when SUPABASE_JWT_SECRET is available',
  });
}
