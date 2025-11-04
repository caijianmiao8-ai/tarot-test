import { randomBytes } from 'crypto';
import { NextResponse } from 'next/server';

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

export function jsonResponse<T>(data: T, init?: ResponseInit) {
  return NextResponse.json(data, init);
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
