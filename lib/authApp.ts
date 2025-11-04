import { NextRequest, NextResponse } from 'next/server';
import { verifyAppToken, AppTokenPayload } from './jwt';

export interface AppAuthContext {
  uid: string;
  token: string;
  payload: AppTokenPayload;
}

export function requireAppAuth(req: NextRequest): AppAuthContext | NextResponse {
  const header = req.headers.get('authorization') || '';
  const match = header.match(/^Bearer\s+(.+)$/i);

  if (!match) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const token = match[1].trim();

  try {
    const payload = verifyAppToken(token);
    if (!payload?.sub) {
      throw new Error('Invalid token payload');
    }
    return { uid: payload.sub, token, payload };
  } catch (err) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
}
