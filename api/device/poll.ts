import type { VercelRequest, VercelResponse } from '@vercel/node';
import supabaseAdmin from '../../lib/supabaseServer';
import { issueAppToken } from '../../lib/jwt';
import { json, readJsonBody } from '../../lib/util';

interface PollRequestBody {
  device_code?: string;
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'method_not_allowed' });
  }

  const body = (await readJsonBody<PollRequestBody>(req)) ?? {};
  const deviceCode = body.device_code?.trim();

  if (!deviceCode) {
    return json(res, 400, { error: 'invalid_request', message: 'device_code is required' });
  }

  const { data: record, error } = await supabaseAdmin
    .from('device_codes')
    .select('*')
    .eq('device_code', deviceCode)
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    return json(res, 500, { error: 'database_error', message: error.message });
  }

  if (!record) {
    return json(res, 404, { error: 'not_found' });
  }

  if (record.expires_at && new Date(record.expires_at).getTime() < Date.now()) {
    return json(res, 200, { status: 'expired' });
  }

  if (record.status !== 'approved') {
    return json(res, 200, { status: 'pending' });
  }

  if (!record.approved_by_user_id) {
    return json(res, 500, { error: 'invalid_state', message: 'approved record missing user' });
  }

  const appToken = issueAppToken(record.approved_by_user_id);

  return json(res, 200, {
    status: 'approved',
    app_token: appToken,
    user: { id: record.approved_by_user_id },
  });
}
