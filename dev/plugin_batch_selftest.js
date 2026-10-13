// Figma 插件「资源批处理」回归测试:在 Node 里模拟 Figma 插件 API,跑一遍「收集选中资源 → 摆回处理结果」(网络部分在 batch.html,不在这里测)
// 用法:node dev/plugin_batch_selftest.js
// 检查:每个选中节点 = 一个资源,子图层各一张切图,位置相对资源左上角(含旋转 / 阴影时用渲染边界)、宽高取导出 PNG 的实际像素;
//   没有子图层的节点自己算一张;隐藏的子图层不导出;摆回时在原资源右边 60px 建画框,切图按位置铺图片填充;manifest 只放行本机工作台地址。
const fs = require("fs"), path = require("path"), vm = require("vm"), zlib = require("zlib");
const ROOT = path.join(__dirname, "..");
const code = fs.readFileSync(path.join(ROOT, "figma-plugin/code.js"), "utf8");
const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "figma-plugin/manifest.json"), "utf8"));
const checks = [], ok = (c, what) => checks.push((c ? "✓ " : "✗ ") + what);

function png(w, h) {   // 最小的合法 PNG(全透明 RGBA)
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type), data]);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(zlib.crc32(td) >>> 0); return Buffer.concat([len, td, crc]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 6;
  const raw = Buffer.alloc((w * 4 + 1) * h);
  return new Uint8Array(Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]));
}
let nid = 0;
function node(type, name, x, y, w, h, kids, extra) {
  const n = Object.assign({ id: "1:" + (++nid), type, name, x, y, width: w, height: h, visible: true, parent: null, children: kids || [],
    absoluteBoundingBox: { x, y, width: w, height: h }, absoluteRenderBounds: { x, y, width: w, height: h },
    async exportAsync() { return png(Math.round(n.absoluteRenderBounds.width), Math.round(n.absoluteRenderBounds.height)); },
    appendChild(c) { c.parent = n; n.children.push(c); }, resize(w2, h2) { n.width = w2; n.height = h2; } }, extra || {});
  n.children.forEach(c => { c.parent = n; });
  if (!kids && type !== "FRAME") delete n.children;
  return n;
}
// 资源 A:画框(绝对坐标 1000,500),子图层:底框、星星(带阴影,渲染边界比形状大 4px)、隐藏的参考图层
const star = node("VECTOR", "上_星星", 1150, 520, 40, 40, null, { absoluteRenderBounds: { x: 1146, y: 516, width: 48, height: 48 } });
const frameA = node("FRAME", "头像框_9002", 1000, 500, 256, 256, [node("RECTANGLE", "底框", 1000, 500, 256, 256), star,
  node("RECTANGLE", "参考", 1000, 500, 256, 256, null, { visible: false })]);
// 资源 B:没有子图层的单张图
const single = node("RECTANGLE", "bg_main", 2000, 0, 300, 120);
const page = node("PAGE", "第 1 页", 0, 0, 0, 0, [frameA, single]);
const messages = [], storage = {}, images = [];
const figma = {
  command: "batch", root: { name: "测试文件", type: "DOCUMENT" }, currentPage: Object.assign(page, { selection: [frameA, single] }),
  showUI() {}, closePlugin() {}, on() {},
  ui: { postMessage: m => messages.push(m), onmessage: null },
  clientStorage: { getAsync: async k => storage[k], setAsync: async (k, v) => { storage[k] = v; } },
  base64Encode: b => Buffer.from(b).toString("base64"), base64Decode: s => new Uint8Array(Buffer.from(s, "base64")),
  createImage(bytes) { if (!bytes || !bytes.length) throw new Error("空图片"); images.push(bytes); return { hash: "h" + images.length }; },
  createFrame: () => node("FRAME", "", 0, 0, 100, 100, []), createRectangle: () => node("RECTANGLE", "", 0, 0, 100, 100),
  getNodeByIdAsync: async id => [frameA, single].find(n => n.id === id) || null,
  viewport: { center: { x: 0, y: 0 }, scrollAndZoomIntoView() {} },
};
page.parent = figma.root; frameA.parent = page; single.parent = page;
vm.runInNewContext(code, { figma, __html__: "", __uiFiles__: { main: "", import: "", batch: "<batch>" }, console, Math, Promise, JSON, Object, Array, String, Number, Error, Uint8Array });
const ask = msg => new Promise(res => { const before = messages.length; figma.ui.onmessage(msg); const t = setInterval(() => {
  const m = messages.slice(before).find(x => x.id === msg.id && (x.type === "ack" || x.type === "error")); if (m) { clearInterval(t); res(m); } }, 5); });

(async () => {
  await new Promise(r => setTimeout(r, 20));
  ok(messages.some(m => m.type === "selection" && m.items.length === 2), "打开时把选中的 2 个资源告诉界面");
  const r = await ask({ type: "collect", id: 1 });
  ok(r.type === "ack", "收集选中资源成功" + (r.type === "error" ? ":" + r.text : ""));
  const [A, B] = r.data.assets;
  ok(A.name === "头像框_9002" && A.w === 256 && A.h === 256 && A.nodeId === frameA.id && A.preview, "资源 = 选中的画框:名字、尺寸、节点 id、整体预览图");
  ok(A.slices.length === 2 && A.slices.map(s => s.name).join(",") === "底框,上_星星", "子图层各一张切图,隐藏的图层不导出");
  const s2 = A.slices[1];
  ok(s2.x === 146 && s2.y === 16 && s2.w === 48 && s2.h === 48, `带阴影的图层按渲染边界算位置和尺寸(${s2.x},${s2.y} ${s2.w}×${s2.h})`);
  ok(B.slices.length === 1 && B.slices[0].name === "bg_main" && B.slices[0].x === 0 && B.slices[0].w === 300, "没有子图层的节点自己算一张切图");
  ok(r.data.file === "测试文件" && r.data.page === "第 1 页", "带上文件名和页面名");
  const result = { job: "j1", name: "自测", assets: [
    { name: A.name, nodeId: A.nodeId, w: 256, h: 256, slices: A.slices.map(s => ({ name: s.name, x: s.x, y: s.y, w: s.w, h: s.h, isNew: true, png: s.png })) },
    { name: "找不到原图层的资源", nodeId: "9:9", w: 300, h: 120, slices: B.slices.map(s => ({ name: s.name, x: 0, y: 0, w: s.w, h: s.h, isNew: false, png: s.png })) }] };
  const p = await ask({ type: "place", id: 2, result });
  ok(p.type === "ack" && p.data.frames === 2, "取回结果:建了 2 个画框" + (p.type === "error" ? ":" + p.text : ""));
  const placed = page.children.filter(n => n.name && n.name.indexOf("· 自测") > 0);
  const fa = placed.find(n => n.name.startsWith("头像框_9002"));
  ok(fa && fa.x === 1000 + 256 + 60 && fa.y === 500 && fa.width === 256, "新画框摆在原资源右边 60px、同样大小");
  ok(fa && fa.children.length === 2 && fa.children[1].x === 146 && fa.children[1].fills[0].type === "IMAGE", "切图按原位置摆放,图片填充");
  ok(placed.some(n => n.name.startsWith("找不到原图层") && n.children[0].name.indexOf("(原图)") > 0), "原图层找不到时也能摆(放在视口中央),没换新图的切图标「原图」");
  ok((await ask({ type: "saveCfg", id: 3, cfg: { server: "http://localhost:8791", key: "abcd1234" } })).type === "ack" && storage.budui_bridge.key === "abcd1234", "配对码存在插件本地(clientStorage)");
  const na = manifest.networkAccess || {};
  ok(na.allowedDomains.join() === "none" && na.devAllowedDomains.every(d => /^http:\/\/(localhost|127\.0\.0\.1):8791$/.test(d)), "manifest 只放行本机工作台地址");
  ok(manifest.menu.some(m => m.command === "batch") && manifest.ui.batch === "batch.html", "manifest 有「资源批处理」命令和界面");
  ok(!/\?\.|\?\?|\.\.\.[A-Za-z_$[{(]/.test(code.replace(/\/\/.*$/gm, "")), "插件主线程只用 ES2017 语法");
  console.log(checks.join("\n"));
  const bad = checks.filter(c => c.startsWith("✗")).length;
  console.log(bad ? `\n${bad} 项失败` : "\n全部通过");
  process.exit(bad ? 1 : 0);
})();
