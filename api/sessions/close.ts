import type { VercelRequest, VercelResponse } from '@vercel/node';
import supabaseAdmin from '../../lib/supabaseServer';
import { requireAppAuth } from '../../lib/authApp';
import { json, nowIso, readJsonBody } from '../../lib/util';

interface CloseSessionBody {
  sessionId?: string;
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

  const body = (await readJsonBody<CloseSessionBody>(req)) ?? {};
  const sessionId = body.sessionId?.toString();

  if (!sessionId) {
    return json(res, 400, { error: 'invalid_request', message: 'sessionId is required' });
  }

  const { data: session, error: fetchError } = await supabaseAdmin
    .from('remote_sessions')
    .select('id, owner_user, controller_user, host_user, state')
    .eq('id', sessionId)
    .maybeSingle();

  if (fetchError) {
    return json(res, 500, { error: 'database_error', message: fetchError.message });
  }

  if (!session) {
    return json(res, 404, { error: 'not_found' });
  }

  if (
    session.owner_user !== auth.uid &&
    session.controller_user !== auth.uid &&
    session.host_user !== auth.uid
  ) {
    return json(res, 403, { error: 'forbidden' });
  }

  if (session.state === 'closed') {
    return json(res, 200, { sessionId: session.id, status: 'closed' });
  }

  const { data, error } = await supabaseAdmin
    .from('remote_sessions')
    .update({
      state: 'closed',
      closed_at: nowIso(),
    })
    .eq('id', session.id)
    .select('id')
    .maybeSingle();

  if (error) {
    return json(res, 500, { error: 'database_error', message: error.message });
  }

  if (!data) {
    return json(res, 500, { error: 'database_error', message: 'Failed to close session' });
  }

  return json(res, 200, { sessionId: data.id, status: 'closed' });
}
