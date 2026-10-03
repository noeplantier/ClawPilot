// Minimal static server for the production build with SPA fallback (no dependency): `node e2e/serve.js [port]`.
const http = require("http");
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "build");
const port = Number(process.argv[2] || process.env.PORT || 3000);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".txt": "text/plain" };

http
  .createServer((req, res) => {
    const clean = decodeURIComponent(req.url.split("?")[0]);
    let file = path.join(root, clean);
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(root, "index.html");
    res.writeHead(200, { "content-type": types[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  })
  .listen(port, () => console.log(`serving ${root} on ${port}`));
