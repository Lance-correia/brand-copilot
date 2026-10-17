// Self-check for folder classification: node apps/web/src/screens/folderKinds.check.ts
import { folderTag, groupByFolder, isUploadable, kindForFolder } from './folderKinds.ts';

const eq = (actual: unknown, expected: unknown) => {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(`expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
};

eq(kindForFolder('01_Guidelines'), 'guideline');
eq(kindForFolder('Logo safe zone'), 'guideline'); // guideline wins over logo
eq(kindForFolder('Logo_Rules'), 'guideline');
eq(kindForFolder('Safe-Zone'), 'guideline');
eq(kindForFolder('05_LOGOS'), 'logo');
eq(kindForFolder('Typography'), 'font');
eq(kindForFolder('fonts'), 'font');
eq(kindForFolder('10 Icons'), 'icon');
eq(kindForFolder('Charms'), 'icon');
eq(kindForFolder('References'), 'sample');
eq(kindForFolder('Ad samples'), 'sample');
eq(kindForFolder('Photography'), 'image');
eq(kindForFolder('2024'), 'image');
eq(folderTag('05_Brand Logos'), 'brand-logos');

eq(isUploadable('Pack/Logos/.DS_Store'), false);
eq(isUploadable('Pack/.hidden/a.png'), false);
eq(isUploadable('__MACOSX/Logos/a.png'), false);
eq(isUploadable('Pack/Docs/notes.txt'), false);
eq(isUploadable('Pack/Fonts/Inter.WOFF2'), true);
eq(isUploadable('Pack/Guide.pdf'), true);

const f = (path: string) => ({ file: new File([''], path.split('/').pop()!), path });
const summary = (paths: string[]) => groupByFolder(paths.map(f)).map(g => [g.folder, g.kind, g.files.length]);
// One picked root: group by the folder under it; root-level files keep the root name.
eq(summary(['Pack/05_Logos/a.svg', 'Pack/05_Logos/svg/b.svg', 'Pack/02_Fonts/x.ttf', 'Pack/cover.png', 'Pack/05_Logos/.DS_Store']),
  [['02_Fonts', 'font', 1], ['05_Logos', 'logo', 2], ['Pack', 'image', 1]]);
// Several dropped folders: group by each dropped folder.
eq(summary(['Logos/a.svg', 'Icons/i.svg', 'Icons/j.svg']), [['Icons', 'icon', 2], ['Logos', 'logo', 1]]);
// A single dropped folder with files directly inside.
eq(summary(['Typography/a.otf']), [['Typography', 'font', 1]]);
console.log('folderKinds: all checks passed');
