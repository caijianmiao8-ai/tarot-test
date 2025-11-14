import jwt, { JwtPayload, SignOptions, Secret } from 'jsonwebtoken';

const APP_JWT_SECRET = (process.env.APP_JWT_SECRET ?? '') as string;

if (!APP_JWT_SECRET) {
  console.warn('[jwt] APP_JWT_SECRET is not set. Set it in Vercel env.');
}

const secret: Secret = APP_JWT_SECRET;

export interface AppTokenPayload extends JwtPayload {
  sub: string;
  uid?: string;
}

export function issueAppToken(payload: { sub: string } | string, ttlSeconds: number = 3600): string {
  const options: SignOptions = { expiresIn: `${ttlSeconds}s`, algorithm: 'HS256' };
  return jwt.sign(payload, secret, options);
}

export function verifyAppToken(token: string): AppTokenPayload | null {
  try {
    const decoded = jwt.verify(token, secret) as AppTokenPayload;
    return decoded;
  } catch {
    return null;
  }
}