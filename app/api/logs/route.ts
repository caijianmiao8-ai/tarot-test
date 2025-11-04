import { NextRequest, NextResponse } from 'next/server';
import supabaseAdmin from '../../../../lib/supabaseServer';
import { requireAppAuth } from '../../../../lib/authApp';
import { jsonResponse } from '../../../../lib/util';

type LogLevel = 'info' | 'warn' | 'error';

interface RequestBody {
  sessionId?: string;
  level?: LogLevel;
  message?: string;
  fields?: Record<string, unknown>;
}

export async function POST(req: NextRequest) {
  const auth = requireAppAuth(req);
  if (auth instanceof NextResponse) {
    return auth;
  }

  let body: RequestBody = {};
  try {
    body = (await req.json()) as RequestBody;
  } catch (error) {
    body = {};
  }

  const { sessionId, level = 'info', message, fields } = body;

  if (!sessionId || !message) {
    return jsonResponse({ error: 'invalid_request', message: 'sessionId and message are required' }, { status: 400 });
  }

  const timestamp = new Date().toISOString();
  const meta = {
    sessionId,
    level,
    message,
    fields: fields ?? null,
    userId: auth.uid,
    timestamp,
  };

  const { error: insertError } = await supabaseAdmin.from('remote_usage').insert({
    session_id: sessionId,
    level,
    message,
    fields: fields ?? null,
    user_id: auth.uid,
    meta,
    created_at: timestamp,
  });

  if (insertError) {
    return jsonResponse({ error: 'database_error', message: insertError.message }, { status: 500 });
  }

  return jsonResponse({ status: 'ok' });
}
