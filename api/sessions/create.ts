import type { VercelRequest, VercelResponse } from '@vercel/node';
import supabaseAdmin from '../../lib/supabaseServer';
import { requireAppAuth } from '../../lib/authApp';
import { json, nowIso, randomCode6, readJsonBody } from '../../lib/util';

interface CreateSessionBody {
  role?: 'controller';
}

const SESSION_TTL_SECONDS = 300;

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'method_not_allowed' });
  }

  const auth = requireAppAuth(req, res);
  if (!auth) {
    return;
  }

  const body = (await readJsonBody<CreateSessionBody>(req)) ?? {};
  if (body.role !== 'controller') {
    return json(res, 400, { error: 'invalid_request', message: 'role must be controller' });
  }

  const code6 = randomCode6();
  const createdAt = nowIso();

  const { data, error } = await supabaseAdmin
    .from('remote_sessions')
    .insert({
      code6,
      owner_user: auth.uid,
      state: 'pending',
      created_at: createdAt,
      meta: { role: 'controller' },
    })
    .select('id, code6')
    .single();

  if (error || !data) {
    return json(res, 500, { error: 'database_error', message: error?.message ?? 'Failed to create session' });
  }

  return json(res, 200, {
    sessionId: data.id,
    code6: data.code6 ?? code6,
    ttl: SESSION_TTL_SECONDS,
  });
}
