import type { VercelRequest, VercelResponse } from '@vercel/node';
import supabaseAdmin from '../../lib/supabaseServer';
import { env, json, nowIso, randomDeviceCode, randomUserCode, readJsonBody } from '../../lib/util';

interface StartRequestBody {
  interval?: number | string;
  expires_in?: number | string;
}

function parseNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return undefined;
}

const DEFAULT_INTERVAL = 5;
const DEFAULT_EXPIRES_IN = 600;

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'method_not_allowed' });
  }

  const body = (await readJsonBody<StartRequestBody>(req)) ?? {};
  const intervalInput = parseNumber(body.interval);
  const expiresInput = parseNumber(body.expires_in);
  const interval = intervalInput !== undefined ? Math.max(1, Math.floor(intervalInput)) : DEFAULT_INTERVAL;
  const expiresIn = expiresInput !== undefined ? Math.max(60, Math.floor(expiresInput)) : DEFAULT_EXPIRES_IN;

  const deviceCode = randomDeviceCode();
  const userCode = randomUserCode();
  const createdAt = nowIso();
  const expiresAt = new Date(Date.now() + expiresIn * 1000).toISOString();

  const { error } = await supabaseAdmin.from('device_codes').insert({
    device_code: deviceCode,
    user_code: userCode,
    status: 'pending',
    interval,
    expires_at: expiresAt,
    created_at: createdAt,
  });

  if (error) {
    return json(res, 500, { error: 'database_error', message: error.message });
  }

  const verificationUri = `${env('PUBLIC_BASE_URL')}/device`;

  return json(res, 200, {
    device_code: deviceCode,
    user_code: userCode,
    verification_uri: verificationUri,
    interval,
    expires_in: expiresIn,
  });
}
