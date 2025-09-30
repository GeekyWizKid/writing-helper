#!/usr/bin/env node
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, '..');

function run(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: 'inherit', cwd: root, ...opts });
    p.on('close', (code) => {
      if (code === 0) resolve(); else reject(new Error(`${cmd} ${args.join(' ')} exited ${code}`));
    });
    p.on('error', reject);
  });
}

async function exists(p) {
  try { await fs.access(p); return true; } catch { return false; }
}

async function ensureDir(p) {
  await fs.mkdir(p, { recursive: true });
}

async function cp(src, dest) {
  await fs.cp(src, dest, { recursive: true, force: true });
}

async function main() {
  const skipBuild = process.env.NO_BUILD === '1' || process.argv.includes('--no-build');

  if (!skipBuild) {
    console.log('> Building Next.js (standalone)...');
    await run('npm', ['run', '-s', 'build']);
  } else {
    console.log('> Skipping build (NO_BUILD=1)');
  }

  const nextDir = path.join(root, '.next');
  const standaloneDir = path.join(nextDir, 'standalone');
  const outDir = path.join(root, 'dist');

  if (!(await exists(standaloneDir))) {
    throw new Error('Missing .next/standalone. Please run build first.');
  }

  // Reassemble dist
  console.log('> Assembling dist...');
  await fs.rm(outDir, { recursive: true, force: true });
  await ensureDir(outDir);
  await cp(standaloneDir + path.sep, outDir + path.sep);

  // Copy static and public
  const nextStatic = path.join(nextDir, 'static');
  const distNext = path.join(outDir, '.next');
  await ensureDir(distNext);
  if (await exists(nextStatic)) {
    await cp(nextStatic, path.join(distNext, 'static'));
  }
  const publicDir = path.join(root, 'public');
  if (await exists(publicDir)) {
    await cp(publicDir, path.join(outDir, 'public'));
  }

  // Write ESM entry
  console.log('> Writing dist/index.js');
  const entry = `import('./server.js').catch(err => {\n  console.error('Failed to start Next standalone server:', err);\n  setTimeout(() => process.exit(1), 10);\n});\n`;
  await fs.writeFile(path.join(outDir, 'index.js'), entry, 'utf8');

  // Compose cherry-node.json at repo root
  let name = 'writing-helper';
  let version = '1.0.0';
  const cherryStudioPath = path.join(root, 'cherry-studio.json');
  if (await exists(cherryStudioPath)) {
    try {
      const raw = await fs.readFile(cherryStudioPath, 'utf8');
      const j = JSON.parse(raw || '{}');
      name = typeof j.name === 'string' && j.name.trim() ? j.name.trim() : name;
      version = typeof j.version === 'string' && j.version.trim() ? j.version.trim() : version;
    } catch {}
  }
  const manifest = { name, version, entry: 'dist/index.js' };
  const manifestPath = path.join(root, 'cherry-node.json');
  await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2), 'utf8');

  // Zip: require system zip
  const stamp = new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 14);
  const zipName = `cherry-package-${stamp}.zip`;
  const zipPath = path.join(outDir, zipName);
  console.log('> Creating zip:', zipPath);
  await run('zip', ['-rq', zipPath, 'cherry-node.json', 'dist']);
  await fs.copyFile(zipPath, path.join(outDir, 'cherry-package.zip'));

  console.log('\n✅ Done');
  console.log('  -', zipPath);
  console.log('  -', path.join(outDir, 'cherry-package.zip'));
}

main().catch((err) => {
  console.error('Package failed:', err);
  process.exit(1);
});

