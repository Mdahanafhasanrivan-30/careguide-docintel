// Every call to the backend lives here, so pages never build URLs themselves.
// Paths start with /api: app/api/[...path]/route.js forwards them to FastAPI and adds the API key.

export const IN_PROGRESS = ['queued', 'parsing', 'extracting', 'validating'];
export const MAX_UPLOAD_MB = 50;   // keep equal to MAX_FILE_BYTES in backend/app/pipeline/parser.py

export const isBusy = (status) => IN_PROGRESS.includes(status);

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;          // 0 = network error; used to decide whether a retry makes sense
  }
}

function errorText(status, body) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;                          // HTTPException(409, '...')
  if (detail?.field) return `${detail.field}: ${detail.message}`;        // correction error (422)
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ');  // FastAPI validation error
  return `Request failed (HTTP ${status})`;
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(path, options);
  } catch {
    throw new ApiError('Network error: is the app running?', 0);
  }
  const body = await res.json().catch(() => null);   // some errors have no JSON body
  if (!res.ok) throw new ApiError(errorText(res.status, body), res.status);
  return body;
}

function query(params = {}) {
  // Drop empty values so the backend only sees filters the user actually set.
  const kept = Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined);
  return new URLSearchParams(kept).toString();
}

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const api = {
  list: (filters) => request(`/api/v1/documents?${query({ limit: 200, ...filters })}`),
  get: (id) => request(`/api/v1/documents/${id}`),
  history: (id) => request(`/api/v1/documents/${id}/history`),
  text: (id) => request(`/api/v1/documents/${id}/text`),
  fileUrl: (id) => `/api/v1/documents/${id}/file`,
  correct: (id, fields) => request(`/api/v1/documents/${id}/extraction`, json('PATCH', { fields })),
  reprocess: (id) => request(`/api/v1/documents/${id}/reprocess`, { method: 'POST' }),
  reprocessFailed: () => request('/api/v1/documents/reprocess-failed', { method: 'POST' }),
  search: (params) => request(`/api/v1/search?${query(params)}`),
};

// One file per request, so each file gets its own progress bar. fetch() cannot report
// upload progress; XMLHttpRequest can (xhr.upload.onprogress).
export function uploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/v1/documents');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body[0]);   // the API answers with a list
      else reject(new ApiError(errorText(xhr.status, body), xhr.status));
    };
    xhr.onerror = () => reject(new ApiError('Network error: is the app running?', 0));
    const form = new FormData();
    form.append('files', file);
    xhr.send(form);
  });
}