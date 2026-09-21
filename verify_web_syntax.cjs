const fs = require('node:fs');
for (const file of ['index.html', 'reference/index.html', 'white/index.html']) {
  const html = fs.readFileSync(file, 'utf8');
  for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
    if (match[0].includes('importmap')) continue;
    new Function(match[1].replace(/^\s*import .*;$/gm, ''));
  }
  console.log(file + ' syntax OK');
}
