// PreToolUse Hook: Bash 文件保护 + 分时限流 v1
// 文件保护：拦截对保护区文件的写/删操作，关闭 Bash(*) 绕过 Edit/Write Hook 的路径
// 分时限流：AKShare/东方财富 API 限流 — 滑动窗口 + 会话预算 + 强制冷却
// 保护区清单从 protected-files.json 动态合并
// 状态文件: .claude/.gate/rate_limit.json

const fs = require("fs");
const path = require("path");

const STATE_FILE = path.join(__dirname, "..", ".gate", "rate_limit.json");
const MIN_INTERVAL_MS = 3000;
const EASTMONEY_INTERVAL_MS = 5000;
const WINDOW_SEC = 60;
const COOLDOWN_60S = 60000;
const COOLDOWN_120S = 120000;
const BUDGET_WARN = 240;
const BUDGET_MAX = 300;
const MAX_HISTORY = 200;

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, "utf-8"));
  } catch {
    return { timestamps: [], cooldowns: 0, blocked: false };
  }
}

function saveState(state) {
  const dir = path.dirname(STATE_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(STATE_FILE, JSON.stringify(state));
}

// ── 判断命令是否包含写/删操作 ──
function isWriteOrDelete(cmd) {
  if (/>[>]?/.test(cmd)) return true;       // > file, >> file
  if (/\brm\s/.test(cmd)) return true;       // rm file
  if (/\btee\s/.test(cmd)) return true;      // tee file
  if (/\bdd\s+.*of=/i.test(cmd)) return true; // dd of=file
  if (/\btruncate\s/.test(cmd)) return true;  // truncate file
  if (/\bcp\s/.test(cmd)) return true;       // cp src dst
  if (/\bmv\s/.test(cmd)) return true;       // mv src dst
  return false;
}

// 从命令中提取所有可能的文件路径
function extractPaths(cmd) {
  const paths = [];
  const qpat = /['"]([^'"]+)['"]/g;
  let m;
  while ((m = qpat.exec(cmd)) !== null) {
    const p = m[1].replace(/\\/g, "/");
    if (p.includes(".") || p.includes("/")) paths.push(p);
  }
  const redirPat = />>?\s*([^\s|;&]+)/g;
  while ((m = redirPat.exec(cmd)) !== null) {
    const p = m[1].replace(/\\/g, "/");
    if (p && !p.match(/^\/dev\//)) paths.push(p);
  }
  const rmPat = /\brm\s+(?:-[a-zA-Z]+\s+)*([^\s|;&]+)/g;
  while ((m = rmPat.exec(cmd)) !== null) {
    const p = m[1].replace(/\\/g, "/");
    if (p) paths.push(p);
  }
  const destPat = /\b(?:tee|cp|mv)\b\s+.*?([^\s|;&]+)\s*$/;
  let dm = destPat.exec(cmd);
  if (dm) {
    const p = dm[1].replace(/\\/g, "/");
    if (p && !p.startsWith("-") && (p.includes(".") || p.includes("/"))) {
      paths.push(p);
    }
  }
  return paths;
}

function isProtected(p, allFiles, allDirs) {
  const base = path.basename(p);
  if (allFiles.some((f) => base === f)) return true;
  if (allDirs.some((d) => p.includes(d))) return true;
  return false;
}

let input = "";
process.stdin.setEncoding("utf-8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  let payload;
  try { payload = JSON.parse(input); } catch { process.exit(0); }

  const toolInput = payload.tool_input || {};
  const command = toolInput.command || "";

  // ── 文件保护（所有 Bash 命令优先检查）──
  if (isWriteOrDelete(command)) {
    const JSON_PATH = path.join(process.cwd(), "protected-files.json");
    let allFiles = [];
    let allDirs = [];
    try {
      if (fs.existsSync(JSON_PATH)) {
        const raw = JSON.parse(fs.readFileSync(JSON_PATH, "utf-8"));
        allFiles = raw.protected_files || [];
        allDirs = raw.protected_dirs || [];
      }
    } catch (_) {}

    // 硬保护：清单自身 + Hook 脚本 + 门禁状态
    allFiles.push("protected-files.json", "protected-contracts.json", "check_values.py");
    allDirs.push(".claude/hooks/", ".claude/.gate/");

    const paths = extractPaths(command);
    const hits = paths.filter((p) => isProtected(p, allFiles, allDirs));

    if (hits.length > 0) {
      console.error(
        "\n============================================" +
        "\n[Bash 文件保护] 禁止通过 Bash 修改保护区文件！" +
        "\n  目标: " + hits.join(", ") +
        "\n  -------------------------------------------" +
        "\n  Bash 写文件绕过所有 Edit/Write 安全 Hook。" +
        "\n  请使用 Edit/Write 工具并遵循 audit 审核协议。" +
        "\n============================================"
      );
      process.exit(2);
    }
  }

  // ── 分时限流：仅拦截网络请求命令 ──
  const isNetworkCmd = /requests\.(get|post)|urllib|httpx|curl|wget|akshare|fund_etf|eastmoney|fetch_etf/i.test(command);
  const isEastMoneyCmd = /eastmoney|fund_etf|push2his/i.test(command);

  if (!isNetworkCmd) {
    process.exit(0);
  }

  const state = loadState();
  const now = Date.now();

  // ── 强制冷却检查 ──
  if (state.coolUntil && now < state.coolUntil) {
    const remain = Math.ceil((state.coolUntil - now) / 1000);
    console.error(
      "\n============================================" +
      "\n[Bash 限流冷却] 因频繁请求触发强制冷却。" +
      "\n  剩余 " + remain + "s，已触发 " + (state.cooldowns || 0) + " 次冷却。" +
      "\n  东方财富 API 建议间隔 ≥5s，冷却期禁止所有网络命令。" +
      "\n============================================"
    );
    process.exit(2);
  }

  // ── 会话预算 ──
  const totalRequests = state.timestamps.length;
  if (totalRequests >= BUDGET_MAX) {
    console.error(
      "\n============================================" +
      "\n[Bash 预算耗尽] 本会话已达 " + BUDGET_MAX + " 次网络请求上限。" +
      "\n  请新开会话继续。" +
      "\n============================================"
    );
    state.blocked = true;
    saveState(state);
    process.exit(2);
  }

  // ── 滑动窗口检查（过去 60s 内的请求数）──
  const cutoff = now - WINDOW_SEC * 1000;
  const recentTimestamps = (state.timestamps || []).filter(function (t) { return t > cutoff; });
  const recentCount = recentTimestamps.length;

  if (recentCount >= 6) {
    state.coolUntil = now + COOLDOWN_120S;
    state.cooldowns = (state.cooldowns || 0) + 1;
    saveState(state);
    console.error(
      "\n============================================" +
      "\n[Bash 限流阻断] 过去 " + WINDOW_SEC + "s 内 " + recentCount + " 次网络请求！" +
      "\n  触发 120s 强制冷却。" +
      "\n  冷却中所有 Bash 网络命令将被拦截。" +
      "\n============================================"
    );
    process.exit(2);
  }

  if (recentCount >= 3) {
    state.coolUntil = now + COOLDOWN_60S;
    state.cooldowns = (state.cooldowns || 0) + 1;
    saveState(state);
    console.error(
      "\n============================================" +
      "\n[Bash 限流阻断] 过去 " + WINDOW_SEC + "s 内 " + recentCount + " 次网络请求。" +
      "\n  触发 60s 强制冷却（东方财富 API 限流严格）。" +
      "\n============================================"
    );
    process.exit(2);
  }

  // ── 最小间隔检查 ──
  const requiredInterval = isEastMoneyCmd ? EASTMONEY_INTERVAL_MS : MIN_INTERVAL_MS;
  if (state.timestamps.length > 0) {
    const last = state.timestamps[state.timestamps.length - 1];
    const elapsed = now - last;
    if (elapsed < requiredInterval) {
      const waitSec = ((requiredInterval - elapsed) / 1000).toFixed(1);
      console.error(
        "\n============================================" +
        "\n[Bash 分时限流] 网络请求过于频繁！" +
        "\n  间隔 " + (elapsed / 1000).toFixed(1) + "s，要求 ≥" + (requiredInterval / 1000).toFixed(0) + "s。" +
        "\n  请等待 " + waitSec + "s。" +
        "\n  过去 " + WINDOW_SEC + "s 内已 " + recentCount + " 次请求" +
        "\n  会话累计 " + totalRequests + "/" + BUDGET_MAX + " 次" +
        "\n============================================"
      );
      process.exit(2);
    }
  }

  // ── 预算预警 ──
  if (totalRequests >= BUDGET_WARN) {
    console.error(
      "\n[预算预警] 本会话网络请求已用 " + totalRequests + "/" + BUDGET_MAX +
      "（" + Math.round(totalRequests / BUDGET_MAX * 100) + "%），接近上限。"
    );
  }

  state.timestamps.push(now);
  if (state.timestamps.length > MAX_HISTORY) state.timestamps = state.timestamps.slice(-MAX_HISTORY);
  saveState(state);
  process.exit(0);
});
