// PreToolUse Hook: 三层拦截(文件级) + 测试门禁 + 新会话 Git 门禁 + audit 标记验证
// v11+ 升级：令牌 + audit 标记双重验证，关闭跳过 audit 直接令牌绕过
// 保护区清单从 protected-files.json 动态合并

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

let input = "";
process.stdin.setEncoding("utf-8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  let payload;
  try { payload = JSON.parse(input); } catch { process.exit(0); }

  const sessionId = payload.session_id || "unknown";
  const toolInput = payload.tool_input || {};
  const newStr = (toolInput.new_string || toolInput.content || "");
  const filePath = (toolInput.file_path || "").replace(/\\/g, "/");

  // ── 新会话 Git 门禁（同一 session 只检查一次）──
  const gateDir = path.join(__dirname, "..", ".gate");
  const gateFile = path.join(gateDir, sessionId);

  if (!fs.existsSync(gateFile)) {
    try {
      const status = execSync("git status --porcelain", {
        encoding: "utf-8", cwd: process.cwd(),
      }).trim();
      const untracked = status.split("\n")
        .filter((l) => l.startsWith("??"))
        .map((l) => l.slice(3).trim());
      const dangerous = untracked.filter((f) => !filePath.includes(f));

      if (dangerous.length > 0) {
        console.error(
          "\n============================================" +
          "\n[Git 门禁] 检测到未跟踪文件！新会话禁止编辑。" +
          "\n  请先 git add + git commit 或清理后重试。" +
          "\n--------------------------------------------" +
          dangerous.map((f) => "\n  ?? " + f).join("") +
          "\n============================================"
        );
        process.exit(2);
      }
      fs.mkdirSync(gateDir, { recursive: true });
      fs.writeFileSync(gateFile, new Date().toISOString());
    } catch (e) {
      if (e.status === 2) process.exit(2);
    }
  }

  // 从 protected-files.json 读取保护区清单
  let PROTECTED = [];
  let PROTECTED_DIRS = [];
  try {
    const raw = JSON.parse(fs.readFileSync(
      path.join(process.cwd(), "protected-files.json"), "utf-8"));
    PROTECTED = raw.protected_files || [];
    PROTECTED_DIRS = raw.protected_dirs || [];
  } catch (_) {}
  const fileName = path.basename(filePath);
  const isProtected = PROTECTED.some((p) => fileName === p)
    || PROTECTED_DIRS.some((d) => filePath.includes(d));

  if (isProtected) {
    const hasToken = newStr.includes("@claude-override-approved");
    if (!hasToken) {
      console.error(
        "\n============================================" +
        "\n[架构防火墙] 致命拦截：禁止直接修改核心保护区！" +
        "\n  目标文件: " + filePath +
        "\n  -------------------------------------------" +
        "\n  1. 立即停止当前修改尝试。" +
        "\n  2. 向人类用户汇报修改意图。" +
        "\n  3. 等待人类明确回复批准。" +
        "\n  4. 获得批准后在内容中加入 @claude-override-approved。" +
        "\n  5. 确保已通过 CLI audit 审核（需 audit 标记文件）。" +
        "\n============================================"
      );
      process.exit(2);
    }

    // 令牌存在 → 验证 audit 标记（防止跳过 audit 流程直接用令牌）
    const safeName = filePath.replace(/[\\/:*?"<>|]/g, "_");
    const markerFile = path.join(gateDir, "audit_ok_" + safeName);
    const markerExists = fs.existsSync(markerFile);
    if (!markerExists) {
      console.error(
        "\n============================================" +
        "\n[架构防火墙] Audit 标记缺失！" +
        "\n  目标文件: " + filePath +
        "\n  -------------------------------------------" +
        "\n  令牌有效，但未找到 audit 审核通过标记。" +
        "\n  请先运行 CLI audit 命令完成异构盲审，" +
        "\n  人工审核通过后由 audit 命令创建标记文件。" +
        "\n  标记路径: " + markerFile +
        "\n============================================"
      );
      process.exit(2);
    }

    // 检查标记有效期（30 分钟）
    try {
      const markerStat = fs.statSync(markerFile);
      const markerAge = (Date.now() - markerStat.mtimeMs) / 1000;
      if (markerAge > 1800) {
        fs.unlinkSync(markerFile);
        console.error(
          "\n============================================" +
          "\n[架构防火墙] Audit 标记已过期（>30min）！" +
          "\n  目标文件: " + filePath +
          "\n  请重新运行 CLI audit 命令。原标记已清除。" +
          "\n============================================"
        );
        process.exit(2);
      }
      // 验证标记内容匹配（防跨文件重用）
      const markerContent = fs.readFileSync(markerFile, "utf-8").trim();
      const expected = filePath.replace(/\\/g, "/");
      if (markerContent !== expected && markerContent !== safeName) {
        console.error(
          "\n============================================" +
          "\n[架构防火墙] Audit 标记不匹配！" +
          "\n  当前文件: " + filePath +
          "\n  标记对应: " + markerContent +
          "\n  禁止跨文件重用 audit 标记。" +
          "\n============================================"
        );
        process.exit(2);
      }
    } catch (e) {
      console.error("[架构防火墙] 读取 audit 标记失败: " + e.message);
      process.exit(2);
    }

    // 标记验证通过，删除标记（一次性使用）
    try { fs.unlinkSync(markerFile); } catch (_) {}
  }

  // ── 测试门禁：改 .py/.ts 必须已有 tests/test_*.py ──
  // 测试文件自身豁免；新建文件（Write 工具）豁免；.claude/ 目录豁免
  const ext = path.extname(fileName);
  if ((ext === ".py" || ext === ".ts" || ext === ".tsx")
      && !filePath.includes("/tests/")
      && !filePath.includes("/test/")
      && !filePath.includes(".claude/")
      && !fileName.endsWith(".d.ts")
      && !fileName.startsWith("test_")) {

    const base = path.basename(fileName, ext);
    const testCandidates = [
      `tests/test_${base}.py`,
      `tests/test_${base}.ts`,
      `tests/test_${base}.tsx`,
      `${path.dirname(filePath)}/__tests__/${base}.test.${ext.slice(1)}`,
    ];

    const hasTest = testCandidates.some((tc) => {
      try {
        return fs.existsSync(path.resolve(process.cwd(), tc));
      } catch { return false; }
    });

    if (!hasTest) {
      console.error(
        "\n============================================" +
        "\n[测试门禁] 阻断 — 请先执行 Test(红灯)！" +
        "\n  目标文件: " + filePath +
        "\n  缺少测试: tests/test_" + base + ".py" +
        "\n  -------------------------------------------" +
        "\n  1. 列出测试场景 → 用户审" +
        "\n  2. 写测试代码 → 跑 → 必须全红" +
        "\n  3. 再回来 Edit 此文件" +
        "\n  参考: .claude/rules/11-testing.md" +
        "\n============================================"
      );
      process.exit(2);
    }
  }

  // ── 跨 hook 联动：读取 Bash 分时限流状态，高频时告警 ──
  const RATE_FILE = path.join(__dirname, "..", ".gate", "rate_limit.json");
  try {
    if (fs.existsSync(RATE_FILE)) {
      const rate = JSON.parse(fs.readFileSync(RATE_FILE, "utf-8"));
      if (rate.coolUntil && Date.now() < rate.coolUntil) {
        const remain = Math.ceil((rate.coolUntil - Date.now()) / 1000);
        console.error(
          "\n[分时告警] Bash 正处于 " + remain + "s 强制冷却中（已触发 " +
          (rate.cooldowns || 0) + " 次）。修改可能基于过时数据，请谨慎。"
        );
      }
      const recent = (rate.timestamps || []).filter(function(t){return t > Date.now()-60000;}).length;
      if (recent >= 5) {
        console.error(
          "\n[分时告警] 过去 60s 内 " + recent + " 次网络请求。" +
          " 建议等待冷却后再修改源文件。"
        );
      }
    }
  } catch (_) {}

  process.exit(0);
});
