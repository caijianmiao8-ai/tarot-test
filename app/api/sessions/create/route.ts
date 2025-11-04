import { NextRequest, NextResponse } from 'next/server';
import supabaseAdmin from '../../../../../lib/supabaseServer';
import { requireAppAuth } from '../../../../../lib/authApp';
import { jsonResponse, randomCode6 } from '../../../../../lib/util';

interface RequestBody {
  role?: 'controller';
}

export async function POST(req: NextRequest) {
  const auth = requireAppAuth(req);
  if (auth instanceof NextResponse) {
    return auth;
  }

  let body: RequestBody = {};
  try {
    body = (await req.json()) as RequestBody;
  } catch (error) {
    body = {};
  }

  if (body.role !== 'controller') {
    return jsonResponse({ error: 'invalid_request', message: 'role must be controller' }, { status: 400 });
  }

  const code6 = randomCode6();
  const expiresAt = new Date(Date.now() + 300 * 1000).toISOString();

  const { data, error } = await supabaseAdmin
    .from('remote_sessions')
    .insert({
      state: 'pending',
      code6,
      controller_user_id: auth.uid,
      created_by: auth.uid,
      expires_at: expiresAt,
      created_at: new Date().toISOString(),
    })
    .select()
    .single();

  if (error || !data) {
    return jsonResponse({ error: 'database_error', message: error?.message ?? 'Failed to create session' }, { status: 500 });
  }

  return jsonResponse({ sessionId: data.id, code6: data.code6 ?? code6, ttl: 300 });
}
