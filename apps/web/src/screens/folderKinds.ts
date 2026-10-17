import type { Asset } from '../types';

export type PathedFile = { file: File; path: string };
export type FolderGroup = { folder: string; tag: string; kind: Asset['kind']; files: File[] };

const UPLOADABLE = /\.(png|jpe?g|gif|webp|avif|bmp|svg|tiff?|ttf|otf|woff2?|pdf)$/i;

/** Folder name without a number prefix ("05_Logos" -> "logos"), lowercased, punctuation as spaces. */
const normalize = (folder: string) => folder.toLowerCase().replace(/^\d+[\s._-]*/, '').replace(/[^a-z0-9]+/g, ' ').trim();

export function kindForFolder(folder: string): Asset['kind'] {
  const name = normalize(folder);
  const has = (...words: string[]) => words.some(word => name.includes(word));
  if (has('guideline', 'safe zone', 'safezone', 'rules')) return 'guideline';
  if (has('logo')) return 'logo';
  if (has('font', 'typography')) return 'font';
  if (has('icon', 'charm')) return 'icon';
  if (has('reference', 'sample')) return 'sample';
  return 'image';
}

export const folderTag = (folder: string) => normalize(folder).replace(/ /g, '-');

/** Skip hidden files/folders (".DS_Store", ".git/…", "__MACOSX/…") and anything that isn't an image, font or PDF. */
export function isUploadable(path: string): boolean {
  const parts = path.split('/');
  return !parts.some(p => p.startsWith('.') || p === '__MACOSX') && UPLOADABLE.test(parts[parts.length - 1]);
}

/**
 * Groups files by their top-level folder. A single picked/dropped root ("Brand pack/05_Logos/a.svg")
 * groups by the folder under it; several dropped folders group by each dropped folder.
 */
export function groupByFolder(files: PathedFile[]): FolderGroup[] {
  const kept = files.filter(f => isUploadable(f.path));
  const dirs = kept.map(f => f.path.split('/').slice(0, -1));
  const singleRoot = dirs.length > 0 && dirs.every(d => d.length > 0 && d[0] === dirs[0][0]);
  const groups = new Map<string, File[]>();
  kept.forEach((f, i) => {
    const d = dirs[i];
    const folder = (singleRoot ? d[1] ?? d[0] : d[0]) ?? 'Loose files';
    groups.set(folder, [...(groups.get(folder) ?? []), f.file]);
  });
  return [...groups].map(([folder, list]) => ({ folder, tag: folderTag(folder), kind: kindForFolder(folder), files: list }))
    .sort((a, b) => a.folder.localeCompare(b.folder, undefined, { numeric: true }));
}
