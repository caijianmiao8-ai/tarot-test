import jwt from 'jsonwebtoken';
import { env } from './util';

const APP_JWT_SECRET = () => env('APP_JWT_SECRET');

type ExpiresIn = string | number;

export interface AppTokenPayload {
  sub: string;
  exp?: number;
  [key: string]: unknown;
}

export function issueAppToken(userId: string, expiresIn: ExpiresIn = '1h', extraPayload: Record<string, unknown> = {}) {
  return jwt.sign({ sub: userId, ...extraPayload }, APP_JWT_SECRET(), { expiresIn });
}

export function verifyAppToken(token: string): AppTokenPayload {
  return jwt.verify(token, APP_JWT_SECRET()) as AppTokenPayload;
}
