import type { Workspace, Asset, BrandKit, Design, DesignSpec, EditOp, LintViolation, Job } from '../types';

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'ApiError'; }
}
const part = encodeURIComponent;
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    const data: { error?: string } = await response.json().catch(() => ({}));
    throw new ApiError(response.status, data.error ?? response.statusText);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}
function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}
export const createWorkspace = (body: { name: string }) => request<Workspace>('/workspaces', json('POST', body));
export const listWorkspaces = () => request<Workspace[]>('/workspaces');
export const getWorkspace = (ws: string) => request<Workspace>(`/workspaces/${part(ws)}`);
export function uploadAsset(ws: string, file: File, kind: Asset['kind']) {
  const form = new FormData(); form.append('file', file); form.append('kind', kind);
  return request<Asset>(`/workspaces/${part(ws)}/assets`, { method: 'POST', body: form });
}
export const listAssets = (ws: string, kind?: Asset['kind']) => request<Asset[]>(`/workspaces/${part(ws)}/assets${kind ? `?kind=${part(kind)}` : ''}`);
export const deleteAsset = (id: string) => request<void>(`/assets/${part(id)}`, { method: 'DELETE' });
export async function getFile(assetId: string): Promise<Blob> {
  const response = await fetch(`/api/files/${part(assetId)}`);
  if (!response.ok) {
    const body: { error?: string } = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.error ?? response.statusText);
  }
  return response.blob();
}
export const extractBrandKit = (ws: string) => request<BrandKit>(`/workspaces/${part(ws)}/brand-kit/extract`, { method: 'POST' });
export const getBrandKit = (ws: string) => request<BrandKit>(`/workspaces/${part(ws)}/brand-kit`);
export const saveBrandKit = (ws: string, kit: BrandKit) => request<BrandKit>(`/workspaces/${part(ws)}/brand-kit`, json('PUT', kit));
export const lintDesign = (ws: string, design: Design) => request<LintViolation[]>(`/workspaces/${part(ws)}/lint`, json('POST', design));
export const listDesigns = (ws: string) => request<Design[]>(`/workspaces/${part(ws)}/designs`);
export const createDesign = (ws: string, design: Design) => request<Design>(`/workspaces/${part(ws)}/designs`, json('POST', design));
export const getDesign = (id: string) => request<Design>(`/designs/${part(id)}`);
export const saveDesign = (id: string, design: Design) => request<Design>(`/designs/${part(id)}`, json('PUT', design));
export function uploadSample(ws: string, file: File) {
  const form = new FormData(); form.append('file', file);
  return request<{ asset: Asset; spec: DesignSpec }>(`/workspaces/${part(ws)}/samples`, { method: 'POST', body: form });
}
export const decompose = (ws: string, body: { sampleAssetId: string }) => request<{ jobId: string }>(`/workspaces/${part(ws)}/decompose`, json('POST', body));
export const generateVariants = (ws: string, body: { sampleAssetId: string; brief?: string }) => request<{ jobId: string }>(`/workspaces/${part(ws)}/variants`, json('POST', body));
export const getJob = (jobId: string) => request<Job>(`/jobs/${part(jobId)}`);
export const editImage = (ws: string, body: { assetId: string; instruction: string }) => request<Asset>(`/workspaces/${part(ws)}/images/edit`, json('POST', body));
export const chat = (ws: string, body: { design: Design; selection: string[]; message: string }) => request<{ reply: string; ops: EditOp[] }>(`/workspaces/${part(ws)}/chat`, json('POST', body));

export const api = { createWorkspace, listWorkspaces, getWorkspace, uploadAsset, listAssets, deleteAsset, getFile,
  extractBrandKit, getBrandKit, saveBrandKit, lintDesign, listDesigns, createDesign, getDesign, saveDesign,
  uploadSample, decompose, generateVariants, getJob, editImage, chat };
