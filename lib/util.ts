import type { VercelRequest, VercelResponse } from '@vercel/node';
import { randomBytes } from 'crypto';

export function env(name: string, fallback?: string): string {
  const value = process.env[name];
  if (value === undefined || value === '') {
    if (fallback !== undefined) {
      return fallback;
    }
    throw new Error(`Missing environment variable: ${name}`);
  }
  return value;
}

export function json<T>(res: VercelResponse, status: number, data: T) {
  res.status(status).json(data);
}

export function nowIso(): string {
  return new Date().toISOString();
}

const DIGITS = '0123456789';
const ALPHANUM = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

function randomFromCharset(length: number, charset: string): string {
  const bytes = randomBytes(length);
  let result = '';
  for (let i = 0; i < length; i += 1) {
    result += charset[bytes[i] % charset.length];
  }
  return result;
}

export function randomCode6(): string {
  return randomFromCharset(6, DIGITS);
}

export function randomDeviceCode(): string {
  return randomFromCharset(32, ALPHANUM);
}

export function randomUserCode(): string {
  const left = randomFromCharset(4, ALPHANUM);
  const right = randomFromCharset(4, ALPHANUM);
  return `${left}-${right}`;
}

export async function readJsonBody<T>(req: VercelRequest): Promise<T | undefined> {
  const existing = req.body;
  if (existing !== undefined) {
    if (typeof existing === 'string') {
      if (!existing) {
        return undefined;
      }
      try {
        return JSON.parse(existing) as T;
      } catch (error) {
        return undefined;
      }
    }
    if (Buffer.isBuffer(existing)) {
      if (!existing.length) {
        return undefined;
      }
      try {
        return JSON.parse(existing.toString('utf8')) as T;
      } catch (error) {
        return undefined;
      }
    }
    return existing as T;
  }

  return new Promise<T | undefined>((resolve) => {
    let data = '';
    req.on('data', (chunk) => {
      data += typeof chunk === 'string' ? chunk : chunk.toString('utf8');
    });
    req.on('end', () => {
      if (!data) {
        resolve(undefined);
        return;
      }
      try {
        resolve(JSON.parse(data) as T);
      } catch (error) {
        resolve(undefined);
      }
    });
    req.on('error', () => resolve(undefined));
  });
}
