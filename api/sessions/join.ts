import type { VercelRequest, VercelResponse } from '@vercel/node';
import supabaseAdmin from '../../lib/supabaseServer';
import { requireAppAuth } from '../../lib/authApp';
import { json, nowIso, readJsonBody } from '../../lib/util';

type Role = 'host' | 'controller';

interface JoinSessionBody {
  code6?: string;
  role?: Role;
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'method_not_allowed' });
  }

  const auth = requireAppAuth(req, res);
  if (!auth) {
    return;
  }

  const body = (await readJsonBody<JoinSessionBody>(req)) ?? {};
  const code6 = body.code6?.trim();
  const role = body.role;

  if (!code6 || !role || (role !== 'host' && role !== 'controller')) {
    return json(res, 400, { error: 'invalid_request', message: 'code6 and role are required' });
  }

  const { data: session, error } = await supabaseAdmin
    .from('remote_sessions')
    .select('*')
    .eq('code6', code6)
    .in('state', ['pending', 'connected'])
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    return json(res, 500, { error: 'database_error', message: error.message });
  }

  if (!session) {
    return json(res, 404, { error: 'not_found' });
  }

  if (role === 'controller' && session.controller_user && session.controller_user !== auth.uid) {
    return json(res, 409, { error: 'conflict', message: 'controller already connected' });
  }

  if (role === 'host' && session.host_user && session.host_user !== auth.uid) {
    return json(res, 409, { error: 'conflict', message: 'host already connected' });
  }

  const updates: Record<string, unknown> = {};
  const now = nowIso();

  if (session.state !== 'connected') {
    updates.state = 'connected';
    updates.started_at = now;
  }

  if (role === 'controller') {
    updates.controller_user = auth.uid;
  } else {
    updates.host_user = auth.uid;
  }

  const { data: updated, error: updateError } = await supabaseAdmin
    .from('remote_sessions')
    .update(updates)
    .eq('id', session.id)
    .select('id')
    .single();

  if (updateError || !updated) {
    return json(res, 500, { error: 'database_error', message: updateError?.message ?? 'Failed to join session' });
  }

  return json(res, 200, { sessionId: updated.id });
}
