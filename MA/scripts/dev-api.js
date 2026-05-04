/**
 * Python FastAPI (backend) — proje kökündeki .venv ile çalışır (Windows / macOS / Linux).
 */
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const root = path.resolve(__dirname, "..");
const backendDir = path.join(root, "backend");
const isWin = process.platform === "win32";

const candidates = isWin
  ? [path.join(root, ".venv", "Scripts", "python.exe")]
  : [
      path.join(root, ".venv", "bin", "python3"),
      path.join(root, ".venv", "bin", "python"),
    ];

let python = null;
for (const p of candidates) {
  if (fs.existsSync(p)) {
    python = p;
    break;
  }
}

if (!python) {
  console.error(
    "[dev-api] .venv bulunamadı. Proje kökünde: python -m venv .venv && .venv\\Scripts\\pip install -r backend\\requirements.txt (Windows)",
  );
  process.exit(1);
}

const child = spawn(
  python,
  [
    "-m",
    "uvicorn",
    "app.main:app",
    "--reload",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
  ],
  {
    cwd: backendDir,
    stdio: "inherit",
    shell: false,
  },
);

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
