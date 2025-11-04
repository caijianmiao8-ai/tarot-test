import type { VercelRequest, VercelResponse } from '@vercel/node';
import supabaseAdmin from '../../lib/supabaseServer';
import { json, nowIso, readJsonBody } from '../../lib/util';

interface ApproveRequestBody {
  device_code?: string;
  user_code?: string;
}

function extractBearer(req: VercelRequest): string | null {
  const header = req.headers['authorization'];
  const value = Array.isArray(header) ? header[0] : header;
  if (!value) {
    return null;
  }
  const match = value.match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : null;
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'method_not_allowed' });
  }

  const accessToken = extractBearer(req);
  if (!accessToken) {
    return json(res, 401, { error: 'unauthorized' });
  }

  const { data: userResult, error: userError } = await supabaseAdmin.auth.getUser(accessToken);
  if (userError || !userResult?.user) {
    return json(res, 401, { error: 'unauthorized' });
  }

  const body = (await readJsonBody<ApproveRequestBody>(req)) ?? {};
  const { device_code: deviceCode, user_code: userCode } = body;

  if (!deviceCode && !userCode) {
    return json(res, 400, { error: 'invalid_request', message: 'device_code or user_code is required' });
  }

  let query = supabaseAdmin.from('device_codes').select('*').eq('status', 'pending');
  if (deviceCode) {
    query = query.eq('device_code', deviceCode);
  }
  if (userCode) {
    query = query.eq('user_code', userCode);
  }
  const { data: record, error } = await query.order('created_at', { ascending: false }).limit(1).maybeSingle();

  if (error) {
    return json(res, 500, { error: 'database_error', message: error.message });
  }

  if (!record) {
    return json(res, 404, { error: 'not_found' });
  }

  if (record.expires_at && new Date(record.expires_at).getTime() < Date.now()) {
    return json(res, 400, { error: 'expired', message: 'device code expired' });
  }

  const approvedAt = nowIso();
  const { data: updated, error: updateError } = await supabaseAdmin
    .from('device_codes')
    .update({
      status: 'approved',
      approved_by_user_id: userResult.user.id,
      approved_at: approvedAt,
    })
    .eq('id', record.id)
    .select('id')
    .maybeSingle();

  if (updateError) {
    return json(res, 500, { error: 'database_error', message: updateError.message });
  }

  if (!updated) {
    return json(res, 409, { error: 'conflict', message: 'device already approved' });
  }

  return json(res, 200, { status: 'approved' });
}
