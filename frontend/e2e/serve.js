// Minimal static server for the production build with SPA fallback (no dependency): `node e2e/serve.js [port]`.
const http = require("http");
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const root = path.join(__dirname, "..", "build");
const port = Number(process.argv[2] || process.env.PORT || 3000);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".txt": "text/plain" };

http
  .createServer((req, res) => {
    const clean = decodeURIComponent(req.url.split("?")[0]);
    let file = path.join(root, clean);
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(root, "index.html");
    // Like the CDN in production: compressed text and long-lived hashed assets (keeps local performance audits honest).
    const type = types[path.extname(file)] || "application/octet-stream";
    const headers = { "content-type": type };
    if (clean.startsWith("/static/")) headers["cache-control"] = "public, max-age=31536000, immutable";
    const stream = fs.createReadStream(file);
    if (/\b(gzip)\b/.test(req.headers["accept-encoding"] || "") && /^(text|application\/(javascript|json)|image\/svg)/.test(type)) {
      headers["content-encoding"] = "gzip";
      res.writeHead(200, headers);
      stream.pipe(zlib.createGzip()).pipe(res);
    } else {
      res.writeHead(200, headers);
      stream.pipe(res);
    }
  })
  .listen(port, () => console.log(`serving ${root} on ${port}`));
