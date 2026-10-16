// 离线体检:不开浏览器,在 Node 里执行 BUD_UI_Studio.html 的页面脚本,拿工程文件跑一遍导出结构校验(只读,不写回工程)。
// 用法:node dev/offline_check.js [工程文件,默认 projects/RechargeRewardsOverview.budui.json] [--reconfigure] [--out 文件.unitypackage]
//   --reconfigure  先在内存里模拟点一次「✦ 一键配动效」,列出会被改掉的交互/动效设置,再校验导出
//   --out          把校验通过的交付包(.unitypackage)写到指定路径,等于不开浏览器直接导出
// 检查项:全部 GameObject 在 UI 层、prefab 内 fileID 引用都能解析、每页一个页面节点 + CanvasGroup 且只有主页激活、
//   View 的 pages[] 按顺序接好、跳转按钮调用了正确的 OpenPage/SwitchPage/OpenPopup 序号、三个 C# 文件大括号配对、事件/数据标识合法且不重复;
//   .unitypackage 结构(每个 GUID 目录含 asset/asset.meta/pathname、目录名与 meta 里的 guid 一致、落点都在模块目录下、prefab 引用的 GUID 全部在包内或是 UGUI/白名单字体)。
// 改了生成器(genPrefab / genViewCs / genMotionCs / genClickFeedbackCs)或自动配置逻辑后跑一遍。需要 Node 18+。
// 页面里的 DOM 用一个"什么都接受"的空桩代替,所以渲染类函数都是空跑;校验只看生成的 YAML 和 C#。
const fs = require("fs"), path = require("path"), vm = require("vm");
const ROOT = path.join(__dirname, "..");
const args = process.argv.slice(2);
const file = path.resolve(ROOT, args.find((a, i) => !a.startsWith("--") && args[i - 1] !== "--out") || "projects/RechargeRewardsOverview.budui.json");

const src = fs.readFileSync(path.join(ROOT, "BUD_UI_Studio.html"), "utf8").match(/<script>([\s\S]*?)<\/script>/)[1];
const stub = () => new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? () => "" : k === Symbol.iterator ? function* () {} : k === "length" ? 0 : k === "then" ? undefined : stub(),
  apply: () => stub(), construct: () => stub(), set: () => true });
const ctx = { document: stub(), addEventListener() {}, removeEventListener() {}, setTimeout: () => 0, clearTimeout() {}, console,
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, crypto: require("crypto").webcrypto, TextEncoder, Blob, atob, btoa, URL, Response, CompressionStream };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(src, ctx);
ctx.toast = m => { ctx.__toast = m; };
ctx.__project = JSON.parse(fs.readFileSync(file, "utf8"));
ctx.__reconfigure = args.includes("--reconfigure");

// 在页面脚本的上下文里执行(用到的 proj / walkAll / genPrefab 等都是页面里的全局)
function check() {
  proj = __project; ensurePages();
  let mx = 0; walkAll(n => { const v = parseInt(String(n.id).slice(1), 10); if (v > mx) mx = v; }); uid = mx + 1;
  const mod = sanitizeModule(proj.module) || "Module", res = { mod, pages: proj.pages.map(p => (p.kind === "popup" ? "🗨 " : "📄 ") + p.name), checks: [] };
  const ok = (cond, what) => res.checks.push((cond ? "✓ " : "✗ ") + what);
  if (__reconfigure) {
    const row = (p, n) => {
      const click = !!(n.clickable || n.type === "button"), tp = n.clickTargetPage && /^(open|switch)/.test(n.clickAction || "") ? pageById(n.clickTargetPage) : null;
      return { where: p.name.split("/")[0].trim() + " · " + n.name, 可点击: click, 关闭: !!n.isClose, 标识: click || n.dynamic ? n.key : "", 动态文本: !!n.dynamic,
        点击反馈: click ? n.clickMotion || "press" : "", 点击后: click ? n.clickAction || "event" : "", 目标节点: n.clickTarget ? (findNodeAll(n.clickTarget) || { name: "?" }).name : "",
        目标页面: tp ? tp.name : "", 动效: n.motion + "@" + (n.motionDelay || 0) };
    };
    const snap = () => { const out = []; proj.pages.forEach(p => walk(n => out.push(row(p, n)), p.nodes)); return out; };
    const before = snap(); autoConfigure(); const after = snap();
    res.changes = [];
    before.forEach((b, i) => { const a = after[i], ks = Object.keys(b).filter(k => k !== "where" && b[k] !== a[k]); if (ks.length) res.changes.push(b.where + ":" + ks.map(k => `${k} ${JSON.stringify(b[k])} → ${JSON.stringify(a[k])}`).join(";")); });
    res.reconfigureToast = __toast;
  }
  // 与导出 / 覆盖到 Unity 相同的生成入口
  const del = buildDelivery(mod), y = del.prefabYaml;
  const buttons = [], dynTexts = []; walkAll(n => { if (n.type === "button" || n.clickable) buttons.push(n); if (n.type === "text" && n.dynamic) dynTexts.push(n); });
  // 稳定 ID:再生成一次必须逐字节相同;把这份当"主工程里的旧 prefab"解析回 ID 再生成,也必须相同(覆盖时沿用旧 ID 的路径)
  const again = buildDelivery(mod);
  ok(again.prefabYaml === y && again.assets.every((a, i) => a.meta === del.assets[i].meta && a.path === del.assets[i].path), "再次导出 GUID / fileID 完全不变");
  const kinds = { [UGUI.image]: "img", [UGUI.text]: "txt", [UGUI.button]: "btn", [UGUI.scrollRect]: "sr", [UGUI.rectMask2D]: "mask", [UGUI.mask]: "rmask", [del.guids.view]: "view", [del.guids.motion]: "motion", [del.guids.press]: "press" };
  ok(buildDelivery(mod, { fidHints: null, existing: {} }).prefabYaml === y, "覆盖到 Unity 新建目标(主工程里还没有旧 prefab)与导出结果一致");
  const old = prefabIdHints(y, kinds), relabeled = buildDelivery(mod, { fidHints: old.hints });
  ok(relabeled.prefabYaml === y && !old.custom.length, `按旧 prefab 层级路径沿用 fileID:${Object.keys(old.hints).length} 个对象全部对上`);
  // 覆盖主工程面板时带面板外壳:根节点多一个 BasePanel 子类,字段 view 指向视图组件;其余内容与普通导出一致
  const asPanel = buildDelivery(mod, { asPanel: true }), py = asPanel.prefabYaml, panelCs = asPanel.assets.find(a => a.path.endsWith(`${mod}Panel.cs`));
  const viewFid = (py.match(new RegExp(`--- !u!114 &(\\d+)\\nMonoBehaviour:[\\s\\S]*?guid: ${asPanel.guids.view}`)) || [])[1];
  const pAnchors = new Set([...py.matchAll(/&(\d+)/g)].map(m => m[1]));
  ok(!!panelCs && py.includes(`guid: ${asPanel.guids.panel}`) && viewFid && py.includes(`  view: {fileID: ${viewFid}}`)
    && [...py.matchAll(/\{fileID: (\d+)\}/g)].every(m => m[1] === "0" || pAnchors.has(m[1])) && /: BasePanel<\w+Panel>/.test(panelCs.text),
    "覆盖成面板时:生成面板外壳脚本,根节点挂上并接好 view 引用,fileID 全部能解析");
  // 覆盖别的面板里的子视图(旧根节点挂业务脚本)时:根节点挂 Controller(普通 MonoBehaviour,不带 BasePanel),再覆盖时按 "|ctrl" 沿用原 ID
  const asSub = buildDelivery(mod, { asSubView: true }), sy = asSub.prefabYaml, ctrlCs = asSub.assets.find(a => a.path.endsWith(`${mod}Controller.cs`));
  const sViewFid = (sy.match(new RegExp(`--- !u!114 &(\\d+)\\nMonoBehaviour:[\\s\\S]*?guid: ${asSub.guids.view}`)) || [])[1];
  const sAnchors = new Set([...sy.matchAll(/&(\d+)/g)].map(m => m[1]));
  const sOld = prefabIdHints(sy, Object.assign({}, kinds, { [asSub.guids.ctrl]: "ctrl" }));
  ok(!!ctrlCs && !asSub.assets.some(a => a.path.endsWith(`${mod}Panel.cs`)) && !/:\s*BasePanel/.test(ctrlCs.text) && /: MonoBehaviour/.test(ctrlCs.text)
    && sy.includes(`guid: ${asSub.guids.ctrl}`) && sViewFid && sy.includes(`  view: {fileID: ${sViewFid}}`)
    && [...sy.matchAll(/\{fileID: (\d+)\}/g)].every(m => m[1] === "0" || sAnchors.has(m[1])) && !!sOld.hints["|ctrl"] && !sOld.custom.length
    && buildDelivery(mod, { asSubView: true, fidHints: sOld.hints }).prefabYaml === sy,
    "覆盖成子视图时:生成 Controller(不带 BasePanel),根节点挂上并接好 view 引用,再覆盖 ID 不变");
  const existing = Object.fromEntries(del.assets.map(a => [a.path.toUpperCase(), "0123456789abcdef0123456789abcdef"]));
  ok(buildDelivery(mod, { existing }).assets.every(a => a.meta.includes("guid: 0123456789abcdef0123456789abcdef")), "主工程已有的 .meta GUID 优先沿用(路径不区分大小写)");
  // 沿用旧资源:指定旧图时 prefab 引用旧 GUID、不多带切图;没指定时按旧 prefab 同路径沿用原来的 Sprite;原来的是本模块自己的切图就不算旧资源
  {
    let t = null; walkAll(n => { if (!t && n.type === "image" && n.spriteId) t = n; });
    if (t) {
      const saved = { keepOld: t.keepOld, oldSprite: t.oldSprite, oldSpriteGuid: t.oldSpriteGuid }, OLD = "fedcba9876543210fedcba9876543210";
      Object.assign(t, { keepOld: true, oldSprite: "Assets/Arts/UI/Old/old_icon.png", oldSpriteGuid: OLD });
      const kd = buildDelivery(mod), picked = kd.prefabYaml.includes(`{fileID: 21300000, guid: ${OLD}, type: 3}`) && kd.kept.length === 1 && !!kd.kept[0].ref && kd.spriteFiles <= del.spriteFiles;
      delete t.oldSprite; delete t.oldSpriteGuid;
      const h = prefabIdHints(y, kinds), auto = buildDelivery(mod, { fidHints: h.hints, oldSprites: h.sprites });
      const own = buildDelivery(mod, { fidHints: h.hints, oldSprites: h.sprites, ownGuids: new Set(del.assets.map(a => (a.meta.match(/^guid: ([0-9a-f]{32})/m) || [])[1])) });
      for (const [k, v] of Object.entries(saved)) if (v === undefined) delete t[k]; else t[k] = v;
      ok(picked && auto.prefabYaml === y && !!auto.kept[0].ref && own.prefabYaml === y && own.kept[0].how === "own",
        "沿用旧资源:指定旧图时引用旧 GUID;没指定时按旧 prefab 同路径沿用原图;原图是本模块切图时不算旧资源");
    }
  }
  const cs = { View: genViewCs(mod, buttons, dynTexts), Motion: genMotionCs(mod), ClickFeedback: genClickFeedbackCs(mod), Panel: genPanelCs(mod), Controller: genControllerCs(mod) };
  const anchors = new Set([...y.matchAll(/&(\d+)/g)].map(m => m[1]));
  const refs = [...y.matchAll(/\{fileID: (\d+)\}/g)].map(m => m[1]).filter(f => f !== "0");
  ok(!/m_Layer: (?!5)/.test(y), "所有 GameObject 都在 UI 层(m_Layer: 5)");
  ok(refs.every(f => anchors.has(f)), `prefab 里的 fileID 引用全部能解析(${refs.length} 处)`);
  const pageGOs = [...y.matchAll(/m_Name: "(?:Page|Popup)_[^"]*"\n[\s\S]*?m_IsActive: (\d)/g)];
  ok(pageGOs.length === proj.pages.length && pageGOs.filter(m => m[1] === "1").length === 1, `每页一个页面节点(${pageGOs.length}/${proj.pages.length}),只有主页初始激活`);
  ok((y.match(/^--- !u!225 &/gm) || []).length === proj.pages.length, "每个页面节点都带 CanvasGroup(切页淡入淡出用)");
  // View 的 pages[] 要按工程页面顺序指向对应的页面节点(OpenPage / OpenPopup 的参数就是这个序号)
  const goName = new Map([...y.matchAll(/--- !u!1 &(\d+)\nGameObject:[\s\S]*?m_Name: "((?:[^"\\]|\\.)*)"/g)].map(m => [m[1], m[2]]));
  const pf = ((y.match(/\n  pages:\n((?:  - \{fileID: \d+\}\n)+)/) || [])[1] || "").match(/\d+/g) || [];
  ok(pf.length === proj.pages.length && pf.every((f, i) => new RegExp(`^(Page|Popup)_${i}_`).test(goName.get(f) || "")), `View 的 pages[] 按顺序接好 ${pf.length}/${proj.pages.length} 个页面节点`);
  // 每个"打开页面/打开弹窗"按钮:目标存在、类型对得上、View 里的监听确实调用了对应序号
  const navOk = [], navBad = [];
  walkAll(n => {
    if (!(n.clickable || n.type === "button") || !/^(open|switch)(Page|Popup)$/.test(n.clickAction || "")) return;
    const idx = proj.pages.findIndex(p => p.id === n.clickTargetPage), tp = proj.pages[idx], want = {openPage: "OpenPage", switchPage: "SwitchPage", openPopup: "OpenPopup"}[n.clickAction];
    const line = cs.View.split("\n").find(l => l.includes(`${n.key}Button.onClick.AddListener`)) || "";
    if (idx <= 0) navBad.push(`${n.name}:目标页面不存在`);
    else if ((tp.kind === "popup") !== (want === "OpenPopup")) navBad.push(`${n.name}:${want} 指向了${tp.kind === "popup" ? "弹窗" : "页面"}「${tp.name}」`);
    else if (!line.includes(`${want}(${idx});`)) navBad.push(`${n.name}:View 里没有接上 ${want}(${idx})`);
    else navOk.push(n.key);
  });
  ok(!navBad.length, `跳转按钮接线正确(${navOk.length} 个)` + (navBad.length ? ";" + navBad.join("、") : ""));
  // 「切换到」(swap):View 里有对应接线;目标 GameObject 字段、按钮字段(= 自己所在的 GameObject)都能在 prefab 里按 fileID 解析。
  // 工程里没有 swap 节点时,临时把第一个可点击节点接到另一个节点上验证一次,验完还原
  {
    const hasSwap = () => { let f = false; walkAll(n => { if ((n.clickable || n.type === "button") && n.clickAction === "swap") f = true; }); return f; };
    let tmp = null;
    if (!hasSwap()) {
      let a = null, b = null; walkAll(n => { if (!a && (n.clickable || n.type === "button")) a = n; });
      if (a) walkAll(n => { if (!b && n.id !== a.id) b = n; });
      if (a && b) { tmp = { a, save: { clickAction: a.clickAction, clickTarget: a.clickTarget } }; a.clickAction = "swap"; a.clickTarget = b.id; }
    }
    const btns2 = [], dyn2 = []; walkAll(n => { if (n.type === "button" || n.clickable) btns2.push(n); if (n.type === "text" && n.dynamic) dyn2.push(n); });
    const y2 = tmp ? buildDelivery(mod).prefabYaml : y, view2 = tmp ? genViewCs(mod, btns2, dyn2) : cs.View;
    const goIds = new Set([...y2.matchAll(/^--- !u!1 &(\d+)$/gm)].map(m => m[1]));
    const monoGo = new Map([...y2.matchAll(/^--- !u!114 &(\d+)\nMonoBehaviour:\n(?:.*\n)*?  m_GameObject: \{fileID: (\d+)\}/gm)].map(m => [m[1], m[2]]));
    const good = [], bad = [];
    btns2.forEach(n => {
      if (n.clickAction !== "swap" || !n.clickTarget || !findNodeAll(n.clickTarget) || n.clickTarget === n.id) return;
      const tf = (y2.match(new RegExp(`\\n  ${n.key}Target: \\{fileID: (\\d+)\\}`)) || [])[1], bf = (y2.match(new RegExp(`\\n  ${n.key}Button: \\{fileID: (\\d+)\\}`)) || [])[1];
      const line = view2.split("\n").find(l => l.includes(`${n.key}Button.onClick.AddListener`)) || "";
      if (!tf || !goIds.has(tf)) bad.push(`${n.key}:目标 GameObject 字段没接上或解析不到`);
      else if (!bf || !goIds.has(monoGo.get(bf))) bad.push(`${n.key}:按钮自身的 GameObject 解析不到`);
      else if (!view2.includes(`private GameObject ${n.key}Target;`) || !line.includes(`${n.key}Target.SetActive(true)`) || !line.includes(`${n.key}Button.gameObject.SetActive(false)`) || !line.includes(`onAction.Invoke("${n.key}")`)) bad.push(`${n.key}:View 里的 swap 接线不完整`);
      else good.push(n.key);
    });
    if (tmp) Object.assign(tmp.a, tmp.save), tmp.save.clickAction === undefined && delete tmp.a.clickAction, tmp.save.clickTarget === undefined && delete tmp.a.clickTarget;
    ok(!bad.length && (good.length > 0 || !tmp), `「切换到」接线正确(${good.length} 个${tmp ? ",临时接线验证" : ""})` + (bad.length ? ";" + bad.join("、") : ""));
  }
  const balanced = s => { let a = 0; for (const c of s) { a += c === "{" ? 1 : c === "}" ? -1 : 0; if (a < 0) return false; } return a === 0; };
  Object.entries(cs).forEach(([k, s]) => ok(balanced(s), `${mod}${k}.cs 大括号配对`));
  const keys = new Set(), bad = [], dup = [];
  walkAll(n => { if (n.type === "button" || n.clickable || (n.type === "text" && n.dynamic)) { const k = (n.key || "").trim(); if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(k)) bad.push(n.name); else if (keys.has(k)) dup.push(k); keys.add(k); } });
  ok(!bad.length && !dup.length, `事件/数据标识合法且不重复(${keys.size} 个)` + (bad.length ? `;不合法:${bad.join("、")}` : "") + (dup.length ? `;重复:${dup.join("、")}` : ""));
  res.stats = `YAML 文档 ${(y.match(/^--- !u!/gm) || []).length} 个 · 可点击 ${buttons.length} · 动态文本 ${dynTexts.length} · 切图文件 ${del.spriteFiles}`;
  return JSON.stringify(res);
}

// 用工作台同一个 buildPackage 生成 .unitypackage,把字节和校验要用的信息交回 Node
async function pack() {
  const mod = sanitizeModule(proj.module) || "Module", { blob } = await buildPackage(mod);
  const external = [...Object.values(UGUI), ...Object.values(FONTS).map(f => f.guid)];
  return { mod, dirs: pkgDirs(mod), external, bytes: new Uint8Array(await blob.arrayBuffer()) };
}
// 解开 gzip + tar,按 GUID 目录归组
function readPackage(bytes) {
  const tar = require("zlib").gunzipSync(Buffer.from(bytes)), entries = {};
  for (let off = 0; off + 512 <= tar.length;) {
    const h = tar.subarray(off, off + 512); if (h.every(b => b === 0)) break;
    const name = h.subarray(0, 100).toString("utf8").replace(/\0.*$/s, ""), size = parseInt(h.subarray(124, 136).toString().replace(/\0.*$/s, "").trim() || "0", 8);
    const [dir, part] = name.split("/");
    if (part) (entries[dir] = entries[dir] || {})[part] = tar.subarray(off + 512, off + 512 + size);
    off += 512 + Math.ceil(size / 512) * 512;
  }
  return entries;
}

(async () => {
  const r = JSON.parse(vm.runInContext(`(${check})()`, ctx));
  const p = await vm.runInContext(`(${pack})()`, ctx);
  const entries = readPackage(p.bytes), guids = new Set(Object.keys(entries)), paths = [], issues = [];
  for (const [g, e] of Object.entries(entries)) {
    if (!e.asset || !e["asset.meta"] || !e.pathname) { issues.push(`${g} 缺少 asset/asset.meta/pathname`); continue; }
    const pn = e.pathname.toString("utf8"); paths.push(pn);
    if (!new RegExp(`^guid: ${g}$`, "m").test(e["asset.meta"].toString())) issues.push(`${pn}:meta 里的 guid 与目录名不一致`);
    if (!pn.startsWith(p.dirs.scripts + "/") && !pn.startsWith(p.dirs.art + "/")) issues.push(`${pn}:不在模块目录下`);
  }
  // Windows / Unity 的路径不区分大小写:Reward_Icon_2.png 与 reward_icon_2.png 会互相覆盖
  const seen = new Map(); paths.forEach(pn => { const k = pn.toLowerCase(); if (seen.has(k)) issues.push(`落点重复(不区分大小写):${seen.get(k)} / ${pn}`); else seen.set(k, pn); });
  const prefabEntry = Object.values(entries).find(e => e.pathname && e.pathname.toString().endsWith(".prefab"));
  const refs = prefabEntry ? [...new Set([...prefabEntry.asset.toString().matchAll(/guid: ([0-9a-f]{32})/g)].map(m => m[1]))] : [];
  const missing = refs.filter(g => !guids.has(g) && !p.external.includes(g));
  r.checks.push((issues.length ? "✗ " : "✓ ") + `.unitypackage 结构完整(${guids.size} 个资产,${(p.bytes.length / 1048576).toFixed(1)} MB)` + (issues.length ? ";" + issues.slice(0, 5).join("、") : ""));
  r.checks.push((prefabEntry && !missing.length ? "✓ " : "✗ ") + `prefab 引用的 ${refs.length} 个 GUID 全部在包内或是 UGUI/白名单字体` + (missing.length ? `;找不到:${missing.join("、")}` : prefabEntry ? "" : ";包里没有 prefab"));

  console.log(`工程:${path.relative(ROOT, file)} · 模块 ${r.mod} · ${r.pages.length} 页`);
  console.log("  " + r.pages.join("\n  "));
  if (r.changes) {
    console.log(`\n模拟「✦ 一键配动效」:${r.reconfigureToast}`);
    console.log(r.changes.length ? `会改动 ${r.changes.length} 处:\n  ` + r.changes.slice(0, 40).join("\n  ") + (r.changes.length > 40 ? `\n  …另有 ${r.changes.length - 40} 处` : "") : "现有配置与自动配置结果完全一致,点按钮不会改动任何设置");
  }
  console.log("\n导出校验:\n  " + r.checks.join("\n  ") + "\n  " + r.stats);
  console.log(`  落点:${p.dirs.scripts}/ · ${p.dirs.art}/`);
  const failed = r.checks.some(c => c.startsWith("✗")), outIdx = args.indexOf("--out");
  if (outIdx >= 0 && args[outIdx + 1]) {
    if (failed) console.log("\n有检查没通过,不写出交付包");
    else { const out = path.resolve(args[outIdx + 1]); fs.writeFileSync(out, p.bytes); console.log(`\n已写出:${out}`); }
  }
  process.exit(failed ? 1 : 0);
})();
