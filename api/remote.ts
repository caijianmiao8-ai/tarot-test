// api/remote.ts
import type { VercelRequest, VercelResponse } from '@vercel/node';
import { supabaseAdmin } from '../lib/supabaseServer';
import { issueAppToken, verifyAppToken } from '../lib/jwt';
import { env, json, nowIso, randomDeviceCode, randomUserCode, readJsonBody } from '../lib/util';
import { requireAppAuth } from '../lib/authApp';

// ---- device handlers ----
async function deviceStart(req: VercelRequest, res: VercelResponse) {
  const body = await readJsonBody<{ interval?: number; expires_in?: number }>(req);
  const interval = body?.interval ?? 5;
  const expires_in = body?.expires_in ?? 600;
  const expires_at = new Date(Date.now() + expires_in * 1000).toISOString();
  const device_code = randomDeviceCode();
  const user_code = randomUserCode();

  const { error } = await supabaseAdmin.from('device_codes').insert({
    device_code,
    user_code,
    status: 'pending',
    interval,
    expires_at,
    created_at: nowIso()
  });

  if (error) {
    console.error('deviceStart error:', error);
    return json(res, 500, { error: error.message });
  }

  const verification_uri = `${env('PUBLIC_BASE_URL')}/device`;
  return json(res, 200, { device_code, user_code, verification_uri, interval, expires_in });
}

async function deviceApprove(req: VercelRequest, res: VercelResponse) {
  const auth = req.headers['authorization'];
  const token = auth?.toString().replace('Bearer ', '') || '';
  
  if (!token) {
    return json(res, 401, { error: 'missing_supabase_token' });
  }

  const { data: userRes, error: userErr } = await supabaseAdmin.auth.getUser(token);
  if (userErr || !userRes?.user) {
    return json(res, 401, { error: 'invalid_supabase_token' });
  }
  
  const uid = userRes.user.id;
  const body = await readJsonBody<{ device_code?: string; user_code?: string }>(req);
  const code = body?.device_code || body?.user_code;
  
  if (!code) {
    return json(res, 400, { error: 'device_code_or_user_code_required' });
  }

  const { data: rows, error } = await supabaseAdmin
    .from('device_codes')
    .select('*')
    .or(`device_code.eq.${code},user_code.eq.${code}`)
    .eq('status', 'pending')
    .limit(1);

  if (error) {
    return json(res, 500, { error: error.message });
  }

  const row = rows?.[0];
  if (!row) {
    return json(res, 404, { error: 'not_found_or_already_approved' });
  }

  const { error: upErr } = await supabaseAdmin
    .from('device_codes')
    .update({
      status: 'approved',
      approved_by_user_id: uid,
      approved_at: nowIso()
    })
    .eq('device_code', row.device_code);

  if (upErr) {
    return json(res, 500, { error: upErr.message });
  }

  return json(res, 200, { ok: true, device_code: row.device_code });
}

async function devicePoll(req: VercelRequest, res: VercelResponse) {
  const body = await readJsonBody<{ device_code?: string }>(req);
  const device_code = body?.device_code;
  
  if (!device_code) {
    return json(res, 400, { error: 'device_code_required' });
  }

  const { data: rows, error } = await supabaseAdmin
    .from('device_codes')
    .select('status, approved_by_user_id, expires_at')
    .eq('device_code', device_code)
    .limit(1);

  if (error) {
    return json(res, 500, { error: error.message });
  }

  const row = rows?.[0];
  if (!row) {
    return json(res, 404, { error: 'not_found' });
  }

  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) {
    return json(res, 200, { status: 'expired' });
  }

  if (row.status !== 'approved' || !row.approved_by_user_id) {
    return json(res, 200, { status: row.status || 'pending' });
  }

  const app_token = issueAppToken({ sub: row.approved_by_user_id }, 3600);
  return json(res, 200, {
    status: 'approved',
    app_token,
    user: { id: row.approved_by_user_id }
  });
}

// ---- session handlers ----
async function sessionsCreate(req: VercelRequest, res: VercelResponse) {
  const auth = requireAppAuth(req, res);
  if (!auth) return;

  const body = await readJsonBody<{ role?: string }>(req);
  const role = body?.role || 'controller';
  const code6 = Math.floor(100000 + Math.random() * 900000).toString();

  const { data, error } = await supabaseAdmin
    .from('remote_sessions')
    .insert({
      code6,
      owner_user: auth.uid,
      state: 'pending',
      created_at: nowIso(),
      meta: { role }
    })
    .select('id, code6')
    .single();

  if (error || !data) {
    return json(res, 500, { error: error?.message || 'insert_failed' });
  }

  return json(res, 200, { sessionId: data.id, code6: data.code6 ?? code6, ttl: 300 });
}

async function sessionsJoin(req: VercelRequest, res: VercelResponse) {
  const auth = requireAppAuth(req, res);
  if (!auth) return;

  const body = await readJsonBody<{ code6?: string; role?: string }>(req);
  const code6 = body?.code6;
  const role = body?.role;

  if (!code6 || !role) {
    return json(res, 400, { error: 'code6_and_role_required' });
  }

  const { data: sess, error } = await supabaseAdmin
    .from('remote_sessions')
    .select('*')
    .eq('code6', code6)
    .in('state', ['pending', 'connected'])
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    return json(res, 500, { error: error.message });
  }

  if (!sess) {
    return json(res, 404, { error: 'invalid_or_expired_code' });
  }

  const patch: any = { updated_at: nowIso() };
  if (sess.state !== 'connected') {
    patch.state = 'connected';
    patch.started_at = nowIso();
  }
  if (role === 'controller') patch.controller_user = auth.uid;
  if (role === 'host') patch.host_user = auth.uid;

  const { error: upErr, data } = await supabaseAdmin
    .from('remote_sessions')
    .update(patch)
    .eq('id', sess.id)
    .select('id')
    .single();

  if (upErr || !data) {
    return json(res, 500, { error: upErr?.message || 'update_failed' });
  }

  return json(res, 200, { sessionId: data.id });
}

async function sessionsClose(req: VercelRequest, res: VercelResponse) {
  const auth = requireAppAuth(req, res);
  if (!auth) return;

  const body = await readJsonBody<{ sessionId?: string }>(req);
  const sessionId = body?.sessionId;

  if (!sessionId) {
    return json(res, 400, { error: 'sessionId_required' });
  }

  const { error } = await supabaseAdmin
    .from('remote_sessions')
    .update({ state: 'closed', closed_at: nowIso() })
    .eq('id', sessionId);

  if (error) {
    return json(res, 500, { error: error.message });
  }

  return json(res, 200, { ok: true });
}

// ---- config / logs ----
async function realtimeSignedTopic(req: VercelRequest, res: VercelResponse) {
  const auth = requireAppAuth(req, res);
  if (!auth) return;

  const url = new URL(req.url || '', 'http://localhost');
  const sessionId = url.searchParams.get('sessionId');

  if (!sessionId) {
    return json(res, 400, { error: 'sessionId_required' });
  }

  return json(res, 200, {
    endpoint: env('NEXT_PUBLIC_SUPABASE_URL'),
    apikey: env('NEXT_PUBLIC_SUPABASE_ANON_KEY'),
    topic: `remote:${sessionId}`,
    signedToken: null,
    expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString()
  });
}

async function ice(req: VercelRequest, res: VercelResponse) {
  try {
    const js = env('ICE_SERVERS_JSON', '[]');
    const iceServers = JSON.parse(js);
    return json(res, 200, { iceServers });
  } catch {
    return json(res, 200, { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
  }
}

async function logs(req: VercelRequest, res: VercelResponse) {
  const auth = requireAppAuth(req, res);
  if (!auth) return;

  const body = await readJsonBody<{
    sessionId?: string;
    level?: string;
    message?: string;
    fields?: any;
  }>(req);

  const { sessionId, level = 'info', message, fields = null } = body || {};

  if (!sessionId || !message) {
    return json(res, 400, { error: 'sessionId_and_message_required' });
  }

  const stamp = nowIso();
  const { error } = await supabaseAdmin.from('remote_usage').insert({
    session_id: sessionId,
    user_id: auth.uid,
    seconds: 0,
    bytes_up: 0,
    bytes_down: 0,
    created_at: stamp,
    meta: { level, message, fields, timestamp: stamp }
  });

  if (error) {
    return json(res, 500, { error: error.message });
  }

  return json(res, 200, { ok: true });
}

// ---- main dispatcher ----
export default async function handler(req: VercelRequest, res: VercelResponse) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  try {
    const url = new URL(req.url || '', 'http://localhost');
    const op = url.searchParams.get('op');

    console.log('Remote API:', op, req.method);

    // 路由分发
    if (op === 'device-start' && req.method === 'POST') return deviceStart(req, res);
    if (op === 'device-approve' && req.method === 'POST') return deviceApprove(req, res);
    if (op === 'device-poll' && req.method === 'POST') return devicePoll(req, res);

    if (op === 'sessions-create' && req.method === 'POST') return sessionsCreate(req, res);
    if (op === 'sessions-join' && req.method === 'POST') return sessionsJoin(req, res);
    if (op === 'sessions-close' && req.method === 'POST') return sessionsClose(req, res);

    if (op === 'realtime-signed-topic' && req.method === 'GET') return realtimeSignedTopic(req, res);
    if (op === 'ice' && req.method === 'GET') return ice(req, res);
    if (op === 'logs' && req.method === 'POST') return logs(req, res);

    // 404
    return json(res, 404, {
      error: 'not_found',
      op,
      method: req.method,
      available: [
        'device-start (POST)',
        'device-approve (POST)',
        'device-poll (POST)',
        'sessions-create (POST)',
        'sessions-join (POST)',
        'sessions-close (POST)',
        'realtime-signed-topic (GET)',
        'ice (GET)',
        'logs (POST)'
      ]
    });
  } catch (e: any) {
    console.error('Unhandled error:', e);
    return json(res, 500, { error: e?.message || 'unhandled_error' });
  }
}