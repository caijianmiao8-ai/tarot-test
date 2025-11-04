import { NextRequest, NextResponse } from 'next/server';
import supabaseAdmin from '../../../../../lib/supabaseServer';
import { requireAppAuth } from '../../../../../lib/authApp';
import { jsonResponse } from '../../../../../lib/util';

type Role = 'host' | 'controller';

interface RequestBody {
  code6?: string;
  role?: Role;
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

  const { code6, role } = body;

  if (!code6 || !role || !['host', 'controller'].includes(role)) {
    return jsonResponse({ error: 'invalid_request', message: 'code6 and role are required' }, { status: 400 });
  }

  const { data: session, error } = await supabaseAdmin
    .from('remote_sessions')
    .select('*')
    .eq('code6', code6)
    .in('state', ['pending', 'connected'])
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error && error.code !== 'PGRST116') {
    return jsonResponse({ error: 'database_error', message: error.message }, { status: 500 });
  }

  if (!session) {
    return jsonResponse({ error: 'not_found' }, { status: 404 });
  }

  if (role === 'controller' && session.controller_user_id && session.controller_user_id !== auth.uid) {
    return jsonResponse({ error: 'conflict', message: 'Controller already joined' }, { status: 409 });
  }

  if (role === 'host' && session.host_user_id && session.host_user_id !== auth.uid) {
    return jsonResponse({ error: 'conflict', message: 'Host already joined' }, { status: 409 });
  }

  const updates: Record<string, unknown> = {
    updated_at: new Date().toISOString(),
  };

  if (session.state !== 'connected') {
    updates.state = 'connected';
  }

  if (role === 'controller') {
    updates.controller_user_id = auth.uid;
    updates.controller_connected_at = new Date().toISOString();
  } else {
    updates.host_user_id = auth.uid;
    updates.host_connected_at = new Date().toISOString();
  }

  const { error: updateError, data } = await supabaseAdmin
    .from('remote_sessions')
    .update(updates)
    .eq('id', session.id)
    .select('id')
    .single();

  if (updateError || !data) {
    return jsonResponse({ error: 'database_error', message: updateError?.message ?? 'Failed to join session' }, { status: 500 });
  }

  return jsonResponse({ sessionId: data.id });
}
