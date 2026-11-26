// Backend-for-frontend proxy. The browser calls /api/... on this Next.js server;
// this code adds the API key and forwards the request to FastAPI. The key never reaches the browser.
const API_URL = process.env.API_URL || 'http://localhost:8000';
const API_KEY = process.env.API_KEY || '';
const PASS_HEADERS = ['content-type', 'content-disposition', 'cache-control', 'x-content-type-options'];

async function proxy(request, { params }) {
  const { path } = await params;                       // ['v1', 'documents', '<id>']
  const url = `${API_URL}/api/${path.map(encodeURIComponent).join('/')}${new URL(request.url).search}`;

  const headers = { 'X-API-Key': API_KEY };
  const type = request.headers.get('content-type');    // keeps the multipart boundary for uploads
  if (type) headers['Content-Type'] = type;
  const hasBody = !['GET', 'HEAD'].includes(request.method);

  let upstream;
  try {
    upstream = await fetch(url, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: 'no-store',
    });
  } catch {
    return Response.json({ detail: 'The API is not reachable. Is the api container running?' }, { status: 502 });
  }

  const out = new Headers();
  for (const name of PASS_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  const body = [204, 304].includes(upstream.status) ? null : upstream.body;   // streamed, not buffered
  return new Response(body, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;