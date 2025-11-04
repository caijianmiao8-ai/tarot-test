import { NextRequest } from 'next/server';
import supabaseAdmin from '../../../../../lib/supabaseServer';
import { env, jsonResponse, randomDeviceCode, randomUserCode } from '../../../../../lib/util';

export async function POST(req: NextRequest) {
  let body: Partial<{ interval: number; expires_in: number }> = {};
  try {
    body = (await req.json()) ?? {};
  } catch (error) {
    body = {};
  }

  const interval = typeof body.interval === 'number' && Number.isFinite(body.interval) ? Math.max(1, Math.floor(body.interval)) : 5;
  const expiresIn = typeof body.expires_in === 'number' && Number.isFinite(body.expires_in) ? Math.max(60, Math.floor(body.expires_in)) : 600;

  const device_code = randomDeviceCode();
  const user_code = randomUserCode();
  const verification_uri = `${env('PUBLIC_BASE_URL')}/device`;

  const { error } = await supabaseAdmin.from('device_codes').insert({
    device_code,
    user_code,
    status: 'pending',
    interval,
    expires_in: expiresIn,
    verification_uri,
    created_at: new Date().toISOString(),
  });

  if (error) {
    return jsonResponse({ error: 'failed_to_create_device_code', details: error.message }, { status: 500 });
  }

  return jsonResponse({ device_code, user_code, verification_uri, interval, expires_in: expiresIn });
}
