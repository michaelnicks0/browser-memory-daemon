const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const dist = path.join(root, 'dist');
fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(path.join(dist, 'src'), { recursive: true });

const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8'));
if (manifest.manifest_version !== 3) throw new Error('manifest must be MV3');
fs.writeFileSync(path.join(dist, 'manifest.json'), JSON.stringify(manifest, null, 2));

for (const file of fs.readdirSync(path.join(root, 'src'))) {
  fs.copyFileSync(path.join(root, 'src', file), path.join(dist, 'src', file));
}
console.log(`built extension dist at ${dist}`);
