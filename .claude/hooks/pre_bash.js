// PreToolUse Hook: Bash 文件保护
// 拦截对保护区文件的写/删操作，关闭 Bash(*) 绕过 Edit/Write Hook 的路径
// 保护区清单从 protected-files.json 动态合并

const fs = require("fs");
const path = require("path");

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

  // ── 角色门禁：顾问角色禁止 Bash 操作 ── @claude-override-approved
  // [2026-05-29] 修改：豁免 .claude/task/ 目录，advisor 可操作协议文件 @claude-override-approved
  // @claude-override-approved
  const ROLE_FILE = path.join(__dirname, "..", "role.json"); // @claude-override-approved — Hook 读取 .claude/role.json，AI step 0 写入，Stop Hook 清除
  try {
    if (fs.existsSync(ROLE_FILE)) {
      const roleData = JSON.parse(fs.readFileSync(ROLE_FILE, "utf-8"));
      if (roleData.role === "advisor" || roleData.role === "consultant") {
        // @claude-override-approved — 白名单精确匹配：顾问仅可操作 5 个协议文件
        const taskPaths = extractPaths(command);
        const ADVISOR_WHITELIST = [
          ".claude/role.json",
          ".claude/next-session.md",
          ".claude/task/direction.md",
          ".claude/task/outcome.md",
          ".claude/task/recommendation.md"
        ];
        // @claude-override-approved — 空路径不自动放行，必须匹配只读命令白名单
        const ADVISOR_READONLY_CMDS = [
          "git status", "git log", "git diff", "git show", "git stash",
          "git branch", "git tag", "git remote", "git config",
          "ls ", "dir ", "cat ", "head ", "tail ", "wc ",
          "grep ", "find ", "which ", "type ", "where ",
          "echo ", "pwd", "whoami", "date", "env", "printenv",
          "node -v", "node --version", "python --version", "python -V",
          "python3 --version", "python3 -V", "npm -v", "npm --version",
          "tsc --version", "tsc -v", "tsc --noEmit",
        ];
        const cmdTrimmed = command.trim();
        const isEmptyReadOnly = taskPaths.length === 0
          && ADVISOR_READONLY_CMDS.some(function(p) { return cmdTrimmed.startsWith(p); });
        const allTaskFiles = isEmptyReadOnly || taskPaths.every(function(p) {
          const np = p.replace(/\\/g, "/");
          return ADVISOR_WHITELIST.some(function(f) { return np.endsWith(f); });
        });
        if (!allTaskFiles) {
          console.error(
            "\n============================================" +
            "\n[角色门禁] 当前为顾问角色，禁止 Bash 操作！" +
            "\n  请切换到执行窗口（输入 \"执行\"）。" +
            "\n============================================"
          );
          process.exit(2);
        }
      }
    }
  } catch (_) {}

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

  // ── 项目自定义逻辑在此后扩展 ──
  // 示例：网络请求限流、特定命令拦截等
  // 注意：非文件保护逻辑请在确认不是写/删操作后添加
  // if (!isWriteOrDelete(command)) { ... }

  process.exit(0);
});
