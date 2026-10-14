// 在 Node 里模拟 Figma 插件环境,跑 figma-plugin/code.js 的导出流程,并校验输出
const fs = require("fs"), vm = require("vm"), zlib = require("zlib"), path = require("path");
const PLUGIN = path.join(__dirname, "..", "figma-plugin", "code.js");
const OUT = path.join(__dirname, "_out", "sample.budfig.json");

// ---- 生成纯色 PNG(8x8),让还原后的画布有可辨认的色块 ----
function png(hex) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const w = 8, h = 8, raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) { raw[y * (w * 4 + 1)] = 0; for (let x = 0; x < w; x++) raw.set([r, g, b, 255], y * (w * 4 + 1) + 1 + x * 4); }
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type), data]); const crc = Buffer.alloc(4); crc.writeUInt32BE(zlib.crc32(td) >>> 0); return Buffer.concat([len, td, crc]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 6;
  return new Uint8Array(Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]));
}

// ---- 模拟 Figma 节点 ----
// clone:复制一份挂在原父级下(记在 liveClones,remove() 后移除);实例的子节点脱离前不可删;顶层 appendChild 后 x/y 即绝对坐标
const liveClones = new Set(), cloneLog = [];
const pageChildren = [];
function makeClone(src, color) {
  const bb = src.absoluteBoundingBox;
  const c = Object.assign({}, src, { id: src.id + "-clone", parent: src.parent || null, x: bb.x, y: bb.y, _w: bb.width, _h: bb.height });
  c.children = (src.children || []).map(ch => { const k = Object.assign({}, ch); k.remove = () => { if (c.type === "INSTANCE") throw new Error("实例的子节点不能删"); c.children.splice(c.children.indexOf(k), 1); }; return k; });
  Object.defineProperty(c, "absoluteBoundingBox", { get() { return { x: c.x, y: c.y, width: c._w, height: c._h }; }, enumerable: true });
  Object.defineProperty(c, "absoluteRenderBounds", { get() { const m = c.effects.length ? 20 : 0; return { x: c.x - m, y: c.y - m, width: c._w + 2 * m, height: c._h + 2 * m }; }, enumerable: true });
  c.resize = (w, h) => { c._w = w; c._h = h; };
  c.detachInstance = () => { c.type = "FRAME"; return c; };
  c.remove = () => { liveClones.delete(c); const i = pageChildren.indexOf(c); if (i >= 0) pageChildren.splice(i, 1); };
  c.exportAsync = async opt => { cloneLog.push({ type: c.type, children: c.children.length, onPage: pageChildren.includes(c), x: c.x, y: c.y, w: c._w, h: c._h, layoutMode: c.layoutMode, scale: opt && opt.constraint && opt.constraint.value }); return png(color); };
  liveClones.add(c);
  return c;
}
const MIXED = Symbol("mixed");
let seq = 100;
const exported = [];
function node(type, name, x, y, w, h, opt = {}, children) {
  const id = `${seq++}:${seq}`;
  const n = { id, type, name, visible: opt.visible !== false, absoluteBoundingBox: { x, y, width: w, height: h }, absoluteRenderBounds: { x, y, width: w, height: h }, opacity: 1, strokes: opt.strokes || [], effects: opt.effects || [] };
  if (opt.layoutMode) n.layoutMode = opt.layoutMode;
  if (type !== "GROUP") n.fills = opt.fills || [];
  if (["FRAME", "INSTANCE", "COMPONENT"].includes(type)) n.clipsContent = !!opt.clip;
  if (children) n.children = children;
  const color = opt.color || "#888888";
  n.exportAsync = async () => { exported.push(name); return png(color); };
  n.clone = () => makeClone(n, color);
  if (type === "INSTANCE") n.detachInstance = () => { throw new Error("原节点不应被 detach"); };
  return n;
}
const solid = hex => [{ type: "SOLID", visible: true, opacity: 1, color: { r: parseInt(hex.slice(1, 3), 16) / 255, g: parseInt(hex.slice(3, 5), 16) / 255, b: parseInt(hex.slice(5, 7), 16) / 255 } }];
function rect(name, x, y, w, h, color, opt = {}) { return node("RECTANGLE", name, x, y, w, h, Object.assign({ fills: solid(color), color }, opt)); }
function text(name, x, y, w, h, chars, size, weight, opt = {}) {
  const n = node("TEXT", name, x, y, w, h, { fills: solid(opt.color || "#ffffff") });
  n.characters = chars; n.fontName = { family: opt.family || "Noto Sans SC", style: weight >= 700 ? "Bold" : weight >= 500 ? "Medium" : "Regular" };
  n.fontSize = size; n.fontWeight = weight; n.textAlignHorizontal = opt.align || "LEFT"; n.textAlignVertical = "CENTER";
  if (opt.mixedFills) { n.fills = MIXED; n.getRangeFills = () => solid("#ffd84a"); }
  return n;
}

// ---- 交互组件桩:COMPONENT_SET(两个变体)+ createInstance / getMainComponentAsync / getNodeByIdAsync / reactions ----
// 临时实例:对目标变体子树深拷贝,根的 x/y 一变,所有后代跟着平移(与 Figma 里顶层节点 x/y = 绝对坐标一致);记在 liveInstances,remove() 后移除
const liveInstances = new Set(), nodeTable = {};
function shiftTree(n, dx, dy) { n._ab.x += dx; n._ab.y += dy; (n.children || []).forEach(c => shiftTree(c, dx, dy)); }
function copyAsInstance(src, root) {
  const ab = Object.assign({}, src.absoluteBoundingBox);
  const c = Object.assign({}, src, { id: "I" + src.id.replace(/:/g, "_") + "-tmp" + seq++, _ab: ab, type: root ? "INSTANCE" : src.type });
  delete c.reactions;
  Object.defineProperty(c, "absoluteBoundingBox", { get() { return c._ab; }, enumerable: true });
  Object.defineProperty(c, "absoluteRenderBounds", { get() { const m = (c.effects || []).length ? 20 : 0; return { x: c._ab.x - m, y: c._ab.y - m, width: c._ab.width + 2 * m, height: c._ab.height + 2 * m }; }, enumerable: true });
  c.children = (src.children || []).map(ch => copyAsInstance(ch, false));
  c.exportAsync = async () => { exported.push(c.name); return png(src._color || "#999999"); };
  c.clone = () => makeClone(c, src._color || "#999999");
  if (root) {
    Object.defineProperty(c, "x", { get() { return c._ab.x; }, set(v) { shiftTree(c, v - c._ab.x, 0); }, enumerable: true });
    Object.defineProperty(c, "y", { get() { return c._ab.y; }, set(v) { shiftTree(c, 0, v - c._ab.y); }, enumerable: true });
    c.resize = (w, h) => { c._ab.width = w; c._ab.height = h; };
    c.remove = () => { liveInstances.delete(c); const i = pageChildren.indexOf(c); if (i >= 0) pageChildren.splice(i, 1); };
    c.detachInstance = () => { throw new Error("临时实例不应被 detach"); };
    liveInstances.add(c);
  }
  return c;
}
// 组件集 Reuse/充值金额显隐(放在 99 共享组件表里,不在导出范围):「金额=隐藏」(旧 API reactions[].action)和「金额=显示」(反向切回)
const VX = 0, VY = 5200;
function variantComp(name, label, color) {
  const comp = node("COMPONENT", name, VX, VY, 610, 96, { fills: solid("#ffffff"), effects: [{ type: "DROP_SHADOW", visible: true }] }, [
    node("FRAME", "金额可见性", VX + 27, VY + 20, 52, 52, { color }, [node("VECTOR", "eye-" + name, VX + 27, VY + 20, 52, 52, { color })]),
    text("amount-lib", VX + 97, VY + 30, 319, 41, label, 30, 500)
  ]);
  comp._color = color; comp.createInstance = () => copyAsInstance(comp, true);
  return comp;
}
const compHidden = variantComp("金额=隐藏", "当前充值金额：*** 元", "#cccccc"), compShown = variantComp("金额=显示", "当前充值金额：98 元", "#ffd84a");
const compSet = node("COMPONENT_SET", "Reuse/充值金额显隐 · 原充值组件", VX, VY, 1300, 96, {}, [compHidden, compShown]);
compSet.children.forEach(c => { c.parent = compSet; nodeTable[c.id] = c; });
compHidden.reactions = [{ trigger: { type: "ON_CLICK" }, action: { type: "NODE", navigation: "CHANGE_TO", destinationId: compShown.id } }];          // 旧 API:单个 action
compShown.reactions = [{ trigger: { type: "ON_CLICK" }, actions: [{ type: "NODE", navigation: "CHANGE_TO", destinationId: compHidden.id }] }];   // 新 API:actions 数组
// 另一个组件集的变体(不同组):Summary/AmountVisibility 引用跨组的目标,应被忽略
const otherSet = node("COMPONENT_SET", "Other/集合", 0, 6000, 100, 100, {}, [node("COMPONENT", "x=1", 0, 6000, 100, 100), node("COMPONENT", "x=2", 0, 6000, 100, 100)]);
otherSet.children.forEach(c => { c.parent = otherSet; nodeTable[c.id] = c; });

// 界面 05 放在总览画板 (2600, 300);结构照搬真实稿子「05 · 充值福利 / 奖励总览」
const X = 2600, Y = 300;
const cards = ["hair", "dress", "shoe", "coin", "bench", "action", "effect", "wing"].map((k, i) => {
  const cx = X + 163 + i * 450, cy = Y + 260;
  return node("INSTANCE", "RewardCard/" + k, cx, cy, 395, 570, {}, [
    rect("card-surface", cx, cy + 115, 395, 455, "#f1e6ff", { strokes: [{ type: "SOLID", visible: true }] }),
    rect("status-surface", cx, cy + 115, 395, 65, "#7d6bff"),
    text("status", cx + 20, cy + 127, 320, 42, "✓ 已领取", 28, 500),
    node("INSTANCE", "奖励图像 / RewardArt", cx + 36, cy + 185, 323, 295, { color: "#ff8fb1" }, [node("VECTOR", "art", cx + 36, cy + 185, 323, 295, { color: "#ff8fb1" })]),
    rect("ribbon", cx, cy + 480, 395, 90, "#ffd84a"),
    text("reward-name", cx + 18, cy + 485, 359, 44, "奖励 " + k, 32, 700, { color: "#3a2f00", align: "CENTER" }),
    text("amount", cx, cy + 525, 395, 45, (6 + i * 30) + " 元", 30, 700, { color: "#3a2f00", align: "CENTER" })
  ]);
});
const screen05 = node("FRAME", "05 · 充值福利 / 奖励总览", X, Y, 2436, 1125, { clip: true }, [
  node("INSTANCE", "00_Background", X, Y, 2436, 1125, {}, [
    rect("bg-rewards-soft", X, Y, 2436, 1125, "#6b5bd6"),
    text("brand/BUD", X + 1400, Y + 200, 934, 617, "BUD", 500, 900, { color: "#7f70e0" }),
    text("brand/signature", X + 1800, Y + 160, 440, 28, "✦ B U D   R E W A R D S", 20, 500),
    rect("footer/hairline", X + 148, Y + 1080, 2140, 1, "#ffffff")
  ]),
  node("INSTANCE", "01_Back", X + 40, Y + 30, 102, 106, { color: "#ffffff" }, [rect("btn_fanhui", X + 40, Y + 30, 102, 106, "#ffffff")]),
  rect("nav/title-plate", X + 160, Y + 40, 300, 80, "#4a3f9a"),
  text("nav/title", X + 190, Y + 53, 240, 54, "充值福利", 44, 700),
  text("intro", X + 163, Y + 150, 1300, 76, "累计充值,解锁专属好礼", 56, 700),
  text("rules-link", X + 2100, Y + 60, 210, 37, "ⓘ 福利规则", 28, 500),
  node("FRAME", "02_RewardsScrollView", X + 163, Y + 260, 2110, 570, { clip: true }, [
    node("FRAME", "Content", X + 163, Y + 260, 3710, 570, {}, cards)
  ]),
  rect("progress/rail", X + 163, Y + 880, 2110, 12, "#3a2f7a"),
  rect("progress/filled", X + 163, Y + 880, 1050, 12, "#ffd84a"),
  node("INSTANCE", "Summary/AmountVisibility", X + 163, Y + 960, 610, 100, {}, [
    rect("summary/background", X + 163, Y + 960, 610, 100, "#4a3f9a"),
    node("FRAME", "Content", X + 163, Y + 960, 610, 100, {}, [
      node("FRAME", "Icon/金额可见性", X + 190, Y + 984, 52, 52, { color: "#ffd84a" }, [node("VECTOR", "eye", X + 190, Y + 984, 52, 52, { color: "#ffd84a" })]),
      text("Label/累计金额", X + 260, Y + 990, 319, 41, "当前累计充值:68 元", 30, 500)
    ])
  ]),
  text("next-tier", X + 800, Y + 990, 650, 40, "再充值 30 元,解锁下一档", 30, 400, { mixedFills: true }),
  // 含文字、自身有白底 + 投影的实例(充值界面的 Amount/RechargeLibrary):外观要靠 #bg 底图保留
  node("INSTANCE", "Amount/RechargeLibrary", X + 163, Y + 1070, 610, 96, { fills: solid("#ffffff"), effects: [{ type: "DROP_SHADOW", visible: true }], layoutMode: "HORIZONTAL" }, [
    node("FRAME", "金额可见性", X + 190, Y + 1090, 52, 52, { color: "#ffd84a" }, [node("VECTOR", "eye2", X + 190, Y + 1090, 52, 52, { color: "#ffd84a" })]),
    text("amount-lib", X + 260, Y + 1100, 319, 41, "充值库 128 元", 30, 500)
  ]),
  node("INSTANCE", "04_CTA", X + 1873, Y + 950, 400, 120, {}, [
    rect("background", X + 1873, Y + 950, 400, 120, "#ffd84a"),
    text("label", X + 1923, Y + 980, 300, 61, "前往充值", 44, 700, { color: "#3a2f00", align: "CENTER" })
  ]),
  text("scroll-hint", X + 1798, Y + 860, 475, 34, "左右滑动查看更多奖励  ›", 24, 400),
  text("hidden-debug", X, Y, 100, 20, "不应导出", 20, 400)
]);
screen05.children[screen05.children.length - 1].visible = false;
const findNode = (n, name) => { if (n.name === name) return n; for (const c of n.children || []) { const r = findNode(c, name); if (r) return r; } return null; };
{   // Amount/RechargeLibrary:主组件 = 「金额=隐藏」,实例自身有 ON_CLICK → CHANGE_TO「金额=显示」(新 API actions 数组);「金额=隐藏」上还有同一目标的旧 API action(去重)
  const lib = findNode(screen05, "Amount/RechargeLibrary");
  lib.getMainComponentAsync = async () => compHidden;
  lib.reactions = [{ trigger: { type: "ON_CLICK" }, actions: [{ type: "NODE", navigation: "CHANGE_TO", destinationId: compShown.id }] }];
  // Summary/AmountVisibility:主组件在别的组件集、reaction 指向不同组的变体 → 不应产出 variantStates
  const sum = findNode(screen05, "Summary/AmountVisibility");
  sum.getMainComponentAsync = async () => otherSet.children[0];
  sum.reactions = [{ trigger: { type: "ON_CLICK" }, actions: [{ type: "NODE", navigation: "CHANGE_TO", destinationId: compShown.id }] }];
  // 04_CTA:只有跳转(NAVIGATE)的原型点击,不是 CHANGE_TO → 忽略;用同步 mainComponent 属性
  const cta = findNode(screen05, "04_CTA");
  const ctaSet = node("COMPONENT_SET", "CTA/状态", 0, 6200, 200, 100, {}, [node("COMPONENT", "状态=A", 0, 6200, 100, 100), node("COMPONENT", "状态=B", 100, 6200, 100, 100)]);
  ctaSet.children.forEach(c => { c.parent = ctaSet; nodeTable[c.id] = c; c.createInstance = () => copyAsInstance(c, true); });
  const navi = [{ trigger: { type: "ON_CLICK" }, actions: [{ type: "NODE", navigation: "NAVIGATE", destinationId: ctaSet.children[1].id }] }];
  ctaSet.children[0].reactions = navi;
  cta.mainComponent = ctaSet.children[0];
  cta.reactions = navi;
}
const screen02 = node("FRAME", "02 · 充值到账确认中", 0, 300, 2436, 1125, { clip: true }, [
  rect("bg", 0, 300, 2436, 1125, "#6b5bd6"),
  text("title", 900, 800, 600, 60, "正在确认到账…", 44, 700, { family: "Some Display Font" })
]);
const sheet99 = node("FRAME", "99 · 共享组件与可导出资源", 0, 5000, 7780, 2240, {}, [rect("x", 0, 5000, 100, 100, "#000000")]);
const board = node("FRAME", "Unity中间版", 0, 0, 7980, 14100, {}, [sheet99, screen05, screen02]);

// ---- 模拟 figma 全局 ----
const messages = [];
const figma = {
  mixed: MIXED,
  currentPage: { selection: [board], children: pageChildren, appendChild(c) { pageChildren.push(c); c.parent = this; } },
  root: { name: "充值福利 xisi" },
  showUI() {}, on() {}, closePlugin() {},
  ui: { postMessage: m => messages.push(m), onmessage: null },
  getNodeByIdAsync: async id => nodeTable[id] || null,
  base64Encode: bytes => Buffer.from(bytes).toString("base64")
};
vm.runInNewContext(fs.readFileSync(PLUGIN, "utf8"), { figma, __html__: "", console, Symbol, Promise, Math, JSON, Date, String, Object, Array, Error, RegExp, Number });

(async () => {
  const sel = messages.find(m => m.type === "selection");
  const checks = [];
  const ok = (cond, what) => checks.push((cond ? "✓ " : "✗ ") + what);
  ok(sel && sel.board === "Unity中间版", "选中总览画板时识别为画板");
  ok(sel && sel.screens.length === 2 && sel.screens.every(s => s.w === 2436), "只列出 2 个 2436×1125 界面(组件表被排除)");
  figma.ui.onmessage({ type: "export", ids: sel.screens.map(s => s.id) });
  for (let i = 0; i < 100 && !messages.some(m => m.type === "done" || m.type === "error"); i++) await new Promise(r => setTimeout(r, 20));
  const err = messages.find(m => m.type === "error"); if (err) { console.log("导出报错:", err.text); process.exit(1); }
  const done = messages.find(m => m.type === "done");
  const pkg = JSON.parse(done.json);
  ok(pkg.format === "bud-ui-studio/figma-export" && pkg.rules === "v1" && pkg.screens.length === 2, "导出包格式/规则版本/界面数正确");
  const s05 = pkg.screens.find(s => s.frame.name.startsWith("05"));
  const names = exported;
  ok(!names.includes("nav/title") && !names.includes("reward-name") && !names.includes("brand/BUD"), "Noto Sans SC 文字没有被渲染成图(保留可编辑)");
  ok(names.includes("title"), "非白名单字体的文字(02 界面)被烘焙成图");
  ok(names.includes("01_Back") && !names.includes("btn_fanhui"), "不含文字的分组整体渲染一张(01_Back)");
  ok(names.includes("Icon/金额可见性") && !names.includes("eye"), "图标整体渲染(Icon/金额可见性)");
  ok(names.filter(n => n === "card-surface").length === 8, "8 张卡片的底板各自渲染");
  ok(!names.includes("hidden-debug"), "隐藏图层不导出");
  ok(!names.includes("x"), "未勾选的组件表不导出");
  const nt = (function find(n) { if (n.name === "next-tier") return n; for (const c of n.children || []) { const r = find(c); if (r) return r; } })(s05.frame);
  ok(nt && Array.isArray(nt.fills) && nt.fills[0].type === "SOLID", "混合填色文字取首字颜色,可正常序列化");
  ok(Object.keys(s05.images).length === 45, `界面 05 切图数 = ${Object.keys(s05.images).length}(预期 45 = 41 + 金额可见性图标 + 容器底图 #bg + 交互目标变体的图标和 #bg)`);
  const lib = (function find(n) { if (n.name === "Amount/RechargeLibrary") return n; for (const c of n.children || []) { const r = find(c); if (r) return r; } })(s05.frame);
  const bgKeys = Object.keys(s05.images).filter(k => k.endsWith("#bg"));
  const vs = lib && lib.variantStates, vtree = vs && vs[0] && vs[0].tree;
  ok(lib && bgKeys.length === 2 && bgKeys.includes(lib.id + "#bg") && vtree && bgKeys.includes(vtree.id + "#bg"), "含文字且有白底+投影的 INSTANCE 产出 #bg 底图(另加交互目标变体根的 #bg),其它容器(无自身外观)不产出");
  ok(lib && lib.bgRenderBounds && lib.bgRenderBounds.x === lib.absoluteBoundingBox.x - 20 && lib.bgRenderBounds.width === lib.absoluteBoundingBox.width + 40, "bgRenderBounds 含投影外扩,序列化在该节点上");
  // ---- 交互组件 variantStates ----
  const allVs = []; (function walkS(n) { if (n.variantStates) allVs.push(n); (n.children || []).forEach(walkS); })(s05.frame);
  ok(allVs.length === 1 && allVs[0] === lib, "只有带 CHANGE_TO 的实例产出 variantStates(跨组件集的、NAVIGATE 的都不算)");
  ok(vs && vs.length === 1 && vs[0].name === "金额=显示" && vs[0].current === "金额=隐藏", "variantStates 记录目标变体名和当前变体名;实例与变体上的 reaction 指向同一目标时去重(新旧 API 都认)");
  ok(vtree && vtree.name === "金额=显示" && vtree.type === "INSTANCE" && JSON.stringify(vtree.absoluteBoundingBox) === JSON.stringify(lib.absoluteBoundingBox), "目标变体临时实例与原实例同绝对坐标、同尺寸");
  const vtext = vtree && (function find(n) { if (n.type === "TEXT") return n; for (const c of n.children || []) { const r = find(c); if (r) return r; } })(vtree);
  ok(vtext && vtext.characters === "当前充值金额：98 元" && lib.children.some(c => c.type === "TEXT" && c.characters === "充值库 128 元"), "目标变体的文字内容进了子树,原实例结构不变");
  const vIcon = vtree && vtree.children.find(c => c.name === "金额可见性");
  ok(vIcon && !!s05.images[vIcon.id] && vtree.bgRenderBounds && !!s05.images[vtree.id + "#bg"], "目标变体的切图(图标)与根 #bg 并入该界面 images,键是临时节点 id");
  ok(liveInstances.size === 0, "导出结束后文档里不残留交互目标变体的临时实例");
  ok(cloneLog.length === 2 && cloneLog[1].type === "FRAME" && cloneLog[1].children === 0 && cloneLog[1].onPage && cloneLog[1].x === lib.absoluteBoundingBox.x && cloneLog[1].y === lib.absoluteBoundingBox.y && cloneLog[1].w === 610 && cloneLog[1].h === 96, "目标变体根的 #bg 同样走 clone 流程(脱离实例、清空子节点、顶层同坐标)");
  ok(cloneLog.length >= 1 && cloneLog[0].type === "FRAME" && cloneLog[0].children === 0 && cloneLog[0].onPage && cloneLog[0].layoutMode === "NONE" && cloneLog[0].x === lib.absoluteBoundingBox.x && cloneLog[0].y === lib.absoluteBoundingBox.y && cloneLog[0].w === 610 && cloneLog[0].h === 96, "底图出图时 clone 已脱离实例、清空子节点、在页面顶层同一绝对坐标、尺寸不变");
  ok(liveClones.size === 0 && pageChildren.length === 0, "导出结束后文档里不残留 clone");
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, done.json);
  console.log(checks.join("\n"));
  console.log(`\n导出包:${(done.json.length / 1024).toFixed(0)} KB,${done.count} 个界面,${done.images} 张切图,跳过 ${done.skipped}`);
  process.exit(checks.some(c => c.startsWith("✗")) ? 1 : 0);
})();
