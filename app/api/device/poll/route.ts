import { NextRequest } from 'next/server';
import supabaseAdmin from '../../../../../lib/supabaseServer';
import { issueAppToken } from '../../../../../lib/jwt';
import { jsonResponse } from '../../../../../lib/util';

interface RequestBody {
  device_code?: string;
}

export async function POST(req: NextRequest) {
  let body: RequestBody = {};
  try {
    body = (await req.json()) as RequestBody;
  } catch (error) {
    body = {};
  }

  const { device_code } = body;

  if (!device_code) {
    return jsonResponse({ error: 'invalid_request', message: 'device_code is required' }, { status: 400 });
  }

  const { data: record, error } = await supabaseAdmin
    .from('device_codes')
    .select('*')
    .eq('device_code', device_code)
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error && error.code !== 'PGRST116') {
    return jsonResponse({ error: 'database_error', message: error.message }, { status: 500 });
  }

  if (!record) {
    return jsonResponse({ error: 'not_found' }, { status: 404 });
  }

  if (record.status !== 'approved') {
    return jsonResponse({ status: 'pending' });
  }

  const userId = record.approved_by_user_id || record.user_id || record.bound_user_id;

  if (!userId) {
    return jsonResponse({ error: 'invalid_device_code', message: 'Missing approved user information' }, { status: 500 });
  }

  const app_token = issueAppToken(userId);

  return jsonResponse({ status: 'approved', app_token, user: { id: userId } });
}
