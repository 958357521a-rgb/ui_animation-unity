// BUD UI Studio 导出插件 · 主线程
// 在 Figma 里读取选中界面的图层结构并导出切图,打包成 .budfig.json,交给 BUD UI Studio「导入插件包」还原。
// 全程在本机完成,不调用 Figma REST 接口,不受账号席位的调用额度限制。
//
// 规则版本 RULES:哪些图层保留为可编辑文字/分组、哪些渲染成切图,
// 必须与 BUD_UI_Studio.html 里 buildScreenFromFigma 的 plan 规则完全一致;改一边就要同步改另一边并升版本号。
// 代码刻意只用 ES2017 语法(不用 ?. ?? 和对象展开),兼容 Figma 插件沙箱。

var RULES = "v1";
var STAGE_W = 2436, STAGE_H = 1125;
var LIVE_FONT = /source han sans|思源黑|noto sans (sc|cjk)|noto sans s chinese|montserrat|pingfang|苹方|microsoft yahei|微软雅黑/i;


function isFrameLike(n) { return n.type === "FRAME" || n.type === "COMPONENT" || n.type === "INSTANCE"; }
function box(r) { return r ? { x: r.x, y: r.y, width: r.width, height: r.height } : null; }

// 选中一张总览画板时,自动展开为其中与画布同比例的界面;否则就是选中的界面本身
function candidates() {
  var sel = figma.currentPage.selection.filter(isFrameLike);
  if (sel.length === 1 && sel[0].children) {
    var b = sel[0].absoluteBoundingBox;
    var kids = sel[0].children.filter(function (c) {
      var cb = c.absoluteBoundingBox;
      return c.visible !== false && isFrameLike(c) && cb && b
        && Math.abs(cb.width / cb.height - STAGE_W / STAGE_H) < 0.15
        && (cb.width < b.width * 0.6 || cb.height < b.height * 0.6);
    });
    if (kids.length >= 2) return { board: sel[0].name, list: kids };
  }
  return { board: null, list: sel };
}

function sendSelection() {
  var c = candidates();
  figma.ui.postMessage({
    type: "selection",
    board: c.board,
    screens: c.list.map(function (n) {
      var b = n.absoluteBoundingBox || { width: n.width, height: n.height };
      return { id: n.id, name: n.name, w: Math.round(b.width), h: Math.round(b.height) };
    })
  });
}

// ---------- 序列化:输出与 Figma REST 接口同名的字段,Studio 可以复用同一套还原逻辑 ----------
function weightOf(styleName) {
  var s = (styleName || "").toLowerCase();
  if (/black|heavy/.test(s)) return 900;
  if (/extra ?bold|ultra ?bold/.test(s)) return 800;
  if (/semi ?bold|demi ?bold/.test(s)) return 600;
  if (/bold/.test(s)) return 700;
  if (/medium/.test(s)) return 500;
  if (/extra ?light|ultra ?light/.test(s)) return 200;
  if (/light/.test(s)) return 300;
  if (/thin|hairline/.test(s)) return 100;
  return 400;
}

function paints(list) {
  if (!list || list === figma.mixed) return [];
  return list.map(function (p) {
    return {
      type: p.type,
      visible: p.visible !== false,
      opacity: p.opacity === undefined ? 1 : p.opacity,
      color: p.color ? { r: p.color.r, g: p.color.g, b: p.color.b } : undefined
    };
  });
}

function ser(node, idMap) {
  idMap[node.id] = node;
  var o = { id: node.id, name: node.name, type: node.type, visible: node.visible !== false };
  if ("absoluteBoundingBox" in node) o.absoluteBoundingBox = box(node.absoluteBoundingBox);
  if ("absoluteRenderBounds" in node) o.absoluteRenderBounds = box(node.absoluteRenderBounds);
  if ("opacity" in node) o.opacity = node.opacity;
  if ("clipsContent" in node) o.clipsContent = !!node.clipsContent;
  if ("strokes" in node) o.strokes = paints(node.strokes);
  if ("effects" in node && node.effects !== figma.mixed) {
    o.effects = node.effects.map(function (e) { return { type: e.type, visible: e.visible !== false }; });
  }
  if (node.type === "TEXT") {
    var len = node.characters.length;
    var fills = node.fills === figma.mixed ? (len ? node.getRangeFills(0, 1) : []) : node.fills;
    var fn = node.fontName === figma.mixed ? (len ? node.getRangeFontName(0, 1) : { family: "", style: "" }) : node.fontName;
    var fs = node.fontSize === figma.mixed ? (len ? node.getRangeFontSize(0, 1) : 36) : node.fontSize;
    var fw = typeof node.fontWeight === "number" ? node.fontWeight : weightOf(fn.style);
    o.fills = paints(fills);
    o.characters = node.characters;
    o.style = {
      fontFamily: fn.family,
      fontWeight: fw,
      fontSize: fs,
      textAlignHorizontal: node.textAlignHorizontal,
      textAlignVertical: node.textAlignVertical
    };
  } else if ("fills" in node) {
    o.fills = paints(node.fills);
  }
  if ("children" in node) o.children = node.children.map(function (c) { return ser(c, idMap); });
  return o;
}

// ---------- 切图规则(与 Studio 的 plan 逐条一致) ----------
function visibleNode(n) { return n.visible !== false; }
function hasText(n) {
  return n.type === "TEXT" || (n.children || []).some(function (c) { return visibleNode(c) && hasText(c); });
}
function liveText(t) {
  var fam = (t.style && t.style.fontFamily) || "";
  var fills = (t.fills || []).filter(visibleNode);
  return LIVE_FONT.test(fam)
    && fills.every(function (f) { return f.type === "SOLID"; })
    && !(t.effects || []).some(visibleNode)
    && !(t.strokes || []).some(visibleNode);
}
function planRenderIds(frame) {
  var ids = [];
  (function walk(node, depth) {
    (node.children || []).forEach(function (c) {
      if (!visibleNode(c) || !c.absoluteBoundingBox) return;
      if (c.type === "TEXT" && liveText(c)) return;
      if (c.children && c.children.length && hasText(c) && depth < 8) { walk(c, depth + 1); return; }
      ids.push(c.id);
    });
  })(frame, 0);
  return ids;
}
// 额外导出(不改变上面的切图集合):planRenderIds 走进去的含文字容器,自身的外观(填充/描边/投影)否则整个丢失,
// 这里列出这些容器(判定与 planRenderIds 的 walk 同条件),doExport 再给有可见外观的出一张去掉子节点的底图 "<id>#bg"。
// Studio 的 REST 拉取路径没有这种图;工作台导入时只认包里有 #bg 的容器。
function planBgIds(frame) {
  var ids = [];
  (function walk(node, depth) {
    (node.children || []).forEach(function (c) {
      if (!visibleNode(c) || !c.absoluteBoundingBox) return;
      if (c.type === "TEXT" && liveText(c)) return;
      if (c.children && c.children.length && hasText(c) && depth < 8) { ids.push(c.id); walk(c, depth + 1); return; }
    });
  })(frame, 0);
  return ids;
}
function hasOwnLook(n) {
  function vis(list) {
    return !!list && list !== figma.mixed && list.some(function (p) { return p.visible !== false && (p.opacity === undefined || p.opacity > 0); });
  }
  return ("fills" in n && vis(n.fills)) || ("strokes" in n && vis(n.strokes)) || ("effects" in n && vis(n.effects));
}

// ---------- 导出 ----------
function progress(text) { figma.ui.postMessage({ type: "progress", text: text }); }

// 被祖先的裁切(滚动区 Viewport / Content 这类 clipsContent)挡住一部分或全部的节点。
// exportAsync 默认按"屏幕上看得到的部分"出图:滚动区外的卡片会被切掉一半或只剩 1×1。
// useAbsoluteBounds 又会按节点外框硬切(放大镜按钮的圆底比外框大一圈,被切成圆角方块),
// 所以这类节点复制到页面顶层同一绝对坐标(不受任何祖先裁切)再按完整渲染范围出图,出完一定删掉复制品。
async function exportUnclipped(node, opts) {
  var bb = node.absoluteBoundingBox;
  var clone = null;
  try {
    clone = node.clone();
    figma.currentPage.appendChild(clone);
    clone.x = bb.x; clone.y = bb.y;
    clone.visible = true;
    var rb = clone.absoluteRenderBounds;
    if (!rb) return null;
    var bytes = await clone.exportAsync(opts);
    return { bytes: bytes, bounds: box(rb) };
  } catch (e) {
    return null;
  } finally {
    if (clone) { try { clone.remove(); } catch (e2) {} }
  }
}
function clippedByAncestor(node, screen) {
  var b = node.absoluteBoundingBox;
  if (!b) return false;
  for (var p = node.parent; p && p !== screen; p = p.parent) {
    if (!p.clipsContent || !p.absoluteBoundingBox) continue;
    var a = p.absoluteBoundingBox;
    if (b.x < a.x - 0.5 || b.y < a.y - 0.5 || b.x + b.width > a.x + a.width + 0.5 || b.y + b.height > a.y + a.height + 0.5) return true;
  }
  return false;
}
function findSer(tree, id) {
  if (tree.id === id) return tree;
  for (var i = 0; i < (tree.children || []).length; i++) { var r = findSer(tree.children[i], id); if (r) return r; }
  return null;
}

// 容器自身外观底图:clone → (实例先脱离)→ 清掉全部子节点 → 挪到页面顶层同一绝对坐标(不受祖先裁切)→ 出图 → 一定删掉 clone
async function exportBg(node, imgScale) {
  var bb = node.absoluteBoundingBox;
  var clone = null;
  try {
    clone = node.clone();
    if (clone.type === "INSTANCE") clone = clone.detachInstance() || clone;
    if ("layoutMode" in clone && clone.layoutMode !== "NONE") clone.layoutMode = "NONE";   // 自动布局会在清空子节点后收缩尺寸
    for (var i = clone.children.length - 1; i >= 0; i--) clone.children[i].remove();
    figma.currentPage.appendChild(clone);
    clone.x = bb.x; clone.y = bb.y;
    clone.resize(Math.max(0.01, bb.width), Math.max(0.01, bb.height));
    clone.visible = true;
    var bytes = await clone.exportAsync({ format: "PNG", constraint: { type: "SCALE", value: imgScale } });
    return { b64: figma.base64Encode(bytes), bounds: box(clone.absoluteRenderBounds || clone.absoluteBoundingBox) };
  } finally {
    if (clone) { try { clone.remove(); } catch (e2) {} }
  }
}

async function doExport(ids) {
  var chosen = candidates().list.filter(function (n) { return ids.indexOf(n.id) >= 0; });
  if (!chosen.length) throw new Error("没有勾选要导出的界面");
  var out = {
    format: "bud-ui-studio/figma-export",
    version: 1,
    rules: RULES,
    exportedAt: new Date().toISOString(),
    fileName: figma.root.name,
    screens: []
  };
  var skipped = 0, imageCount = 0;
  for (var k = 0; k < chosen.length; k++) {
    var screen = chosen[k];
    var idMap = {};
    var tree = ser(screen, idMap);
    var sb = tree.absoluteBoundingBox;
    var imgScale = Math.min(4, Math.max(0.25, STAGE_W / sb.width));
    var renderIds = planRenderIds(tree);
    var images = {};
    for (var i = 0; i < renderIds.length; i++) {
      progress("界面 " + (k + 1) + "/" + chosen.length + "「" + screen.name + "」:切图 " + (i + 1) + "/" + renderIds.length);
      try {
        var opts = { format: "PNG", constraint: { type: "SCALE", value: imgScale } };
        var bytes = null;
        if (clippedByAncestor(idMap[renderIds[i]], screen)) {
          var sn = findSer(tree, renderIds[i]);
          var whole = await exportUnclipped(idMap[renderIds[i]], opts);
          if (whole) {
            bytes = whole.bytes;
            if (sn) sn.absoluteRenderBounds = whole.bounds;              // 位置按复制品的完整渲染范围(含超出外框的圆底、投影)
          } else {
            opts.useAbsoluteBounds = true;                               // 复制失败才退回按外框出图(超出外框的部分会被切掉)
            if (sn) sn.absoluteRenderBounds = sn.absoluteBoundingBox;
          }
        }
        if (!bytes) bytes = await idMap[renderIds[i]].exportAsync(opts);
        images[renderIds[i]] = figma.base64Encode(bytes);
        imageCount++;
      } catch (e) {
        skipped++;
      }
    }
    var bgIds = planBgIds(tree);
    for (var j = 0; j < bgIds.length; j++) {
      var bn = idMap[bgIds[j]];
      if (!hasOwnLook(bn)) continue;
      progress("界面 " + (k + 1) + "/" + chosen.length + "「" + screen.name + "」:容器底图 " + (j + 1) + "/" + bgIds.length);
      try {
        var bg = await exportBg(bn, imgScale);
        var bs = findSer(tree, bgIds[j]);
        if (bs && bg.bounds) { images[bgIds[j] + "#bg"] = bg.b64; bs.bgRenderBounds = bg.bounds; imageCount++; }
      } catch (e3) {
        skipped++;
      }
    }
    out.screens.push({ frame: tree, images: images });
  }
  progress("正在打包…");
  figma.ui.postMessage({
    type: "done",
    json: JSON.stringify(out),
    fileName: figma.root.name,
    count: chosen.length,
    images: imageCount,
    skipped: skipped
  });
}

// 两个命令(manifest 的 menu):export = 导出给工作台(原有功能),import = 把工作台工程还原成 Figma 图层(importer.js 段)
var UI_FILES = typeof __uiFiles__ !== "undefined" ? __uiFiles__ : null;
if (figma.command === "import") {
  startImport(UI_FILES ? UI_FILES["import"] : __html__);
} else if (figma.command === "batch") {
  startBatch(UI_FILES ? UI_FILES.batch : __html__);
} else {
  figma.showUI(UI_FILES ? UI_FILES.main : __html__, { width: 380, height: 540, themeColors: true });
  figma.ui.onmessage = function (msg) {
    if (msg.type === "export") {
      doExport(msg.ids).catch(function (e) {
        figma.ui.postMessage({ type: "error", text: String((e && e.message) || e) });
      });
    } else if (msg.type === "saveCfg") {   // 「发送到工作台」的连接设置,与资源批处理(batch)共用 budui_bridge
      if (figma.clientStorage) figma.clientStorage.setAsync("budui_bridge", msg.cfg);
    } else if (msg.type === "close") {
      figma.closePlugin();
    }
  };
  figma.on("selectionchange", sendSelection);
  sendSelection();
  if (figma.clientStorage) {
    figma.clientStorage.getAsync("budui_bridge").then(function (cfg) {
      figma.ui.postMessage({ type: "init", cfg: cfg || {}, file: figma.root.name });
    });
  }
}

// ================= 导入:把工作台工程(.budui.json)还原成 Figma 图层 =================
// 容器 → Frame(不填充),切图 → 矩形 + 图片填充(拉伸铺满,与工作台 / UGUI 一致),文字 → 可编辑文字(白名单字体,本机没有就用替补),
// 按钮 → Frame + 底图 + 文字;默认隐藏的节点导入为隐藏。每个节点的工作台信息(标识、点击、动效)存在 pluginData "budui" 里。
// 每个工程是目标页面上的一个分区(Section),里面每个界面一张 2436×1125 的画框;同名分区重新导入时先删掉旧的再建。
// 参考图(PNG)放进「参考图」分区。

var FONT_CHOICES = {
  Heavy: [["Source Han Sans CN", "Heavy"], ["Source Han Sans SC", "Heavy"], ["思源黑体 CN", "Heavy"], ["Noto Sans SC", "Black"], ["Inter", "Black"]],
  Medium: [["Source Han Sans CN", "Medium"], ["Source Han Sans SC", "Medium"], ["思源黑体 CN", "Medium"], ["Noto Sans SC", "Medium"], ["Inter", "Medium"]],
  Regular: [["Source Han Sans CN", "Regular"], ["Source Han Sans SC", "Regular"], ["思源黑体 CN", "Regular"], ["Noto Sans SC", "Regular"], ["Inter", "Regular"]],
  MontBlack: [["Montserrat", "Black"], ["Inter", "Black"]],
  MontBold: [["Montserrat", "Bold"], ["Inter", "Bold"]],
  MontMedium: [["Montserrat", "Medium"], ["Inter", "Medium"]]
};
var IMP = { page: null, fonts: {}, fallbacks: [], images: {}, nodes: 0 };

function impProgress(text) { figma.ui.postMessage({ type: "progress", text: text }); }

function hexRgb(hex) {
  var v = String(hex || "#ffffff").replace("#", "");
  if (v.length === 3) v = v[0] + v[0] + v[1] + v[1] + v[2] + v[2];
  return { r: parseInt(v.slice(0, 2), 16) / 255 || 0, g: parseInt(v.slice(2, 4), 16) / 255 || 0, b: parseInt(v.slice(4, 6), 16) / 255 || 0 };
}

async function prepareFonts() {
  var list = await figma.listAvailableFontsAsync(), have = {};
  list.forEach(function (f) { have[f.fontName.family + "|" + f.fontName.style] = true; });
  var keys = Object.keys(FONT_CHOICES);
  for (var i = 0; i < keys.length; i++) {
    var opts = FONT_CHOICES[keys[i]], pick = null;
    for (var j = 0; j < opts.length && !pick; j++) if (have[opts[j][0] + "|" + opts[j][1]]) pick = { family: opts[j][0], style: opts[j][1] };
    if (!pick) pick = { family: "Inter", style: "Regular" };
    if (pick.family !== opts[0][0]) IMP.fallbacks.push(keys[i] + " → " + pick.family + " " + pick.style);
    await figma.loadFontAsync(pick);
    IMP.fonts[keys[i]] = pick;
  }
}

async function targetPage(name) {
  var page = null;
  for (var i = 0; i < figma.root.children.length; i++) if (figma.root.children[i].name === name) page = figma.root.children[i];
  if (!page) { page = figma.createPage(); page.name = name; }
  await figma.setCurrentPageAsync(page);
  IMP.page = page;
  return page;
}

// 页面上已有内容的最下沿:新分区往下排,不压住别的东西
function pageBottom(page) {
  var y = 0;
  page.children.forEach(function (c) { y = Math.max(y, c.y + c.height); });
  return page.children.length ? y + 400 : 0;
}

function makeSection(page, name, w, h) {
  page.children.filter(function (c) { return c.name === name && (c.type === "SECTION" || c.type === "FRAME"); }).forEach(function (c) { c.remove(); });
  var s;
  if (typeof figma.createSection === "function") { s = figma.createSection(); s.resizeWithoutConstraints(w, h); }
  else { s = figma.createFrame(); s.fills = []; s.resize(w, h); }
  s.name = name; s.x = 0; s.y = pageBottom(page);
  page.appendChild(s);
  return s;
}

function imageFill(hash, keepAspect) {
  // CROP + 单位变换 = 整张图拉伸铺满节点框(工作台和 UGUI Image 的默认行为);保持比例的用 FIT
  return keepAspect ? { type: "IMAGE", imageHash: hash, scaleMode: "FIT" }
    : { type: "IMAGE", imageHash: hash, scaleMode: "CROP", imageTransform: [[1, 0, 0], [0, 1, 0]] };
}

function setBox(node, n) {
  node.x = n.x || 0; node.y = n.y || 0;
  var w = Math.max(0.01, n.w || 0.01), h = Math.max(0.01, n.h || 0.01);
  if (node.type === "TEXT") node.resize(w, h); else node.resize(w, h);
}

function tagNode(node, n) {
  node.setPluginData("budui", JSON.stringify({ id: n.id, type: n.type, key: n.key || "", clickable: !!(n.clickable || n.type === "button"),
    clickAction: n.clickAction || "", motion: n.motion || "none", motionDelay: n.motionDelay || 0, dynamic: !!n.dynamic, isClose: !!n.isClose }));
  if (n.hiddenByDefault) node.visible = false;
}

function makeText(txt, font, size, color, alpha, w, h, ah, av) {
  var t = figma.createText();
  t.fontName = IMP.fonts[font] || IMP.fonts.Regular;
  t.characters = String(txt == null ? "" : txt);
  t.fontSize = Math.max(1, size || 24);
  t.fills = [{ type: "SOLID", color: hexRgb(color) }];
  t.opacity = alpha == null ? 1 : alpha;
  t.textAutoResize = "NONE";
  t.textAlignHorizontal = ["LEFT", "CENTER", "RIGHT"][ah || 0] || "LEFT";
  t.textAlignVertical = ["TOP", "CENTER", "BOTTOM"][av || 0] || "TOP";
  t.resize(Math.max(1, w), Math.max(1, h));
  return t;
}

function buildNode(n, parent, assetHash) {
  var node;
  IMP.nodes++;
  if (n.type === "text") {
    node = makeText(n.text, n.font, n.fontSize, n.textColor, n.alpha, n.w, n.h, n.alignH, n.alignV);
    node.x = n.x || 0; node.y = n.y || 0;
  } else if (n.type === "image" && !(n.children && n.children.length)) {
    node = figma.createRectangle();
    setBox(node, n);
    var h = n.spriteId && assetHash[n.spriteId];
    node.fills = h ? [imageFill(h, n.preserveAspect)] : [{ type: "SOLID", color: hexRgb(n.color), opacity: n.alpha == null ? 1 : n.alpha }];
    if (h && n.alpha != null) node.opacity = n.alpha;
  } else {
    node = figma.createFrame();
    setBox(node, n);
    node.clipsContent = !!(n.clip || n.scroll);
    var hh = (n.type === "image" || n.type === "button") && n.spriteId && assetHash[n.spriteId];
    node.fills = hh ? [imageFill(hh, n.preserveAspect)] : n.type === "button" && !n.spriteId ? [{ type: "SOLID", color: hexRgb(n.color) }] : [];
    if ((n.type === "image" || n.type === "button") && n.alpha != null) node.opacity = n.alpha;
    (n.children || []).forEach(function (c) { buildNode(c, node, assetHash); });
    if (n.type === "button" && n.label) {
      var lab = makeText(n.label, n.labelFont, n.labelSize, n.labelColor, 1, n.w, n.h, 1, 1);
      lab.name = "Label"; node.appendChild(lab);
    }
  }
  node.name = n.name || n.type;
  tagNode(node, n);
  parent.appendChild(node);
  return node;
}

var GAP = 200, PER_ROW = 4, STAGE_BG = { r: 0.094, g: 0.086, b: 0.133 };

function importProject(p) {
  var assetHash = {}, ids = Object.keys(p.assets || {});
  ids.forEach(function (id, i) {
    if (i % 10 === 0) impProgress("「" + p.title + "」:图片 " + (i + 1) + "/" + ids.length);
    assetHash[id] = figma.createImage(figma.base64Decode(p.assets[id])).hash;
  });
  var pages = p.pages || [], rows = Math.ceil(pages.length / PER_ROW) || 1;
  var cols = Math.min(PER_ROW, pages.length) || 1;
  var sec = makeSection(IMP.page, p.title, cols * STAGE_W + (cols + 1) * GAP, rows * (STAGE_H + GAP) + GAP + 120);
  pages.forEach(function (pg, i) {
    impProgress("「" + p.title + "」:界面 " + (i + 1) + "/" + pages.length + " " + pg.name);
    var f = figma.createFrame();
    f.name = (i === 0 ? "【主页】" : pg.kind === "popup" ? "【弹窗】" : "【页面】") + pg.name;
    f.resize(STAGE_W, STAGE_H);
    f.fills = [{ type: "SOLID", color: STAGE_BG }];
    f.clipsContent = true;
    f.x = GAP + (i % PER_ROW) * (STAGE_W + GAP); f.y = GAP + 120 + Math.floor(i / PER_ROW) * (STAGE_H + GAP);
    f.setPluginData("budui", JSON.stringify({ module: p.module, pageId: pg.id, kind: pg.kind, figmaId: pg.figmaId || "" }));
    (pg.nodes || []).forEach(function (n) { buildNode(n, f, assetHash); });
    sec.appendChild(f);
  });
  return sec;
}

function importImages(title, imgs) {
  if (!imgs.length) return null;
  var x = GAP, rowH = 0, y = GAP, maxW = 0, MAXROW = 9000, placed = [];
  imgs.forEach(function (im) {
    if (x > GAP && x + im.w > MAXROW) { x = GAP; y += rowH + GAP + 80; rowH = 0; }
    placed.push({ im: im, x: x, y: y }); x += im.w + GAP; rowH = Math.max(rowH, im.h); maxW = Math.max(maxW, x);
  });
  var sec = makeSection(IMP.page, title, maxW, y + rowH + GAP + 80);
  placed.forEach(function (p) {
    var cap = makeText(p.im.name, "Medium", 48, "#ffffff", 1, Math.max(400, p.im.w), 64, 0, 0);
    cap.x = p.x; cap.y = p.y; sec.appendChild(cap);
    var r = figma.createRectangle();
    r.name = p.im.name; r.resize(p.im.w, p.im.h); r.x = p.x; r.y = p.y + 80;
    r.fills = [imageFill(figma.createImage(figma.base64Decode(p.im.b64)).hash, false)];
    sec.appendChild(r);
  });
  return sec;
}

function startImport(html) {
  figma.showUI(html, { width: 420, height: 560, themeColors: true });
  figma.ui.postMessage({ type: "init", file: figma.root.name });
  var made = [];
  figma.ui.onmessage = function (msg) {
    var job = null;
    if (msg.type === "begin") job = (async function () {
      IMP.fallbacks = []; IMP.nodes = 0; made = [];
      await prepareFonts();
      await targetPage(msg.page || "lijixiantest");
    })();
    else if (msg.type === "project") job = (async function () { made.push(importProject(msg.project)); })();
    else if (msg.type === "images") job = (async function () { var s = importImages(msg.title, msg.images); if (s) made.push(s); })();
    else if (msg.type === "end") job = (async function () {
      figma.viewport.scrollAndZoomIntoView(made.length ? made : IMP.page.children);
      figma.ui.postMessage({ type: "done", nodes: IMP.nodes, sections: made.map(function (s) { return s.name; }), fallbacks: IMP.fallbacks, page: IMP.page.name });
    })();
    else if (msg.type === "close") { figma.closePlugin(); return; }
    if (job) job.then(function () { figma.ui.postMessage({ type: "ack", id: msg.id }); }, function (e) {
      figma.ui.postMessage({ type: "error", id: msg.id, text: String((e && e.message) || e) });
    });
  };
}

// ================= 资源批处理:选中的资源 → 工作台中转箱;工作台处理完的新切图 → 摆回 Figma =================
// 选中的每个节点 = 一个资源(如「头像框_40」):它的直接子图层各导出一张切图(带相对资源左上角的位置),没有子图层就把它自己当一张切图。
// 网络请求都在 batch.html 里发(只能访问本机 localhost:8791,见 manifest 的 devAllowedDomains),这里只负责读写图层。
function pngSize(bytes) {   // PNG 头里的宽高(IHDR,大端)
  var r = function (o) { return ((bytes[o] << 24) | (bytes[o + 1] << 16) | (bytes[o + 2] << 8) | bytes[o + 3]) >>> 0; };
  return { w: r(16), h: r(20) };
}

function boxOf(n) {
  return n.absoluteRenderBounds || n.absoluteBoundingBox || { x: n.x, y: n.y, width: n.width, height: n.height };
}

async function collectAssets() {
  var sel = figma.currentPage.selection;
  if (!sel.length) throw new Error("先在画布上选中要处理的资源(每个资源一个画框 / 分组)");
  var assets = [];
  for (var i = 0; i < sel.length; i++) {
    var a = sel[i], ab = boxOf(a);
    var parts = ("children" in a && a.children.length) ? a.children.filter(function (c) { return c.visible; }) : [a];
    var preview = await a.exportAsync({ format: "PNG", constraint: { type: "SCALE", value: 1 } });
    var slices = [];
    for (var k = 0; k < parts.length; k++) {
      var p = parts[k];
      figma.ui.postMessage({ type: "progress", text: "导出 " + a.name + " / " + p.name + "(" + (k + 1) + "/" + parts.length + ")" });
      var bytes = await p.exportAsync({ format: "PNG", constraint: { type: "SCALE", value: 1 } });
      var sz = pngSize(bytes), pb = boxOf(p);
      slices.push({ name: p.name, nodeId: p.id, x: Math.round(pb.x - ab.x), y: Math.round(pb.y - ab.y), w: sz.w, h: sz.h, png: figma.base64Encode(bytes) });
    }
    var psz = pngSize(preview);
    assets.push({ name: a.name, nodeId: a.id, w: psz.w, h: psz.h, preview: figma.base64Encode(preview), slices: slices });
  }
  return assets;
}

async function placeResults(result) {
  var made = [];
  for (var i = 0; i < result.assets.length; i++) {
    var a = result.assets[i];
    var src = a.nodeId ? await figma.getNodeByIdAsync(a.nodeId) : null;
    var f = figma.createFrame();
    f.name = a.name + " · " + result.name; f.resize(Math.max(1, a.w), Math.max(1, a.h)); f.fills = []; f.clipsContent = false;
    var parent = src && src.parent && src.parent.type !== "DOCUMENT" ? src.parent : figma.currentPage;
    parent.appendChild(f);
    if (src) { f.x = src.x + src.width + 60; f.y = src.y; }
    else { f.x = figma.viewport.center.x; f.y = figma.viewport.center.y + i * (a.h + 60); }
    for (var k = 0; k < a.slices.length; k++) {
      var s = a.slices[k], r = figma.createRectangle();
      r.name = s.name + (s.isNew ? "" : "(原图)"); r.resize(Math.max(1, s.w), Math.max(1, s.h)); r.x = s.x; r.y = s.y;
      r.fills = [{ type: "IMAGE", scaleMode: "FILL", imageHash: figma.createImage(figma.base64Decode(s.png)).hash }];
      f.appendChild(r);
    }
    made.push(f);
  }
  if (made.length) { figma.currentPage.selection = made; figma.viewport.scrollAndZoomIntoView(made); }
  return made.length;
}

function startBatch(html) {
  figma.showUI(html, { width: 400, height: 580, themeColors: true });
  var sendSel = function () {
    figma.ui.postMessage({ type: "selection", items: figma.currentPage.selection.map(function (n) {
      return { name: n.name, w: Math.round(n.width), h: Math.round(n.height), parts: ("children" in n) ? n.children.length : 0 };
    }) });
  };
  figma.clientStorage.getAsync("budui_bridge").then(function (cfg) {
    figma.ui.postMessage({ type: "init", cfg: cfg || {}, file: figma.root.name }); sendSel();
  });
  figma.on("selectionchange", sendSel);
  figma.ui.onmessage = function (msg) {
    var job = null;
    if (msg.type === "saveCfg") job = figma.clientStorage.setAsync("budui_bridge", msg.cfg).then(function () { return {}; });
    else if (msg.type === "collect") job = collectAssets().then(function (assets) { return { assets: assets, file: figma.root.name, page: figma.currentPage.name }; });
    else if (msg.type === "place") job = placeResults(msg.result).then(function (n) { return { frames: n }; });
    else if (msg.type === "close") { figma.closePlugin(); return; }
    if (job) job.then(function (data) { figma.ui.postMessage({ type: "ack", id: msg.id, data: data }); }, function (e) {
      figma.ui.postMessage({ type: "error", id: msg.id, text: String((e && e.message) || e) });
    });
  };
}
