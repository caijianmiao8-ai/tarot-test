import { NextRequest } from 'next/server';
import supabaseAdmin from '../../../../../lib/supabaseServer';
import { jsonResponse } from '../../../../../lib/util';

interface RequestBody {
  device_code?: string;
  user_code?: string;
}

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get('authorization') || '';
  const match = authHeader.match(/^Bearer\s+(.+)$/i);
  if (!match) {
    return jsonResponse({ error: 'unauthorized' }, { status: 401 });
  }

  const accessToken = match[1].trim();
  const { data: userData, error: userError } = await supabaseAdmin.auth.getUser(accessToken);

  if (userError || !userData?.user) {
    return jsonResponse({ error: 'unauthorized' }, { status: 401 });
  }

  let body: RequestBody = {};
  try {
    body = (await req.json()) as RequestBody;
  } catch (error) {
    body = {};
  }

  const { device_code, user_code } = body;

  if (!device_code && !user_code) {
    return jsonResponse({ error: 'invalid_request', message: 'device_code or user_code is required' }, { status: 400 });
  }

  let query = supabaseAdmin.from('device_codes').select('*').eq('status', 'pending');

  if (device_code) {
    query = query.eq('device_code', device_code);
  }

  if (user_code) {
    query = query.eq('user_code', user_code);
  }

  const { data: record, error } = await query.order('created_at', { ascending: false }).limit(1).maybeSingle();

  if (error && error.code !== 'PGRST116') {
    return jsonResponse({ error: 'database_error', message: error.message }, { status: 500 });
  }

  if (!record) {
    return jsonResponse({ error: 'not_found' }, { status: 404 });
  }

  const updatePayload: Record<string, unknown> = {
    status: 'approved',
    approved_by_user_id: userData.user.id,
    approved_at: new Date().toISOString(),
  };

  const { error: updateError } = await supabaseAdmin
    .from('device_codes')
    .update(updatePayload)
    .eq('device_code', record.device_code);

  if (updateError) {
    return jsonResponse({ error: 'database_error', message: updateError.message }, { status: 500 });
  }

  return jsonResponse({ status: 'approved' });
}
