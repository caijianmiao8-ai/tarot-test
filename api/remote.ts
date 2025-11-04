// api/remote.ts
import { supabaseAdmin } from '../lib/supabaseServer'
import { issueAppToken, verifyAppToken } from '../lib/jwt'

// ---- utilities ----
function send(res: any, status: number, data: any) {
  res.statusCode = status
  res.setHeader('content-type', 'application/json')
  res.end(JSON.stringify(data))
}
function ok(res: any, data: any) { send(res, 200, data) }
function bad(res: any, m = 'bad_request') { send(res, 400, { error: m }) }
function unauthorized(res: any, m = 'unauthorized') { send(res, 401, { error: m }) }
function serverErr(res: any, m = 'server_error') { send(res, 500, { error: m }) }
function getEnv(name: string, def?: string) {
  const v = process.env[name]
  if (v) return v
  if (def !== undefined) return def
  throw new Error(`Missing env: ${name}`)
}
function parseJSON(body: any) {
  if (!body) return {}
  if (typeof body === 'string') { try { return JSON.parse(body) } catch { return {} } }
  return body
}
function bearerUid(req: any): string | null {
  const auth = req.headers?.authorization || ''
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : ''
  if (!token) return null
  try {
    const claims = verifyAppToken(token) as any
    return claims?.sub || claims?.uid || null
  } catch { return null }
}

// ---- device handlers ----
async function deviceStart(req: any, res: any) {
  const now = Date.now()
  const body = parseJSON(req.body)
  const interval = Number(body?.interval ?? 5)
  const expires_in = Number(body?.expires_in ?? 600)
  const expires_at = new Date(now + expires_in * 1000).toISOString()
  const device_code = 'dc_' + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2)
  const user_code = Math.random().toString(36).slice(2, 6).toUpperCase() + '-' + Math.floor(1000 + Math.random()*9000)

  const { error } = await supabaseAdmin.from('device_codes').insert({
    device_code, user_code, status: 'pending', interval, expires_at, created_at: new Date().toISOString()
  })
  if (error) return serverErr(res, error.message)

  const verification_uri = `${getEnv('PUBLIC_BASE_URL')}/device`
  ok(res, { device_code, user_code, verification_uri, interval, expires_in })
}

async function deviceApprove(req: any, res: any) {
  // 浏览器端会传 Supabase access_token（不是 app_token）
  const auth = req.headers?.authorization || ''
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : ''
  if (!token) return unauthorized(res, 'missing_supabase_token')

  const { data: userRes, error: userErr } = await supabaseAdmin.auth.getUser(token)
  if (userErr || !userRes?.user) return unauthorized(res, 'invalid_supabase_token')
  const uid = userRes.user.id

  const body = parseJSON(req.body)
  const code = body?.device_code || body?.user_code
  if (!code) return bad(res, 'device_code_or_user_code_required')

  const { data: rows, error } = await supabaseAdmin
    .from('device_codes')
    .select('*')
    .or(`device_code.eq.${code},user_code.eq.${code}`)
    .eq('status','pending')
    .limit(1)
  if (error) return serverErr(res, error.message)
  const row = rows?.[0]
  if (!row) return send(res, 404, { error: 'not_found_or_already_approved' })

  const { error: upErr } = await supabaseAdmin
    .from('device_codes')
    .update({ status: 'approved', approved_by_user_id: uid, approved_at: new Date().toISOString() })
    .eq('device_code', row.device_code)
  if (upErr) return serverErr(res, upErr.message)

  ok(res, { ok: true, device_code: row.device_code })
}

async function devicePoll(req: any, res: any) {
  const body = parseJSON(req.body)
  const device_code = body?.device_code
  if (!device_code) return bad(res, 'device_code_required')

  const { data: rows, error } = await supabaseAdmin
    .from('device_codes')
    .select('status, approved_by_user_id, expires_at')
    .eq('device_code', device_code)
    .limit(1)
  if (error) return serverErr(res, error.message)
  const row = rows?.[0]
  if (!row) return send(res, 404, { error: 'not_found' })

  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) return ok(res, { status: 'expired' })
  if (row.status !== 'approved' || !row.approved_by_user_id) return ok(res, { status: row.status || 'pending' })

  const app_token = issueAppToken(row.approved_by_user_id, 60*60)
  ok(res, { status: 'approved', app_token, user: { id: row.approved_by_user_id } })
}

// ---- session handlers ----
function needUid(req: any, res: any): string | null {
  const uid = bearerUid(req)
  if (!uid) { unauthorized(res); return null }
  return uid
}
function code6() { return Math.floor(100000 + Math.random()*900000).toString() }

async function sessionsCreate(req: any, res: any) {
  const uid = needUid(req, res); if (!uid) return
  const body = parseJSON(req.body)
  const role = body?.role || 'controller'
  const c6 = code6()
  const { data, error } = await supabaseAdmin
    .from('remote_sessions')
    .insert({ code6: c6, owner_user: uid, state: 'pending', created_at: new Date().toISOString(), meta: { role } })
    .select('id, code6')
    .single()
  if (error || !data) return serverErr(res, error?.message || 'insert_failed')
  ok(res, { sessionId: data.id, code6: data.code6 ?? c6, ttl: 300 })
}

async function sessionsJoin(req: any, res: any) {
  const uid = needUid(req, res); if (!uid) return
  const body = parseJSON(req.body)
  const c6 = body?.code6; const role = body?.role
  if (!c6 || !role) return bad(res, 'code6_and_role_required')

  const { data: sess, error } = await supabaseAdmin
    .from('remote_sessions')
    .select('*')
    .eq('code6', c6)
    .in('state', ['pending','connected'])
    .order('created_at', { ascending: false })
    .limit(1).maybeSingle()
  if (error) return serverErr(res, error.message)
  if (!sess) return send(res, 404, { error: 'invalid_or_expired_code' })

  const patch: any = { updated_at: new Date().toISOString() }
  if (sess.state !== 'connected') { patch.state = 'connected'; patch.started_at = new Date().toISOString() }
  if (role === 'controller') patch.controller_user = uid
  if (role === 'host') patch.host_user = uid

  const { error: upErr, data } = await supabaseAdmin
    .from('remote_sessions')
    .update(patch)
    .eq('id', sess.id)
    .select('id').single()
  if (upErr || !data) return serverErr(res, upErr?.message || 'update_failed')

  ok(res, { sessionId: data.id })
}

async function sessionsClose(req: any, res: any) {
  const uid = needUid(req, res); if (!uid) return
  const body = parseJSON(req.body)
  const sessionId = body?.sessionId
  if (!sessionId) return bad(res, 'sessionId_required')
  const { error } = await supabaseAdmin
    .from('remote_sessions')
    .update({ state: 'closed', closed_at: new Date().toISOString() })
    .eq('id', sessionId)
  if (error) return serverErr(res, error.message)
  ok(res, { ok: true })
}

// ---- config / logs ----
async function realtimeSignedTopic(req: any, res: any) {
  const uid = needUid(req, res); if (!uid) return
  const url = new URL(req.url, 'http://x')
  const sessionId = url.searchParams.get('sessionId')
  if (!sessionId) return bad(res, 'sessionId_required')
  ok(res, {
    endpoint: getEnv('NEXT_PUBLIC_SUPABASE_URL'),
    apikey: getEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY'),
    topic: `remote:${sessionId}`,
    signedToken: null, // MVP
    expires_at: new Date(Date.now() + 10*60*1000).toISOString()
  })
}

async function ice(req: any, res: any) {
  try {
    const js = getEnv('ICE_SERVERS_JSON', '[]')
    const iceServers = JSON.parse(js)
    ok(res, { iceServers })
  } catch {
    ok(res, { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] })
  }
}

async function logs(req: any, res: any) {
  const uid = needUid(req, res); if (!uid) return
  const body = parseJSON(req.body)
  const { sessionId, level='info', message, fields=null } = body || {}
  if (!sessionId || !message) return bad(res, 'sessionId_and_message_required')
  const stamp = new Date().toISOString()
  const { error } = await supabaseAdmin
    .from('remote_usage')
    .insert({ session_id: sessionId, user_id: uid, seconds: 0, bytes_up: 0, bytes_down: 0, created_at: stamp, meta: { level, message, fields, timestamp: stamp } as any })
  if (error) return serverErr(res, error.message)
  ok(res, { ok: true })
}

// ---- main dispatcher ----
export default async function handler(req: any, res: any) {
  try {
    const url = new URL(req.url, 'http://x')
    const op = url.searchParams.get('op')

    // 按 routes 映射的 op 分发
    if (op === 'device-start'      && req.method === 'POST') return deviceStart(req, res)
    if (op === 'device-approve'    && req.method === 'POST') return deviceApprove(req, res)
    if (op === 'device-poll'       && req.method === 'POST') return devicePoll(req, res)

    if (op === 'sessions-create'   && req.method === 'POST') return sessionsCreate(req, res)
    if (op === 'sessions-join'     && req.method === 'POST') return sessionsJoin(req, res)
    if (op === 'sessions-close'    && req.method === 'POST') return sessionsClose(req, res)

    if (op === 'realtime-signed-topic' && req.method === 'GET')  return realtimeSignedTopic(req, res)
    if (op === 'ice'                   && req.method === 'GET')  return ice(req, res)
    if (op === 'logs'                  && req.method === 'POST') return logs(req, res)

    // 兜底
    return send(res, 404, { error: 'not_found', op, method: req.method })
  } catch (e: any) {
    return serverErr(res, e?.message || 'unhandled_error')
  }
}
