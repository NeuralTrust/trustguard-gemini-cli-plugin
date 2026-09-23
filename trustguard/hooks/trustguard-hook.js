#!/usr/bin/env node
// Bootstrap for the TrustGuard Gemini CLI extension.
//
// Gemini CLI runs hook commands through bash on macOS/Linux and PowerShell on
// Windows, so the one launcher both can run is Node, which Gemini CLI itself
// needs. This script executes trustguard-gemini-cli from the PATH when present
// (manual/MDM installs win); otherwise it installs the pinned release for this
// OS/arch into ~/.trustguard/bin in the background, verifying its SHA-256
// against the table below, and evaluates from the next event on. Every
// bootstrap failure fails open (Gemini CLI must never brick) with a warning on
// stderr: an empty JSON object on stdout and exit code 0 is "allow".
//
// The VERSION and SHA256 table are updated per release.
'use strict';

const VERSION = '0.1.0';

// Per-platform SHA-256 of the release binaries (filled per release).
const SHA256 = {
  darwin_amd64: '',
  darwin_arm64: '',
  linux_amd64: '',
  linux_arm64: '',
  windows_amd64: '',
  windows_arm64: '',
};

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const https = require('node:https');
const { spawnSync, spawn } = require('node:child_process');

const NAME = 'trustguard-gemini-cli';
const EXT = process.platform === 'win32' ? '.exe' : '';
const BASE_URL =
  process.env.TRUSTGUARD_GEMINI_CLI_DOWNLOAD_BASE ||
  'https://github.com/NeuralTrust/trustguard-gemini-cli-plugin/releases/download';
const BIN_DIR =
  process.env.TRUSTGUARD_GEMINI_CLI_BIN_DIR || path.join(os.homedir(), '.trustguard', 'bin');

function failOpen(message) {
  process.stderr.write(`${NAME} bootstrap: ${message} — allowing without evaluation\n`);
  process.stdout.write('{}\n');
  process.exit(0);
}

function readStdin() {
  try {
    return fs.readFileSync(0);
  } catch {
    return Buffer.alloc(0);
  }
}

function runBinary(bin) {
  const result = spawnSync(bin, ['hook'], {
    input: readStdin(),
    stdio: ['pipe', 'pipe', 'inherit'],
    maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error) {
    failOpen(`cannot run ${bin}: ${result.error.message}`);
  }
  if (result.stdout && result.stdout.length > 0) {
    process.stdout.write(result.stdout);
  }
  // The binary answers with JSON on exit 0 and exits 1 on its own errors,
  // which Gemini CLI reads as a non-blocking warning.
  process.exit(result.status === null ? 1 : result.status);
}

function onPath(name) {
  const dirs = (process.env.PATH || '').split(path.delimiter).filter(Boolean);
  const names = process.platform === 'win32' ? [name + '.exe', name + '.cmd', name + '.bat', name] : [name];
  for (const dir of dirs) {
    for (const candidate of names) {
      const full = path.join(dir, candidate);
      try {
        fs.accessSync(full, fs.constants.X_OK);
        if (fs.statSync(full).isFile()) return full;
      } catch {
        // keep looking
      }
    }
  }
  return null;
}

function platform() {
  const osName = { darwin: 'darwin', linux: 'linux', win32: 'windows' }[process.platform];
  const arch = { x64: 'amd64', arm64: 'arm64' }[process.arch];
  return { osName, arch };
}

function download(url, target, wantSha, redirects = 0) {
  return new Promise((resolve, reject) => {
    if (redirects > 5) return reject(new Error('too many redirects'));
    const req = https.get(url, { headers: { 'User-Agent': `${NAME}/${VERSION}` } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return resolve(download(new URL(res.headers.location, url).toString(), target, wantSha, redirects + 1));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      const tmp = `${target}.download.${process.pid}`;
      const hash = crypto.createHash('sha256');
      const file = fs.createWriteStream(tmp, { mode: 0o755 });
      res.on('data', (chunk) => hash.update(chunk));
      res.pipe(file);
      file.on('finish', () => {
        file.close(() => {
          const got = hash.digest('hex');
          if (got !== wantSha) {
            fs.rmSync(tmp, { force: true });
            return reject(new Error(`checksum mismatch (got ${got}, want ${wantSha})`));
          }
          try {
            fs.renameSync(tmp, target);
            resolve();
          } catch (err) {
            fs.rmSync(tmp, { force: true });
            reject(err);
          }
        });
      });
      file.on('error', (err) => {
        fs.rmSync(tmp, { force: true });
        reject(err);
      });
    });
    req.setTimeout(300_000, () => req.destroy(new Error('download timed out')));
    req.on('error', reject);
  });
}

async function installOnly() {
  const { osName, arch } = platform();
  const wantSha = SHA256[`${osName}_${arch}`];
  const target = path.join(BIN_DIR, `${NAME}-${VERSION}${EXT}`);
  const url = `${BASE_URL}/v${VERSION}/${NAME}_${VERSION}_${osName}_${arch}${EXT}`;
  const lock = path.join(BIN_DIR, `install-gemini-cli-${VERSION}.lock`);
  try {
    fs.mkdirSync(BIN_DIR, { recursive: true });
    await download(url, target, wantSha);
  } catch (err) {
    process.stderr.write(`${NAME} bootstrap: install failed: ${err.message}\n`);
  } finally {
    fs.rmSync(lock, { recursive: true, force: true });
  }
}

function main() {
  if (process.argv.includes('--install-only')) {
    return installOnly();
  }

  const fromPath = onPath(NAME);
  if (fromPath) runBinary(fromPath);

  // Local and MDM installs use the stable, unversioned filename.
  const localBin = path.join(BIN_DIR, `${NAME}${EXT}`);
  if (fs.existsSync(localBin)) runBinary(localBin);

  const versioned = path.join(BIN_DIR, `${NAME}-${VERSION}${EXT}`);
  if (fs.existsSync(versioned)) runBinary(versioned);

  const { osName, arch } = platform();
  if (!osName) failOpen(`unsupported OS ${process.platform}; install ${NAME} manually`);
  if (!arch) failOpen(`unsupported arch ${process.arch}; install ${NAME} manually`);
  if (!SHA256[`${osName}_${arch}`]) {
    failOpen(`no pinned checksum for ${osName}/${arch} (release ${VERSION} not published yet?); install ${NAME} manually`);
  }

  try {
    fs.mkdirSync(BIN_DIR, { recursive: true });
  } catch (err) {
    failOpen(`cannot create ${BIN_DIR}: ${err.message}`);
  }

  const lock = path.join(BIN_DIR, `install-gemini-cli-${VERSION}.lock`);
  try {
    const stat = fs.statSync(lock);
    if (Date.now() - stat.mtimeMs > 10 * 60 * 1000) fs.rmSync(lock, { recursive: true, force: true });
  } catch {
    // no lock
  }
  let locked = false;
  try {
    fs.mkdirSync(lock);
    locked = true;
  } catch {
    // another event is already installing
  }
  if (locked) {
    const child = spawn(process.execPath, [__filename, '--install-only'], {
      detached: true,
      stdio: 'ignore',
      env: process.env,
    });
    child.unref();
  }
  failOpen(`${NAME} ${VERSION} not installed yet; fetching it in the background`);
}

try {
  const result = main();
  if (result && typeof result.catch === 'function') {
    result.catch((err) => failOpen(`unexpected error: ${err.message}`));
  }
} catch (err) {
  failOpen(`unexpected error: ${err && err.message ? err.message : String(err)}`);
}
