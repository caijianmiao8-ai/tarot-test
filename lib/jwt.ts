// lib/jwt.ts
import jwt, { JwtPayload, SignOptions, Secret } from 'jsonwebtoken';

const APP_JWT_SECRET = (process.env.APP_JWT_SECRET ?? '') as string;

// 运行时兜底提示（编译不报错，运行时没有会返回 null）
if (!APP_JWT_SECRET) {
  console.warn('[jwt] APP_JWT_SECRET is not set. Set it in Vercel env.');
}

const secret: Secret = APP_JWT_SECRET;

export function issueAppToken(payload: object | string, ttlSeconds: number = 3600): string {
  // 用字符串 '3600s' 避免某些版本的类型窄化问题
  const options: SignOptions = { expiresIn: `${ttlSeconds}s`, algorithm: 'HS256' };
  return jwt.sign(payload, secret, options);
}

export function verifyAppToken<T extends JwtPayload = JwtPayload>(token: string): T | null {
  try {
    return jwt.verify(token, secret) as T;
  } catch {
    return null;
  }
}
