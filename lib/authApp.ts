import type { VercelRequest, VercelResponse } from '@vercel/node';
import { verifyAppToken, AppTokenPayload } from './jwt';
import { json } from './util';

export interface AppAuthContext {
  uid: string;
  token: string;
  payload: AppTokenPayload;
}

function extractBearerToken(req: VercelRequest): string | null {
  const header = req.headers['authorization'];
  const value = Array.isArray(header) ? header[0] : header;
  if (!value) {
    return null;
  }
  const match = value.match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : null;
}

export function requireAppAuth(req: VercelRequest, res: VercelResponse): AppAuthContext | undefined {
  const token = extractBearerToken(req);
  if (!token) {
    json(res, 401, { error: 'unauthorized' });
    return undefined;
  }

  try {
    const payload = verifyAppToken(token);
    if (!payload?.sub) {
      throw new Error('Invalid token payload');
    }
    return { uid: payload.sub, token, payload };
  } catch (error) {
    json(res, 401, { error: 'unauthorized' });
    return undefined;
  }
}
