import type { VercelRequest, VercelResponse } from '@vercel/node';
import { json } from '../lib/util';

const FALLBACK_ICE = [{ urls: 'stun:stun.l.google.com:19302' }];

function parseIceServers(): unknown[] {
  const raw = process.env.ICE_SERVERS_JSON;
  if (!raw) {
    return FALLBACK_ICE;
  }
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed;
    }
    return FALLBACK_ICE;
  } catch (error) {
    return FALLBACK_ICE;
  }
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return json(res, 405, { error: 'method_not_allowed' });
  }

  return json(res, 200, { iceServers: parseIceServers() });
}
