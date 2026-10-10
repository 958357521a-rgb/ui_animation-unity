// Figma 插件「从工作台导入」回归测试:在 Node 里模拟 Figma 插件 API,把真实工程按插件界面的消息顺序导一遍
// 用法:node dev/plugin_import_selftest.js [工程文件...](默认 projects/Sign.budui.json projects/GemPack.budui.json)
// 检查:每个工作台节点都建出了图层(按钮多一个 Label)、每个界面一张 2436×1125 画框、图片填充都指向已创建的图片、
//   文字内容 / 字号 / 对齐照搬、默认隐藏的节点不可见、pluginData 带上标识、同名分区重导会替换、只用了 ES2017 语法。
const fs = require("fs"), path = require("path"), vm = require("vm");
const ROOT = path.join(__dirname, "..");
const files = process.argv.slice(2).length ? process.argv.slice(2) : ["projects/Sign.budui.json", "projects/GemPack.budui.json"];
const code = fs.readFileSync(path.join(ROOT, "figma-plugin/code.js"), "utf8");
const checks = [], ok = (c, what) => checks.push((c ? "✓ " : "✗ ") + what);
ok(!/\?\.|\?\?|\.\.\.[A-Za-z_$[{(]/.test(code.replace(/\/\/.*$/gm, "")), "插件主线程只用 ES2017 语法(没有 ?. ?? 展开)");

let made = 0;
function mk(type) {
  made++;
  const n = { type, children: [], x: 0, y: 0, width: 100, height: 100, visible: true, opacity: 1, fills: [], name: "", parent: null, _pd: {},
    appendChild(c) { if (c.parent) c.parent.children.splice(c.parent.children.indexOf(c), 1); c.parent = n; n.children.push(c); },
    remove() { if (n.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1); n.parent = null; },
    resize(w, h) { if (!(w > 0 && h > 0)) throw new Error(`resize(${w}, ${h})`); n.width = w; n.height = h; },
    resizeWithoutConstraints(w, h) { n.resize(w, h); },
    setPluginData(k, v) { n._pd[k] = v; }, getPluginData(k) { return n._pd[k] || ""; } };
  if (type === "TEXT") {
    let font = null;
    Object.defineProperty(n, "fontName", { get: () => font, set: v => { if (!loaded.has(v.family + "|" + v.style)) throw new Error("字体没加载:" + v.family + " " + v.style); font = v; } });
    Object.defineProperty(n, "characters", { get: () => n._chars, set: v => { if (!font) throw new Error("先设字体再写文字"); n._chars = v; } });
  }
  return n;
}
const loaded = new Set(), images = new Set(), messages = [];
const page0 = mk("PAGE"); page0.name = "Page 1";
const figma = {
  command: "import", root: { name: "lijixiantest", children: [page0] },
  showUI() {}, closePlugin() {}, on() {},
  ui: { postMessage: m => messages.push(m), onmessage: null },
  createPage() { const p = mk("PAGE"); figma.root.children.push(p); return p; },
  setCurrentPageAsync: async p => { figma.currentPage = p; },
  createFrame: () => mk("FRAME"), createRectangle: () => mk("RECTANGLE"), createText: () => mk("TEXT"), createSection: () => mk("SECTION"),
  createImage(bytes) { if (!bytes || !bytes.length) throw new Error("空图片"); const h = "h" + images.size; images.add(h); return { hash: h }; },
  base64Decode: s => Buffer.from(s, "base64"),
  listAvailableFontsAsync: async () => [["Source Han Sans CN", "Heavy"], ["Source Han Sans CN", "Medium"], ["Source Han Sans CN", "Regular"], ["Montserrat", "Bold"], ["Montserrat", "Black"], ["Montserrat", "Medium"], ["Inter", "Regular"]]
    .map(([family, style]) => ({ fontName: { family, style } })),
  loadFontAsync: async f => { loaded.add(f.family + "|" + f.style); },
  viewport: { scrollAndZoomIntoView() {} }, currentPage: page0
};
vm.runInNewContext(code, { figma, __html__: "", __uiFiles__: { main: "", import: "" }, console, Promise, Math, JSON, Date, String, Object, Array, Error, RegExp, Number, parseInt });

let seq = 0;
function send(msg) {
  msg.id = ++seq; const before = messages.length; figma.ui.onmessage(msg);
  return new Promise((res, rej) => { const t = setInterval(() => {
    const m = messages.slice(before).find(x => x.id === msg.id && (x.type === "ack" || x.type === "error"));
    if (m) { clearInterval(t); m.type === "ack" ? res() : rej(new Error(m.text)); } }, 1); });
}
const walk = (ns, fn) => ns.forEach(n => { fn(n); walk(n.children || [], fn); });

(async () => {
  const projs = files.map(f => JSON.parse(fs.readFileSync(path.resolve(ROOT, f), "utf8")));
  const title = p => (p.taskName || p.module) + (p.module && p.taskName ? ` · ${p.module}` : "");
  // 和插件界面一样:dataUrl → base64(测试里不做 4096 缩小)
  const payload = p => ({ title: title(p), module: p.module, pages: p.pages,
    assets: Object.fromEntries(Object.entries(p.assets).map(([k, a]) => [k, a.dataUrl.split(",")[1]])) });
  for (let round = 1; round <= 2; round++) {   // 导两遍:第二遍同名分区应替换而不是叠加
    await send({ type: "begin", page: "lijixiantest" });
    for (const p of projs) await send({ type: "project", project: payload(p) });
    await send({ type: "images", title: "参考图", images: [{ name: "模板", b64: Buffer.from("x").toString("base64"), w: 800, h: 400 }] });
    await send({ type: "end" });
  }
  const page = figma.root.children.find(p => p.name === "lijixiantest");
  ok(!!page, "新建了页面 lijixiantest");
  const secs = page.children;
  ok(secs.length === projs.length + 1 && secs.every(s => s.type === "SECTION"), `重导两遍后仍是 ${projs.length + 1} 个分区(同名替换):${secs.map(s => s.name).join(" / ")}`);
  for (const p of projs) {
    const sec = secs.find(s => s.name === title(p));
    if (!sec) { ok(false, `找不到分区「${title(p)}」`); continue; }
    let wb = 0, labels = 0, hidden = 0; p.pages.forEach(pg => walk(pg.nodes, n => { wb++; if (n.type === "button" && n.label) labels++; if (n.hiddenByDefault) hidden++; }));
    let fg = 0, fgHidden = 0, badFill = 0, tagged = 0, texts = [], wbTexts = [];
    sec.children.forEach(f => walk(f.children, n => { fg++; if (!n.visible) fgHidden++; if (n._pd.budui) tagged++;
      (n.fills || []).forEach(fl => { if (fl.type === "IMAGE" && !images.has(fl.imageHash)) badFill++; });
      if (n.type === "TEXT" && n.name !== "Label") texts.push([n.characters, n.fontSize, n.textAlignHorizontal, n.textAlignVertical].join("|")); }));
    p.pages.forEach(pg => walk(pg.nodes, n => { if (n.type === "text") wbTexts.push([n.text, n.fontSize, ["LEFT", "CENTER", "RIGHT"][n.alignH || 0], ["TOP", "CENTER", "BOTTOM"][n.alignV || 0]].join("|")); }));
    ok(sec.children.length === p.pages.length && sec.children.every(f => f.type === "FRAME" && f.width === 2436 && f.height === 1125), `「${p.module}」每个界面一张 2436×1125 画框(${sec.children.length}/${p.pages.length})`);
    ok(fg === wb + labels, `「${p.module}」图层数 = 工作台节点数 + 按钮文字(${fg} = ${wb} + ${labels})`);
    ok(!badFill, `「${p.module}」图片填充都指向已创建的图片`);
    ok(JSON.stringify(texts) === JSON.stringify(wbTexts), `「${p.module}」${texts.length} 段文字内容 / 字号 / 对齐照搬`);
    ok(fgHidden === hidden && tagged === wb + 0, `「${p.module}」默认隐藏 ${hidden} 个、${tagged} 个图层带工作台标识`);
  }
  const done = messages.filter(m => m.type === "done").pop();
  ok(done && !done.fallbacks.length, "字体齐全时没有替补:" + (done ? done.fallbacks.join(";") || "无" : "没收到 done"));
  console.log(checks.join("\n"));
  process.exit(checks.some(c => c.startsWith("✗")) ? 1 : 0);
})().catch(e => { console.log(checks.join("\n") + "\n✗ 运行出错:" + e.stack); process.exit(1); });
