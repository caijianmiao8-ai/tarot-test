import { NextRequest, NextResponse } from 'next/server';
import supabaseAdmin from '../../../../../lib/supabaseServer';
import { requireAppAuth } from '../../../../../lib/authApp';
import { jsonResponse } from '../../../../../lib/util';

interface RequestBody {
  sessionId?: string;
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

  if (!body.sessionId) {
    return jsonResponse({ error: 'invalid_request', message: 'sessionId is required' }, { status: 400 });
  }

  const { data: session, error: fetchError } = await supabaseAdmin
    .from('remote_sessions')
    .select('id')
    .eq('id', body.sessionId)
    .limit(1)
    .maybeSingle();

  if (fetchError && fetchError.code !== 'PGRST116') {
    return jsonResponse({ error: 'database_error', message: fetchError.message }, { status: 500 });
  }

  if (!session) {
    return jsonResponse({ error: 'not_found' }, { status: 404 });
  }

  const { error: updateError } = await supabaseAdmin
    .from('remote_sessions')
    .update({
      state: 'closed',
      closed_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    .eq('id', body.sessionId);

  if (updateError) {
    return jsonResponse({ error: 'database_error', message: updateError.message }, { status: 500 });
  }

  return jsonResponse({ status: 'closed' });
}
