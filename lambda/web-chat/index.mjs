// Web Chat Lambda - discovers running claude-portable EC2 instance
// and proxies/redirects phone browser to it.
//
// GET /           -> serves mobile web UI (chat interface)
// POST /api/discover -> returns { ip, url } of running instance
// POST /api/prompt   -> relays prompt to EC2 web-chat, returns response

import { EC2Client, DescribeInstancesCommand } from '@aws-sdk/client-ec2';
import { WEB_UI } from './ui.mjs';

const ec2 = new EC2Client({ region: process.env.AWS_REGION || 'us-east-2' });
const API_TOKEN = process.env.API_TOKEN;
const WEB_CHAT_PORT = process.env.WEB_CHAT_PORT || '8888';

function json(statusCode, body) {
  return {
    statusCode,
    headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
    body: JSON.stringify(body)
  };
}

function html(body) {
  return {
    statusCode: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
    body
  };
}

function validateToken(headers) {
  if (!API_TOKEN) return true; // no token = open (dev mode)
  const auth = headers?.authorization || headers?.Authorization || '';
  const token = auth.replace('Bearer ', '');
  return token === API_TOKEN;
}

async function findRunningInstance() {
  const res = await ec2.send(new DescribeInstancesCommand({
    Filters: [
      { Name: 'tag:Project', Values: ['claude-portable'] },
      { Name: 'instance-state-name', Values: ['running'] }
    ]
  }));
  for (const r of res.Reservations || []) {
    for (const inst of r.Instances || []) {
      if (inst.PublicIpAddress) {
        const tags = Object.fromEntries((inst.Tags || []).map(t => [t.Key, t.Value]));
        return {
          id: inst.InstanceId,
          ip: inst.PublicIpAddress,
          name: tags.Name || inst.InstanceId,
          type: inst.InstanceType
        };
      }
    }
  }
  return null;
}

async function getWebChatToken(ip) {
  // Try to get the token from the running instance's web-chat health endpoint
  try {
    const res = await fetch(`http://${ip}:${WEB_CHAT_PORT}/health`, { signal: AbortSignal.timeout(3000) });
    if (res.ok) return { reachable: true };
  } catch {}
  return { reachable: false };
}

export async function handler(event) {
  const method = event.requestContext?.http?.method || event.httpMethod || 'GET';
  const path = event.rawPath || event.path || '/';

  // CORS preflight
  if (method === 'OPTIONS') {
    return {
      statusCode: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
      },
      body: ''
    };
  }

  // Serve web UI
  if (method === 'GET' && (path === '/' || path === '')) {
    return html(WEB_UI);
  }

  // Auth gate for API routes
  if (path.startsWith('/api/') && !validateToken(event.headers)) {
    return json(401, { error: 'Unauthorized' });
  }

  // Parse body
  let body = {};
  if (event.body) {
    try {
      const raw = event.isBase64Encoded ? Buffer.from(event.body, 'base64').toString() : event.body;
      body = JSON.parse(raw);
    } catch {
      return json(400, { error: 'Invalid JSON' });
    }
  }

  // Discover running instance
  if (path === '/api/discover') {
    const inst = await findRunningInstance();
    if (!inst) return json(200, { online: false, message: 'No running instance' });
    const status = await getWebChatToken(inst.ip);
    return json(200, {
      online: true,
      instance: inst,
      web_chat_url: `http://${inst.ip}:${WEB_CHAT_PORT}`,
      web_chat_reachable: status.reachable
    });
  }

  // Relay prompt to EC2 web-chat
  if (path === '/api/prompt') {
    const prompt = body.prompt || body.text;
    if (!prompt) return json(400, { error: 'prompt required' });

    const inst = await findRunningInstance();
    if (!inst) return json(503, { error: 'No running instance' });

    try {
      const res = await fetch(`http://${inst.ip}:${WEB_CHAT_PORT}/api/prompt?token=${API_TOKEN || ''}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, project: body.project || '/workspace' }),
        signal: AbortSignal.timeout(300000) // 5 min timeout for Claude
      });
      const data = await res.json();
      return json(200, data);
    } catch (e) {
      return json(502, { error: `Instance unreachable: ${e.message}` });
    }
  }

  return json(404, { error: `Unknown route: ${path}` });
}
