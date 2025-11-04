import type { VercelRequest, VercelResponse } from '@vercel/node';
import supabaseAdmin from '../lib/supabaseServer';
import { requireAppAuth } from '../lib/authApp';
import { json, nowIso, readJsonBody } from '../lib/util';

type LogLevel = 'info' | 'warn' | 'error';

interface LogRequestBody {
  sessionId?: string;
  level?: LogLevel;
  message?: string;
  fields?: Record<string, unknown>;
}

const ALLOWED_LEVELS: LogLevel[] = ['info', 'warn', 'error'];

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'method_not_allowed' });
  }

  const auth = requireAppAuth(req, res);
  if (!auth) {
    return;
  }

  const body = (await readJsonBody<LogRequestBody>(req)) ?? {};
  const sessionId = body.sessionId?.toString();
  const message = body.message?.toString();
  const level = body.level && ALLOWED_LEVELS.includes(body.level) ? body.level : 'info';

  if (!sessionId || !message) {
    return json(res, 400, { error: 'invalid_request', message: 'sessionId and message are required' });
  }

  const timestamp = nowIso();
  const meta = {
    level,
    message,
    fields: body.fields ?? null,
    timestamp,
    user: auth.uid,
  };

  const { error } = await supabaseAdmin
    .from('remote_usage')
    .insert({
      session_id: sessionId,
      user_id: auth.uid,
      meta,
      created_at: timestamp,
    });

  if (error) {
    return json(res, 500, { error: 'database_error', message: error.message });
  }

  return json(res, 200, { status: 'ok' });
}
