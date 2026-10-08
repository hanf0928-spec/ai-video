
import axios from 'axios'

export const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

http.interceptors.response.use(
  (r) => r,
  (e) => {
    const msg = e?.response?.data?.message || e.message
    console.error('[http]', msg)
    return Promise.reject(new Error(msg))
  },
)

// ---------- Projects ----------
export const listProjects = () => http.get('/projects').then((r) => r.data)
export const createProject = (data: any) => http.post('/projects', data).then((r) => r.data)
export const getProject = (id: string) => http.get(`/projects/${id}`).then((r) => r.data)
export const updateProject = (id: string, data: any) => http.patch(`/projects/${id}`, data).then((r) => r.data)
export const deleteProject = (id: string) => http.delete(`/projects/${id}`).then((r) => r.data)

// ---------- Episodes & Shots ----------
export const listEpisodes = (projectId: string) => http.get(`/projects/${projectId}/episodes`).then((r) => r.data)
export const createEpisode = (data: any) => http.post('/episodes', data).then((r) => r.data)
export const getEpisode = (id: string) => http.get(`/episodes/${id}`).then((r) => r.data)
export const listShots = (episodeId: string) => http.get(`/episodes/${episodeId}/shots`).then((r) => r.data)
export const createShot = (data: any) => http.post('/shots', data).then((r) => r.data)
export const updateShot = (id: string, data: any) => http.patch(`/shots/${id}`, data).then((r) => r.data)
export const deleteShot = (id: string) => http.delete(`/shots/${id}`).then((r) => r.data)

// ---------- Library ----------
export const listCharacters = (projectId: string) => http.get(`/projects/${projectId}/characters`).then((r) => r.data)
export const createCharacter = (data: any) => http.post('/characters', data).then((r) => r.data)
export const listScenes = (projectId: string) => http.get(`/projects/${projectId}/scenes`).then((r) => r.data)
export const createScene = (data: any) => http.post('/scenes', data).then((r) => r.data)

// ---------- Manga ----------
export const uploadManga = (projectId: string, file: File) => {
  const fd = new FormData()
  fd.append('project_id', projectId)
  fd.append('file', file)
  return http.post('/manga/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data)
}
export const listUploads = (projectId: string) => http.get(`/manga/uploads/${projectId}`).then((r) => r.data)
export const convertManga = (data: any) => http.post('/manga/convert', data).then((r) => r.data)

// ---------- Generate ----------
export const generateScript = (data: any) => http.post('/generate/script', data).then((r) => r.data)
export const generateShot = (data: any) => http.post('/generate/shot', data).then((r) => r.data)
export const generateEpisode = (data: any) => http.post('/generate/episode', data).then((r) => r.data)

// ---------- Jobs ----------
export const listJobs = (projectId?: string) =>
  http.get('/jobs', { params: projectId ? { project_id: projectId } : {} }).then((r) => r.data)
export const getJob = (id: string) => http.get(`/jobs/${id}`).then((r) => r.data)

export function openJobWS(jobId: string, onMessage: (data: any) => void): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/api/jobs/ws/${jobId}`)
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch { /* ignore */ }
  }
  return ws
}

// ---------- Comfy ----------
export const comfyHealth = () => http.get('/comfy/health').then((r) => r.data)
export const listWorkflows = () => http.get('/comfy/workflows').then((r) => r.data)
export const runWorkflow = (data: any) => http.post('/comfy/run', data).then((r) => r.data)

// ---------- Model Config ----------
export const listProviders = () => http.get('/config/providers').then((r) => r.data)
export const getProvider = (name: string) => http.get(`/config/providers/${name}`).then((r) => r.data)
export const saveProvider = (name: string, body: any) => http.put(`/config/providers/${name}`, body).then((r) => r.data)
export const testProvider = (name: string) => http.post(`/config/providers/${name}/test`).then((r) => r.data)
export const clearProvider = (name: string) => http.delete(`/config/providers/${name}`).then((r) => r.data)
