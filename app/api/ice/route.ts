import { NextRequest } from 'next/server';
import { jsonResponse } from '../../../../lib/util';

export async function GET(_req: NextRequest) {
  const fallback = [{ urls: 'stun:stun.l.google.com:19302' }];
  let iceServers = fallback;

  const raw = process.env.ICE_SERVERS_JSON;
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        iceServers = parsed;
      }
    } catch (error) {
      console.error('Failed to parse ICE_SERVERS_JSON', error);
    }
  }

  return jsonResponse({ iceServers });
}
