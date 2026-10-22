/* ==========================================================================
 * 赛博女友 CyberGirlfriend —— 前端 SPA（Vue 3 全局构建 / 零构建 / 零第三方库）
 * --------------------------------------------------------------------------
 * 结构分区：
 *   1. 常量与字典
 *   2. 通用工具（fetch 封装 / SSE 解析 / 格式化）
 *   3. 应用状态（reactive）
 *   4. 数据加载与业务动作
 *   5. hash 路由
 *   6. 视图模板
 *   7. 应用装配
 * 所有接口路径均与后端 backend/app/api/*.py 严格对齐。
 * ========================================================================== */
(function () {
  "use strict";

  var Vue = window.Vue;
  if (!Vue || !Vue.createApp) {
    var box = document.getElementById("app");
    if (box) {
      box.innerHTML =
        '<div class="boot">Vue 运行时加载失败：请确认 ./vendor/vue.global.prod.js 存在。</div>';
    }
    return;
  }

  var reactive = Vue.reactive;
  var computed = Vue.computed;
  var watch = Vue.watch;
  var nextTick = Vue.nextTick;

  /* ======================================================================
   * 1. 常量与字典
   * ==================================================================== */
  var NAV_ITEMS = [
    { key: "wall", icon: "🏠", label: "角色墙" },
    { key: "import", icon: "📥", label: "导入向导" },
    { key: "chat", icon: "💬", label: "聊天" },
    { key: "persona", icon: "🎭", label: "人设编辑" },
    { key: "cards", icon: "🎴", label: "角色卡" },
    { key: "lore", icon: "📖", label: "世界书" },
    { key: "memory", icon: "🧠", label: "记忆库" },
    { key: "backup", icon: "🗄", label: "备份" },
    { key: "settings", icon: "⚙️", label: "设置" }
  ];

  /* 世界书注入位置字典（与后端 position 枚举严格一致） */
  var LORE_POSITIONS = ["before_char", "after_char", "at_depth"];
  var LORE_POSITION_LABELS = {
    before_char: "角色设定前",
    after_char: "角色设定后",
    at_depth: "对话深度"
  };

  /* 备份导入策略（与后端 VALID_STRATEGIES 严格一致） */
  var BACKUP_STRATEGIES = ["merge_by_id", "merge_by_name", "skip_duplicates"];
  var BACKUP_STRATEGY_LABELS = {
    merge_by_id: "按 ID 合并（同 ID 覆盖更新）",
    merge_by_name: "按名称合并（同名视为同一角色）",
    skip_duplicates: "跳过重复（已存在则不导入）"
  };

  var SLIDER_KEYS = ["gentle", "tsundere", "sharp", "clingy", "proactive"];
  var SLIDER_LABELS = {
    gentle: "温柔",
    tsundere: "傲娇",
    sharp: "毒舌",
    clingy: "黏人",
    proactive: "主动"
  };
  var MEMORY_KINDS = ["fact", "preference", "event", "promise"];
  var KIND_LABELS = { fact: "事实", preference: "偏好", event: "事件", promise: "约定" };
  var RELATIONS = ["女友", "老婆", "闺蜜", "自定义"];
  var PROVIDERS = ["mock", "openai", "ollama"];
  var PROVIDER_LABELS = {
    mock: "本地演示（mock，无需 Key）",
    openai: "OpenAI 兼容接口",
    ollama: "本地 Ollama"
  };
  var EMOJI_CHOICES = ["🌸", "🌙", "🍬", "💫", "🐱", "🦊", "🌿", "☕", "🎀", "🧊", "🔥", "🫧"];

  var WIZARD_STEPS = ["上传文件", "解析预览", "TA 是谁", "生成人格"];
  var FORMAT_HELP = [
    {
      name: "微信导出 txt",
      sample: "张三 2024-03-01 21:04:11\n今天好累啊\n\n我 2024-03-01 21:05:02\n辛苦啦，早点睡",
      tip: "「发言人 时间」独占一行，消息在下一行；支持「我」「你」为发言人。"
    },
    {
      name: "QQ 导出 txt",
      sample: "2024-03-01 21:04:11 张三(10001)\n今天好累啊\n\n2024-03-01 21:05:02 我(10002)\n辛苦啦",
      tip: "「时间 昵称(QQ号)」独占一行，消息在下一行。"
    },
    {
      name: "Telegram json",
      sample: '{ "name": "Chat", "messages": [ { "from": "张三", "text": "今天好累啊", "date": "2024-03-01T21:04:11" } ] }',
      tip: "读取 messages 数组，取 from / text / date 字段；也兼容通用 json 数组。"
    },
    {
      name: "通用 csv",
      sample: "speaker,content,timestamp\n张三,今天好累啊,2024-03-01 21:04:11\n我,辛苦啦,2024-03-01 21:05:02",
      tip: "首行表头需含 speaker/发言人 与 content/内容 两列，时间列可选。"
    }
  ];

  function emptySliderSet() {
    var sliders = {};
    SLIDER_KEYS.forEach(function (key) {
      sliders[key] = 50;
    });
    return sliders;
  }

  function emptyPersonaForm() {
    return {
      id: null,
      name: "",
      avatar_emoji: "🌸",
      relation: "女友",
      nickname_for_user: "你",
      sliders: { gentle: 70, tsundere: 20, sharp: 20, clingy: 45, proactive: 50 },
      greeting: "",
      phrases: "",
      description: "",
      sample_dialogues: [],
      persona_card: {},
      source: "manual",
      saving: false
    };
  }

  function emptyMemForm() {
    return { id: null, persona_id: null, content: "", kind: "fact", importance: 0.6 };
  }

  /* ======================================================================
   * 2. 通用工具
   * ==================================================================== */
  function buildQuery(params) {
    if (!params) return "";
    var pairs = [];
    Object.keys(params).forEach(function (key) {
      var value = params[key];
      if (value === undefined || value === null || value === "") return;
      pairs.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
    });
    return pairs.length ? "?" + pairs.join("&") : "";
  }

  function extractError(data, res) {
    var detail = data && data.detail !== undefined ? data.detail : data;
    if (Array.isArray(detail)) {
      detail = detail
        .map(function (item) {
          return item && item.msg ? item.msg : JSON.stringify(item);
        })
        .join("；");
    }
    if (detail && typeof detail === "object") {
      try {
        detail = JSON.stringify(detail);
      } catch (err) {
        detail = String(detail);
      }
    }
    if (!detail) {
      detail = "HTTP " + res.status + " " + (res.statusText || "");
    }
    return String(detail);
  }

  function request(method, path, body, params) {
    var url = path + buildQuery(params);
    var options = { method: method, headers: {} };
    if (body !== undefined && body !== null) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(url, options).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        if (text) {
          try {
            data = JSON.parse(text);
          } catch (err) {
            data = text;
          }
        }
        if (!res.ok) {
          throw new Error(extractError(data, res));
        }
        return data;
      });
    });
  }

  var Api = {
    get: function (path, params) {
      return request("GET", path, null, params);
    },
    post: function (path, body, params) {
      return request("POST", path, body, params);
    },
    put: function (path, body) {
      return request("PUT", path, body, null);
    },
    del: function (path) {
      return request("DELETE", path, null, null);
    }
  };

  /** 严格按后端 to_sse() 的报文格式解析：event: <type>\ndata: <json>\n\n */
  function readSse(response, onEvent) {
    if (!response.body || !response.body.getReader) {
      return response.text().then(function (text) {
        splitSse(text).forEach(onEvent);
      });
    }
    var reader = response.body.getReader();
    var decoder = new TextDecoder("utf-8");
    var buffer = "";

    function pump() {
      return reader.read().then(function (result) {
        if (result.done) {
          if (buffer.trim()) {
            splitSse(buffer).forEach(onEvent);
          }
          return;
        }
        buffer += decoder.decode(result.value, { stream: true });
        var cut = buffer.lastIndexOf("\n\n");
        if (cut >= 0) {
          var block = buffer.slice(0, cut);
          buffer = buffer.slice(cut + 2);
          splitSse(block).forEach(onEvent);
        }
        return pump();
      });
    }
    return pump();
  }

  function splitSse(chunk) {
    var events = [];
    String(chunk || "")
      .split(/\n\n/)
      .forEach(function (block) {
        var type = "message";
        var dataLines = [];
        block.split("\n").forEach(function (line) {
          if (line.indexOf("event:") === 0) {
            type = line.slice(6).trim();
          } else if (line.indexOf("data:") === 0) {
            dataLines.push(line.slice(5).trim());
          }
        });
        if (!dataLines.length) return;
        var payload = dataLines.join("\n");
        try {
          var parsed = JSON.parse(payload);
          if (!parsed.type) parsed.type = type;
          events.push(parsed);
        } catch (err) {
          events.push({ type: type, text: payload });
        }
      });
    return events;
  }

  function fmtTime(value) {
    if (!value) return "—";
    var text = String(value).replace("T", " ");
    return text.length >= 16 ? text.slice(0, 16) : text;
  }

  function fmtImportance(value) {
    var number = Number(value);
    return isNaN(number) ? "0.60" : number.toFixed(2);
  }

  function kindLabel(kind) {
    return KIND_LABELS[kind] || kind || "事实";
  }

  function providerLabel(provider) {
    return PROVIDER_LABELS[provider] || provider;
  }

  function byUpdatedDesc(a, b) {
    var ta = a.updated_at ? Date.parse(String(a.updated_at).replace(" ", "T")) : 0;
    var tb = b.updated_at ? Date.parse(String(b.updated_at).replace(" ", "T")) : 0;
    if (isNaN(ta)) ta = 0;
    if (isNaN(tb)) tb = 0;
    if (tb !== ta) return tb - ta;
    return (b.id || 0) - (a.id || 0);
  }

  function responseErrorMessage(err) {
    if (!err) return "未知错误";
    return err.message || String(err);
  }

  function pad2(value) {
    var number = Number(value) || 0;
    return (number < 10 ? "0" : "") + number;
  }

  /** 消息时间 HH:mm（后端 ISO 字符串 / 时间戳 / Date 都可） */
  function fmtClock(value) {
    if (!value) return "";
    var dt;
    if (value instanceof Date) {
      dt = value;
    } else if (typeof value === "number") {
      dt = new Date(value);
    } else {
      var raw = String(value).trim();
      dt = new Date(raw.indexOf("T") >= 0 ? raw : raw.replace(" ", "T"));
      if (isNaN(dt.getTime())) dt = new Date(raw.replace(/-/g, "/"));
    }
    if (!dt || isNaN(dt.getTime())) return "";
    return pad2(dt.getHours()) + ":" + pad2(dt.getMinutes());
  }

  function dateStamp() {
    var now = new Date();
    return (
      "" + now.getFullYear() + pad2(now.getMonth() + 1) + pad2(now.getDate()) + "-" + pad2(now.getHours()) + pad2(now.getMinutes())
    );
  }

  function safeFileName(name, fallback) {
    var text = String(name || "")
      .replace(/[\\/:*?"<>|]+/g, "_")
      .replace(/\s+/g, "_")
      .replace(/^_+|_+$/g, "");
    return text || fallback || "cyber-girlfriend";
  }

  /* ---------------- 剪贴板 ---------------- */
  function copyText(text, label) {
    var value = String(text === undefined || text === null ? "" : text);
    function done() {
      toast("success", (label || "内容") + "已复制");
    }
    function fallback() {
      try {
        var area = document.createElement("textarea");
        area.value = value;
        area.setAttribute("readonly", "readonly");
        area.style.position = "fixed";
        area.style.top = "-2000px";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        var ok = document.execCommand("copy");
        document.body.removeChild(area);
        if (ok) {
          done();
        } else {
          toast("error", "复制失败，请手动选择文本");
        }
      } catch (err) {
        toast("error", "复制失败，请手动选择文本");
      }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(done).catch(fallback);
      return;
    }
    fallback();
  }

  /* ---------------- 下载 ---------------- */
  function downloadBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1500);
  }

  /** 走 fetch 拿二进制再触发下载，便于统一处理 4xx/5xx 错误 */
  function downloadFromApi(path, filename) {
    return fetch(path, { method: "GET" }).then(function (res) {
      if (!res.ok) {
        return res.text().then(function (text) {
          var data = null;
          if (text) {
            try {
              data = JSON.parse(text);
            } catch (err) {
              data = text;
            }
          }
          throw new Error(extractError(data, res));
        });
      }
      return res.blob().then(function (blob) {
        downloadBlob(blob, filename);
      });
    });
  }

  /** multipart 上传（字段名固定为 file） */
  function uploadFormData(path, file) {
    var payload = new FormData();
    payload.append("file", file);
    return fetch(path, { method: "POST", body: payload }).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        if (text) {
          try {
            data = JSON.parse(text);
          } catch (err) {
            data = text;
          }
        }
        if (!res.ok) {
          throw new Error(extractError(data, res));
        }
        return data;
      });
    });
  }

  /* ======================================================================
   * 2.1 Markdown 轻量渲染器（自实现，零外部依赖）
   *
   * 安全模型：**先对原文做 HTML 转义，再按规则替换为受控标签**。
   * 任何用户 / 模型输入中的 < > & " ' 都会先变成实体，因此产出的
   * HTML 只可能包含本文件显式拼接的标签，不存在注入执行路径。
   * 支持：围栏代码块（带语言标签 + 复制按钮）、行内代码、加粗、斜体、
   *      删除线、引用、有序 / 无序列表、链接（白名单协议）、标题、分割线。
   * ==================================================================== */
  var MD_CACHE = {};
  var MD_CACHE_ORDER = [];
  var MD_CACHE_LIMIT = 400;

  function escapeHtml(text) {
    return String(text === undefined || text === null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /** 链接协议白名单：仅 http(s) / mailto / 站内相对路径，杜绝 javascript: 等伪协议 */
  function isSafeUrl(url) {
    var value = String(url || "").trim();
    if (!value) return false;
    if (/^(https?:\/\/|mailto:)/i.test(value)) return true;
    if (/^(\/|#|\.\/)/.test(value)) return true;
    return false;
  }

  function renderInline(raw) {
    var codes = [];
    var text = escapeHtml(raw);
    // 行内代码先抽出占位，避免其中内容被后续强调规则二次改写
    text = text.replace(/`([^`\n]+)`/g, function (match, code) {
      codes.push(code);
      return "\u0001" + (codes.length - 1) + "\u0001";
    });
    // 链接：label 已是转义文本，地址需过白名单
    text = text.replace(/\[([^\]\n]+)\]\(([^()\s]+)\)/g, function (match, label, url) {
      var href = String(url).replace(/&amp;/g, "&");
      if (!isSafeUrl(href)) {
        return label + " (" + url + ")";
      }
      return (
        '<a class="md-link" href="' + escapeHtml(href) + '" target="_blank" rel="noopener noreferrer">' + label + "</a>"
      );
    });
    text = text.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
    text = text.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
    text = text.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
    text = text.replace(/\u0001(\d+)\u0001/g, function (match, index) {
      return '<code class="md-inline">' + (codes[Number(index)] || "") + "</code>";
    });
    return text;
  }

  function codeBlockHtml(lang, code) {
    var label = lang ? escapeHtml(lang) : "代码";
    return (
      '<div class="md-code">' +
      '<div class="md-code-bar"><span class="md-code-lang">' +
      label +
      "</span>" +
      '<button type="button" class="md-code-copy" data-copy-block="1">复制</button>' +
      "</div>" +
      "<pre><code>" +
      escapeHtml(code) +
      "</code></pre>" +
      "</div>"
    );
  }

  function renderMarkdown(source) {
    var text = String(source === undefined || source === null ? "" : source).replace(/\r\n?/g, "\n");
    if (!text) return "";
    if (MD_CACHE[text] !== undefined) return MD_CACHE[text];

    var lines = text.split("\n");
    var html = [];
    var paragraph = [];
    var listItems = [];
    var listType = "";
    var quoteLines = [];

    function flushParagraph() {
      if (!paragraph.length) return;
      html.push('<p class="md-p">' + paragraph.join("<br>") + "</p>");
      paragraph = [];
    }
    function flushList() {
      if (!listItems.length) return;
      var tag = listType === "ol" ? "ol" : "ul";
      html.push("<" + tag + ' class="md-list">' + listItems.join("") + "</" + tag + ">");
      listItems = [];
      listType = "";
    }
    function flushQuote() {
      if (!quoteLines.length) return;
      html.push('<blockquote class="md-quote">' + quoteLines.join("<br>") + "</blockquote>");
      quoteLines = [];
    }
    function flushAll() {
      flushParagraph();
      flushList();
      flushQuote();
    }

    var index = 0;
    while (index < lines.length) {
      var line = lines[index];
      var trimmed = line.trim();

      /* 围栏代码块（含未闭合容错：一直取到文末） */
      var fence = trimmed.match(/^```([^`]*)$/);
      if (fence) {
        flushAll();
        var lang = String(fence[1] || "").trim();
        var buffer = [];
        index += 1;
        while (index < lines.length && !/^```\s*$/.test(lines[index].trim())) {
          buffer.push(lines[index]);
          index += 1;
        }
        index += 1;
        html.push(codeBlockHtml(lang, buffer.join("\n")));
        continue;
      }

      if (!trimmed) {
        flushAll();
        index += 1;
        continue;
      }

      var heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        flushAll();
        var level = Math.min(6, Math.max(3, heading[1].length));
        html.push('<div class="md-h md-h' + level + '">' + renderInline(heading[2]) + "</div>");
        index += 1;
        continue;
      }

      if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
        flushAll();
        html.push('<hr class="md-hr" />');
        index += 1;
        continue;
      }

      if (/^>\s?/.test(trimmed)) {
        flushParagraph();
        flushList();
        quoteLines.push(renderInline(trimmed.replace(/^>\s?/, "")));
        index += 1;
        continue;
      }

      var ordered = trimmed.match(/^(\d+)[.)]\s+(.*)$/);
      var bullet = trimmed.match(/^[-*+]\s+(.*)$/);
      if (ordered || bullet) {
        flushParagraph();
        flushQuote();
        var type = ordered ? "ol" : "ul";
        if (listType && listType !== type) flushList();
        listType = type;
        listItems.push("<li>" + renderInline(ordered ? ordered[2] : bullet[1]) + "</li>");
        index += 1;
        continue;
      }

      flushList();
      flushQuote();
      paragraph.push(renderInline(line));
      index += 1;
    }
    flushAll();

    var output = html.join("");
    MD_CACHE[text] = output;
    MD_CACHE_ORDER.push(text);
    if (MD_CACHE_ORDER.length > MD_CACHE_LIMIT) {
      var oldest = MD_CACHE_ORDER.shift();
      delete MD_CACHE[oldest];
    }
    return output;
  }

  /* ---------------- 脱敏统计读值（导入批次 / 角色卡摘要通用） ---------------- */
  function desensStats(payload) {
    return (payload && payload.desensitize) || {};
  }

  function desensEnabled(payload) {
    var stats = desensStats(payload);
    if (stats.enabled === undefined || stats.enabled === null) {
      return payload && payload.desensitize_enabled !== false;
    }
    return stats.enabled !== false;
  }

  function desensCounts(payload) {
    var stats = desensStats(payload);
    return stats.counts_labeled || stats.counts || {};
  }

  function desensTotal(payload) {
    return Number(desensStats(payload).total_masked || 0);
  }

  function desensDropped(payload) {
    return Number(desensStats(payload).dropped_messages || 0);
  }

  function desensKeywords(payload) {
    return desensStats(payload).dropped_keywords || [];
  }

  function desensHint(payload) {
    if (!desensEnabled(payload)) {
      return "脱敏已关闭：手机号 / 身份证等原文会直接进入人格提取";
    }
    return "已自动替换手机号、身份证、邮箱、银行卡、链接、IP、QQ 号，命中黑名单的消息整条丢弃";
  }

  /* 脱敏类别中英对照（后端 counts 的键名可能是拼音 / 英文，做兜底映射） */
  var DESENS_LABELS = {
    phone: "手机号",
    mobile: "手机号",
    id_card: "身份证",
    idcard: "身份证",
    email: "邮箱",
    bank_card: "银行卡",
    bankcard: "银行卡",
    url: "链接",
    link: "链接",
    ip: "IP 地址",
    qq: "QQ 号",
    wechat: "微信号",
    address: "地址",
    name: "姓名",
    other: "其他"
  };

  /** 把 counts / counts_labeled 转成可渲染的 [{key,label,count}]，并按命中数降序 */
  function desensRows(payload) {
    var counts = desensCounts(payload) || {};
    var rows = [];
    Object.keys(counts).forEach(function (key) {
      var count = Number(counts[key] || 0);
      if (count > 0) {
        rows.push({ key: key, label: DESENS_LABELS[key] || key, count: count });
      }
    });
    rows.sort(function (a, b) {
      return b.count - a.count;
    });
    return rows;
  }

  function desensTotalText(payload) {
    if (!desensEnabled(payload)) {
      return "脱敏已关闭，原文将完整保留";
    }
    var total = desensTotal(payload);
    if (!total) {
      total = desensRows(payload).reduce(function (sum, row) {
        return sum + row.count;
      }, 0);
    }
    if (!total) return "未检测到敏感信息，原文保持完整";
    return "共脱敏 " + total + " 处敏感信息";
  }

  /** 丢弃信息文案：整条丢弃的消息数 + 命中黑名单的关键词数 */
  function desensDropText(payload) {
    var messages = Number(desensStats(payload).dropped_messages || 0);
    var keywords = desensKeywords(payload);
    var keywordCount = keywords && keywords.length !== undefined ? keywords.length : Number(keywords || 0);
    if (!messages && !keywordCount) return "没有消息因敏感词被丢弃";
    return "丢弃 " + messages + " 条消息 · " + keywordCount + " 处敏感词";
  }

  function lorePosLabel(position) {
    return LORE_POSITION_LABELS[position] || position || "角色设定前";
  }

  /** 代码块复制按钮：通过事件委托处理 v-html 内部按钮的点击 */
  function onMarkdownClick(event) {
    var node = event && event.target;
    if (!node || !node.closest) return;
    var button = node.closest("[data-copy-block]");
    if (!button) return;
    var box = button.closest(".md-code");
    var code = box ? box.querySelector("code") : null;
    copyText(code ? code.textContent : "", "代码");
  }

  /* ======================================================================
   * 3. 应用状态
   * ==================================================================== */
  var state = reactive({
    ready: false,
    view: "wall",
    meta: {},
    settings: {},
    personas: [],

    /* 角色墙 / 新建人格弹窗 */
    createVisible: false,
    createSaving: false,
    createForm: { name: "", avatar_emoji: "🌸", relation: "女友", nickname_for_user: "你", greeting: "" },

    /* 导入向导 */
    wizard: {
      step: 1,
      uploading: false,
      batch: null,
      speaker: "",
      name: "",
      emoji: "💫",
      relation: "女友",
      nickname: "你",
      generating: false,
      result: null
    },

    /* 聊天 */
    activePersonaId: null,
    activeSessionId: null,
    sessions: [],
    messages: [],
    inputText: "",
    streaming: false,
    streamError: "",
    notices: [],
    memorySideOpen: false,
    chatMemories: [],

    /* 反馈改写弹窗 */
    rewriteVisible: false,
    rewriteMessageId: null,
    rewriteText: "",
    rewriteSaving: false,

    /* 人设编辑 */
    personaForm: emptyPersonaForm(),
    previewPrompt: "",
    previewLoading: false,

    /* 记忆库 */
    memories: [],
    memFilterPersonaId: 0,
    memEditId: null,
    memForm: emptyMemForm(),
    memTestPersonaId: null,
    memTestQuery: "",
    memTestResult: null,
    memTestLoading: false,

    /* 消息编辑后重发 */
    editVisible: false,
    editTarget: -1,
    editText: "",

    /* 角色卡 */
    cards: {
      parseResult: null,
      parseIsImport: false,
      pending: null,
      parsing: false,
      importing: false,
      exporting: "",
      personaId: null
    },

    /* 世界书 */
    lore: {
      personaId: null,
      entries: [],
      loading: false,
      editing: null,
      editVisible: false,
      saving: false,
      previewText: "",
      previewBudget: 0,
      previewLoading: false,
      preview: null
    },

    /* 备份 */
    backup: {
      exporting: false,
      importing: false,
      strategy: "merge_by_id",
      result: null
    },

    /* 导入批次 */
    batches: [],
    batchesLoading: false,

    /* 设置 */
    settingsForm: null,
    settingsSaving: false,
    settingsSaved: false,

    /* 全局 */
    toasts: [],
    loading: false
  });

  var toastSeq = 0;
  var chatAbort = null;
  var previewTimer = null;
  var pendingCardFile = null;

  /* ======================================================================
   * 4. 数据加载与业务动作
   * ==================================================================== */
  function toast(type, text) {
    toastSeq += 1;
    var id = toastSeq;
    state.toasts.push({ id: id, type: type, text: text });
    setTimeout(function () {
      var index = state.toasts.findIndex(function (item) {
        return item.id === id;
      });
      if (index >= 0) state.toasts.splice(index, 1);
    }, 3600);
  }

  function toastError(err) {
    toast("error", responseErrorMessage(err));
  }

  function scrollToBottom() {
    nextTick(function () {
      var box = document.querySelector(".msgs");
      if (box) box.scrollTop = box.scrollHeight;
    });
  }

  /* ---------------- 人格 ---------------- */
  function loadPersonas() {
    return Api.get("/api/personas")
      .then(function (list) {
        state.personas = list || [];
        if (state.personas.length && !state.memTestPersonaId) {
          state.memTestPersonaId = state.personas[0].id;
        }
        if (state.personas.length && !state.memForm.persona_id) {
          state.memForm.persona_id = state.personas[0].id;
        }
        ensurePersonaPick();
        return state.personas;
      })
      .catch(function (err) {
        toastError(err);
        return [];
      });
  }

  function openCreatePersona() {
    state.createForm = { name: "", avatar_emoji: "🌸", relation: "女友", nickname_for_user: "你", greeting: "" };
    state.createVisible = true;
  }

  function submitCreatePersona() {
    var form = state.createForm;
    if (!(form.name || "").trim()) {
      toast("warn", "请填写人格名称");
      return;
    }
    state.createSaving = true;
    Api.post("/api/personas", {
      name: form.name.trim(),
      avatar_emoji: form.avatar_emoji || "🌸",
      relation: form.relation || "女友",
      nickname_for_user: form.nickname_for_user || "你",
      greeting: form.greeting || "",
      sliders: emptySliderSet(),
      persona_card: { nickname: form.name.trim(), sample_dialogues: [], top_phrases: [] },
      source: "manual"
    })
      .then(function (persona) {
        state.createVisible = false;
        toast("success", "人格「" + persona.name + "」已创建");
        return loadPersonas();
      })
      .catch(toastError)
      .then(function () {
        state.createSaving = false;
      });
  }

  /* ---------------- 导入向导 ---------------- */
  function resetWizard() {
    state.wizard = {
      step: 1,
      uploading: false,
      batch: null,
      speaker: "",
      name: "",
      emoji: "💫",
      relation: "女友",
      nickname: "你",
      generating: false,
      result: null
    };
  }

  function onFileChange(event) {
    var file = event.target.files && event.target.files[0];
    if (!file) return;
    var data = new FormData();
    data.append("file", file);
    state.wizard.uploading = true;
    fetch("/api/import/upload", { method: "POST", body: data })
      .then(function (res) {
        return res.text().then(function (text) {
          var json = null;
          if (text) {
            try {
              json = JSON.parse(text);
            } catch (err) {
              json = text;
            }
          }
          if (!res.ok) throw new Error(extractError(json, res));
          return json;
        });
      })
      .then(function (batch) {
        state.wizard.batch = batch;
        state.wizard.speaker = "";
        state.wizard.step = 2;
        toast("success", "解析完成，共 " + batch.message_count + " 条消息");
      })
      .catch(toastError)
      .then(function () {
        state.wizard.uploading = false;
        event.target.value = "";
      });
  }

  function chooseSpeaker(name) {
    state.wizard.speaker = name;
    if (!state.wizard.name) state.wizard.name = name;
  }

  function percent(count, total) {
    var all = Number(total) || 0;
    if (!all) return "0%";
    return ((Number(count) || 0) / all * 100).toFixed(1) + "%";
  }

  function generatePersona() {
    var wizard = state.wizard;
    if (!wizard.batch) {
      toast("warn", "请先上传聊天记录");
      return;
    }
    if (!wizard.speaker) {
      toast("warn", "请先选择「TA 是谁」");
      return;
    }
    wizard.generating = true;
    Api.post("/api/personas/generate", {
      import_batch_id: wizard.batch.id,
      speaker: wizard.speaker,
      name: wizard.name ? wizard.name.trim() : null,
      relation: wizard.relation || "女友",
      avatar_emoji: wizard.emoji || "💫",
      nickname_for_user: wizard.nickname || "你"
    })
      .then(function (persona) {
        wizard.result = persona;
        wizard.step = 4;
        toast("success", "已从 " + wizard.batch.message_count + " 条消息中提取人格");
        return loadPersonas();
      })
      .catch(toastError)
      .then(function () {
        wizard.generating = false;
      });
  }

  /* ---------------- 聊天 ---------------- */
  function loadSessions(personaId) {
    var params = personaId ? { persona_id: personaId } : {};
    return Api.get("/api/sessions", params)
      .then(function (list) {
        state.sessions = (list || []).slice().sort(byUpdatedDesc);
        return state.sessions;
      })
      .catch(function (err) {
        toastError(err);
        return [];
      });
  }

  function loadMessages() {
    if (!state.activeSessionId) {
      state.messages = [];
      return Promise.resolve();
    }
    return Api.get("/api/sessions/" + state.activeSessionId + "/messages", { limit: 300 })
      .then(function (list) {
        state.messages = list || [];
        scrollToBottom();
      })
      .catch(toastError);
  }

  function openChat(personaId) {
    state.activePersonaId = personaId;
    state.streamError = "";
    state.notices = [];
    return loadSessions(personaId)
      .then(function () {
        var mine = state.sessions.filter(function (item) {
          return item.persona_id === personaId;
        });
        if (mine.length) {
          state.activeSessionId = mine[0].id;
          return null;
        }
        return Api.post("/api/sessions", { persona_id: personaId }).then(function (session) {
          state.activeSessionId = session.id;
          return loadSessions(personaId);
        });
      })
      .then(function () {
        return loadMessages();
      })
      .then(function () {
        return loadChatMemories();
      })
      .catch(toastError);
  }

  function createSession() {
    if (!state.activePersonaId) {
      toast("warn", "请先在下方选择一个角色");
      return;
    }
    Api.post("/api/sessions", { persona_id: state.activePersonaId })
      .then(function (session) {
        state.activeSessionId = session.id;
        return loadSessions(state.activePersonaId);
      })
      .then(loadMessages)
      .then(loadChatMemories)
      .catch(toastError);
  }

  function switchSession(sessionId) {
    state.activeSessionId = sessionId;
    state.streamError = "";
    state.notices = [];
    loadMessages();
  }

  function removeSession(sessionId) {
    if (!window.confirm("确定删除这个会话及其全部消息？该操作不可撤销。")) return;
    Api.del("/api/sessions/" + sessionId)
      .then(function () {
        toast("success", "会话已删除");
        if (state.activeSessionId === sessionId) {
          state.activeSessionId = null;
          state.messages = [];
        }
        return loadSessions(state.activePersonaId);
      })
      .then(function () {
        if (!state.activeSessionId && state.sessions.length) {
          state.activeSessionId = state.sessions[0].id;
        }
        return loadMessages();
      })
      .catch(toastError);
  }

  function onPersonaSwitch(event) {
    var personaId = Number(event.target.value);
    if (personaId) openChat(personaId);
  }

  function onComposerKeydown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage();
    }
  }

  function applySessionState(mood, affection) {
    var session = state.sessions.find(function (item) {
      return item.id === state.activeSessionId;
    });
    if (!session) return;
    if (typeof mood === "number") session.mood = mood;
    if (typeof affection === "number") session.affection = affection;
  }

  function sendMessage() {
    var text = (state.inputText || "").trim();
    if (!text || state.streaming || !state.activeSessionId) return;

    state.inputText = "";
    var sessionId = state.activeSessionId;
    var stamp = Date.now();
    var nowIso = new Date().toISOString();
    state.messages.push({
      id: "u-" + stamp,
      role: "user",
      content: text,
      feedback: 0,
      pending: false,
      created_at: nowIso
    });
    state.messages.push({
      id: "a-" + stamp,
      role: "assistant",
      content: "",
      feedback: 0,
      pending: true,
      created_at: nowIso
    });
    // 【响应式关键】push 之后必须通过数组下标取回 Vue 的响应式代理对象再读写。
    // 若像以前那样持有 push 之前的原始对象（var ai = {...}）去累加 content，
    // 改动发生在未被代理的裸对象上，不会触发重渲染，流式打字机就会失效。
    streamInto(sessionId, text, state.messages.length - 1);
  }

  /** 统一的流式写入入口：发送 / 重新生成 / 编辑后重发共用 */
  function streamInto(sessionId, text, aiIndex) {
    if (!sessionId || state.streaming) return;
    state.streamError = "";
    state.notices = [];
    function aiBubble() {
      return state.messages[aiIndex];
    }
    var target = aiBubble();
    if (target) {
      target.content = "";
      target.pending = true;
    }
    state.streaming = true;
    scrollToBottom();

    chatAbort = new AbortController();

    fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, content: text, use_memory: true }),
      signal: chatAbort.signal
    })
      .then(function (res) {
        if (!res.ok) {
          return res.text().then(function (body) {
            var data = null;
            try {
              data = JSON.parse(body);
            } catch (err) {
              data = body;
            }
            throw new Error(extractError(data, res));
          });
        }
        return readSse(res, function (event) {
          var ai = aiBubble();
          if (!ai) return;
          if (event.type === "delta") {
            ai.content += event.text || "";
            scrollToBottom();
          } else if (event.type === "notice") {
            state.notices.push({ level: event.level || "info", message: event.message || "" });
          } else if (event.type === "meta") {
            applySessionState(event.mood, event.affection);
          } else if (event.type === "error") {
            state.streamError = event.message || "生成失败";
          } else if (event.type === "done") {
            if (event.message_id) ai.id = event.message_id;
            if (event.content) ai.content = event.content;
            ai.pending = false;
            applySessionState(event.mood, event.affection);
            if (event.memory_added > 0) {
              toast("success", "TA 记住了 " + event.memory_added + " 条新信息");
              loadChatMemories();
            }
          }
        });
      })
      .then(function () {
        var ai = aiBubble();
        if (!ai) return;
        ai.pending = false;
        if (!ai.content) ai.content = "（本次没有收到内容，请重试）";
        scrollToBottom();
      })
      .catch(function (err) {
        var ai = aiBubble();
        if (err && err.name === "AbortError") {
          if (ai) {
            ai.pending = false;
            if (!ai.content) ai.content = "（已停止生成）";
          }
          return;
        }
        state.streamError = responseErrorMessage(err);
        if (ai) {
          ai.pending = false;
          if (!ai.content) ai.content = "（生成失败）";
        }
      })
      .then(function () {
        state.streaming = false;
        chatAbort = null;
        scrollToBottom();
        loadSessions(state.activePersonaId);
      });
  }

  function stopGeneration() {
    if (chatAbort) chatAbort.abort();
  }

  /* ---------------- 消息操作：重新生成 / 编辑后重发 / 复制 ---------------- */
  function messageIndexOf(target) {
    if (!target) return -1;
    for (var i = 0; i < state.messages.length; i += 1) {
      if (state.messages[i] === target) return i;
      if (target.id !== undefined && state.messages[i].id === target.id) return i;
    }
    return -1;
  }

  function isLastAssistant(message) {
    if (!message || message.role !== "assistant") return false;
    for (var i = state.messages.length - 1; i >= 0; i -= 1) {
      if (state.messages[i].role === "assistant") {
        return state.messages[i] === message || state.messages[i].id === message.id;
      }
    }
    return false;
  }

  function findPrevUserText(index) {
    for (var i = index - 1; i >= 0; i -= 1) {
      var item = state.messages[i];
      if (item && item.role === "user" && String(item.content || "").trim()) {
        return String(item.content);
      }
    }
    return "";
  }

  /**
   * 重新生成：后端目前没有「重生成指定消息」的接口，这里用「以同一提问再发一轮」
   * 的方式实现——清空当前气泡并用 SSE 重新填充，旧回复不落库、新回复落库。
   */
  function regenerateMessage(message) {
    if (state.streaming) {
      toast("warn", "正在生成中，请稍候");
      return;
    }
    var index = messageIndexOf(message);
    if (index < 0) return;
    var prompt = findPrevUserText(index);
    if (!prompt) {
      toast("warn", "这条消息之前没有可重发的提问");
      return;
    }
    if (!state.activeSessionId) return;
    state.messages[index].created_at = new Date().toISOString();
    state.messages[index].feedback = 0;
    streamInto(state.activeSessionId, prompt, index);
  }

  function openEditMessage(message) {
    if (state.streaming) {
      toast("warn", "正在生成中，暂不能编辑");
      return;
    }
    var index = messageIndexOf(message);
    if (index < 0) return;
    state.editTarget = index;
    state.editText = String(message.content || "");
    state.editVisible = true;
  }

  function closeEditMessage() {
    state.editVisible = false;
    state.editTarget = -1;
    state.editText = "";
  }

  /** 编辑后重发：就地更新用户气泡文案，并以新文案重新提问、把回复流进新的 AI 气泡 */
  function submitEditMessage() {
    var text = String(state.editText || "").trim();
    if (!text) {
      toast("warn", "内容不能为空");
      return;
    }
    var index = state.editTarget;
    if (index < 0 || !state.messages[index]) {
      closeEditMessage();
      return;
    }
    if (!state.activeSessionId) {
      toast("warn", "请先选择一个会话");
      return;
    }
    var target = state.messages[index];
    target.content = text;
    target.edited = true;
    var nextIndex = index + 1;
    closeEditMessage();

    var stamp = Date.now();
    state.messages.splice(nextIndex, 0, {
      id: "a-edit-" + stamp,
      role: "assistant",
      content: "",
      feedback: 0,
      pending: true,
      created_at: new Date().toISOString()
    });
    streamInto(state.activeSessionId, text, nextIndex);
  }

  function sendFeedback(message, action) {
    if (typeof message.id !== "number") return;
    Api.post("/api/messages/" + message.id + "/feedback", { action: action })
      .then(function (data) {
        message.feedback = data.feedback;
        applySessionState(data.mood, data.affection);
        toast("success", action === "like" ? "已记录你的喜欢" : "已记录你的不满");
      })
      .catch(toastError);
  }

  function openRewrite(message) {
    if (typeof message.id !== "number") return;
    state.rewriteMessageId = message.id;
    state.rewriteText = message.content;
    state.rewriteVisible = true;
  }

  function submitRewrite() {
    var text = (state.rewriteText || "").trim();
    if (!text) {
      toast("warn", "改写内容不能为空");
      return;
    }
    state.rewriteSaving = true;
    Api.post("/api/messages/" + state.rewriteMessageId + "/feedback", {
      action: "rewrite",
      content: text
    })
      .then(function (data) {
        var target = state.messages.find(function (item) {
          return item.id === data.message_id;
        });
        if (target) {
          target.content = data.content;
          target.rewritten = true;
        }
        applySessionState(data.mood, data.affection);
        state.rewriteVisible = false;
        toast("success", "已改写，并作为偏好样本记录");
      })
      .catch(toastError)
      .then(function () {
        state.rewriteSaving = false;
      });
  }

  /* ---------------- 记忆 ---------------- */
  function loadChatMemories() {
    if (!state.activePersonaId) {
      state.chatMemories = [];
      return Promise.resolve();
    }
    return Api.get("/api/memories", { persona_id: state.activePersonaId })
      .then(function (list) {
        state.chatMemories = list || [];
      })
      .catch(toastError);
  }

  function loadMemories() {
    var params = state.memFilterPersonaId ? { persona_id: state.memFilterPersonaId } : {};
    return Api.get("/api/memories", params)
      .then(function (list) {
        state.memories = list || [];
      })
      .catch(toastError);
  }

  function startAddMemory() {
    state.memEditId = 0;
    state.memForm = emptyMemForm();
    state.memForm.persona_id =
      state.memFilterPersonaId || (state.personas.length ? state.personas[0].id : null);
  }

  function startEditMemory(memory) {
    state.memEditId = memory.id;
    state.memForm = {
      id: memory.id,
      persona_id: memory.persona_id,
      content: memory.content,
      kind: memory.kind,
      importance: memory.importance
    };
  }

  function cancelMemoryEdit() {
    state.memEditId = null;
    state.memForm = emptyMemForm();
  }

  function submitMemory() {
    var form = state.memForm;
    if (!form.persona_id) {
      toast("warn", "请选择人格");
      return;
    }
    if (!(form.content || "").trim()) {
      toast("warn", "记忆内容不能为空");
      return;
    }
    var payload = {
      persona_id: form.persona_id,
      content: form.content.trim(),
      kind: form.kind,
      importance: Number(form.importance)
    };
    var task = state.memEditId
      ? Api.put("/api/memories/" + state.memEditId, {
          content: payload.content,
          kind: payload.kind,
          importance: payload.importance
        })
      : Api.post("/api/memories", payload);

    task
      .then(function () {
        toast("success", state.memEditId ? "记忆已更新" : "记忆已新增");
        cancelMemoryEdit();
        return loadMemories();
      })
      .then(loadChatMemories)
      .catch(toastError);
  }

  function removeMemory(memoryId, fromChatPanel) {
    if (!window.confirm("确定删除这条记忆？删除后 TA 将不再记得这件事。")) return;
    Api.del("/api/memories/" + memoryId)
      .then(function () {
        toast("success", "记忆已删除");
        if (fromChatPanel) {
          return loadChatMemories();
        }
        return loadMemories();
      })
      .catch(toastError);
  }

  function runMemoryTest() {
    var query = (state.memTestQuery || "").trim();
    if (!query) {
      toast("warn", "请输入用于检索的句子");
      return;
    }
    if (!state.memTestPersonaId) {
      toast("warn", "请选择人格");
      return;
    }
    state.memTestLoading = true;
    Api.post("/api/memories/search", {
      persona_id: state.memTestPersonaId,
      query: query,
      top_k: 5
    })
      .then(function (data) {
        state.memTestResult = data;
      })
      .catch(toastError)
      .then(function () {
        state.memTestLoading = false;
      });
  }

  /* ---------------- 人设编辑 ---------------- */
  function loadPersonaForm(personaId) {
    if (!personaId) {
      state.personaForm = emptyPersonaForm();
      return refreshPreview();
    }
    return Api.get("/api/personas/" + personaId)
      .then(function (persona) {
        var card = persona.persona_card || {};
        state.personaForm = {
          id: persona.id,
          name: persona.name,
          avatar_emoji: persona.avatar_emoji,
          relation: persona.relation,
          nickname_for_user: persona.nickname_for_user,
          sliders: Object.assign(emptySliderSet(), persona.sliders || {}),
          greeting: persona.greeting || "",
          phrases: (card.top_phrases || []).join(", "),
          description: card.extra_description || "",
          sample_dialogues: card.sample_dialogues || [],
          persona_card: card,
          source: persona.source,
          saving: false
        };
        return refreshPreview();
      })
      .catch(toastError);
  }

  function buildPersonaCard() {
    var form = state.personaForm;
    var card = Object.assign({}, form.persona_card || {});
    card.nickname = form.name || "未命名";
    card.top_phrases = String(form.phrases || "")
      .split(/[,，、\s]+/)
      .map(function (item) {
        return item.trim();
      })
      .filter(function (item) {
        return item;
      })
      .slice(0, 10);
    card.extra_description = form.description || "";
    if (form.sample_dialogues && form.sample_dialogues.length) {
      card.sample_dialogues = form.sample_dialogues;
    }
    return card;
  }

  function refreshPreview() {
    state.previewLoading = true;
    return Api.post("/api/personas/preview-prompt", {
      persona: {
        name: state.personaForm.name || "未命名",
        avatar_emoji: state.personaForm.avatar_emoji || "🌸",
        relation: state.personaForm.relation || "女友",
        nickname_for_user: state.personaForm.nickname_for_user || "你",
        sliders: state.personaForm.sliders,
        persona_card: buildPersonaCard(),
        greeting: state.personaForm.greeting || ""
      },
      sample_user_message: "在吗？今天有点累"
    })
      .then(function (data) {
        state.previewPrompt = data.system_prompt || "";
      })
      .catch(function (err) {
        state.previewPrompt = "预览失败：" + responseErrorMessage(err);
      })
      .then(function () {
        state.previewLoading = false;
      });
  }

  function schedulePreview() {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(refreshPreview, 450);
  }

  function savePersona() {
    var form = state.personaForm;
    if (!(form.name || "").trim()) {
      toast("warn", "请填写人格名称");
      return;
    }
    form.saving = true;
    var payload = {
      name: form.name.trim(),
      avatar_emoji: form.avatar_emoji || "🌸",
      relation: form.relation || "女友",
      nickname_for_user: form.nickname_for_user || "你",
      sliders: form.sliders,
      persona_card: buildPersonaCard(),
      greeting: form.greeting || ""
    };
    var task = form.id
      ? Api.put("/api/personas/" + form.id, payload)
      : Api.post("/api/personas", Object.assign({ source: "manual" }, payload));

    task
      .then(function (persona) {
        form.id = persona.id;
        toast("success", "人设已保存");
        return loadPersonas();
      })
      .catch(toastError)
      .then(function () {
        form.saving = false;
      });
  }

  function onPersonaFormSwitch(event) {
    var value = event.target.value;
    loadPersonaForm(value ? Number(value) : null);
  }

  /* ---------------- 角色卡 / 世界书 / 备份 ---------------- */
  function ensurePersonaPick() {
    if (!state.cards.personaId && state.personas.length) {
      state.cards.personaId = state.personas[0].id;
    }
    if (!state.lore.personaId && state.personas.length) {
      state.lore.personaId = state.personas[0].id;
    }
  }

  function findPersona(id) {
    var target = Number(id) || 0;
    return (
      state.personas.find(function (item) {
        return item.id === target;
      }) || null
    );
  }

  function onCardFileChange(event) {
    var file = event.target.files && event.target.files[0];
    if (!file) return;
    var input = event.target;
    pendingCardFile = file;
    state.cards.pending = { name: file.name, size: file.size };
    state.cards.parseResult = null;
    state.cards.parseIsImport = false;
    state.cards.parsing = true;
    uploadFormData("/api/cards/parse", file)
      .then(function (summary) {
        state.cards.parseResult = summary || null;
        toast("success", "角色卡解析完成，可点「导入为角色」");
      })
      .catch(function (err) {
        pendingCardFile = null;
        state.cards.pending = null;
        toastError(err);
      })
      .then(function () {
        state.cards.parsing = false;
        input.value = "";
      });
  }

  function importCard() {
    if (!pendingCardFile) {
      toast("warn", "请先选择角色卡文件");
      return;
    }
    state.cards.importing = true;
    uploadFormData("/api/cards/import", pendingCardFile)
      .then(function (data) {
        state.cards.parseResult = (data && data.summary) || null;
        state.cards.parseIsImport = true;
        if (data && data.persona) {
          state.cards.personaId = data.persona.id;
          state.lore.personaId = data.persona.id;
          toast("success", "已导入角色「" + data.persona.name + "」");
        } else {
          toast("success", "角色卡已导入");
        }
        pendingCardFile = null;
        state.cards.pending = null;
        return loadPersonas();
      })
      .catch(toastError)
      .then(function () {
        state.cards.importing = false;
      });
  }

  function exportCard(kind) {
    var persona = findPersona(state.cards.personaId) || state.personas[0];
    if (!persona) {
      toast("warn", "还没有可导出的角色");
      return;
    }
    var ext = kind === "png" ? "png" : "json";
    var filename = safeFileName(persona.name, "persona") + "-card." + ext;
    state.cards.exporting = ext;
    downloadFromApi("/api/personas/" + persona.id + "/card." + ext, filename)
      .then(function () {
        toast("success", ext === "png" ? "PNG 角色卡已导出" : "JSON 角色卡已导出");
      })
      .catch(toastError)
      .then(function () {
        state.cards.exporting = "";
      });
  }

  function emptyLoreForm() {
    return {
      id: null,
      keys: "",
      content: "",
      enabled: true,
      constant: false,
      case_sensitive: false,
      priority: 100,
      position: "before_char",
      depth: 4,
      token_budget: 0,
      comment: ""
    };
  }

  function loadWorldbook(personaId) {
    var id = Number(personaId || state.lore.personaId || 0);
    if (!id) {
      state.lore.entries = [];
      return Promise.resolve();
    }
    state.lore.personaId = id;
    state.lore.loading = true;
    return Api.get("/api/personas/" + id + "/worldbook")
      .then(function (data) {
        state.lore.entries = (data && data.entries) || [];
        state.lore.preview = null;
      })
      .catch(toastError)
      .then(function () {
        state.lore.loading = false;
      });
  }

  function onLorePersonaChange(event) {
    var id = Number(event.target.value);
    if (!id) return;
    state.lore.personaId = id;
    loadWorldbook(id);
  }

  function openLoreEditor(entry) {
    var form = emptyLoreForm();
    if (entry) {
      form.id = entry.id;
      form.keys = (entry.keys || []).join(", ");
      form.content = entry.content || "";
      form.enabled = entry.enabled !== false;
      form.constant = !!entry.constant;
      form.case_sensitive = !!entry.case_sensitive;
      form.priority = entry.priority === undefined || entry.priority === null ? 100 : entry.priority;
      form.position = entry.position || "before_char";
      form.depth = entry.depth === undefined || entry.depth === null ? 4 : entry.depth;
      form.token_budget = entry.token_budget === undefined || entry.token_budget === null ? 0 : entry.token_budget;
      form.comment = entry.comment || "";
    }
    state.lore.editing = form;
    state.lore.editVisible = true;
  }

  function closeLoreEditor() {
    state.lore.editVisible = false;
    state.lore.editing = null;
  }

  function saveLoreEntry() {
    var form = state.lore.editing;
    if (!form) return;
    if (!state.lore.personaId) {
      toast("warn", "请先选择角色");
      return;
    }
    if (!String(form.content || "").trim()) {
      toast("warn", "条目内容不能为空");
      return;
    }
    var keys = String(form.keys || "")
      .split(/[,，\n]+/)
      .map(function (item) {
        return item.trim();
      })
      .filter(function (item) {
        return item;
      });
    if (!keys.length && !form.constant) {
      toast("warn", "非常驻条目至少需要一个触发关键词");
      return;
    }
    var payload = {
      keys: keys,
      content: String(form.content).trim(),
      enabled: !!form.enabled,
      constant: !!form.constant,
      case_sensitive: !!form.case_sensitive,
      priority: Number(form.priority) || 0,
      position: form.position || "before_char",
      depth: Number(form.depth) || 0,
      token_budget: Number(form.token_budget) || 0,
      comment: form.comment || ""
    };
    state.lore.saving = true;
    var task = form.id
      ? Api.put("/api/worldbook/" + form.id, payload)
      : Api.post("/api/personas/" + state.lore.personaId + "/worldbook", payload);
    task
      .then(function () {
        toast("success", form.id ? "条目已更新" : "条目已创建");
        state.lore.editVisible = false;
        state.lore.editing = null;
        return loadWorldbook(state.lore.personaId);
      })
      .catch(toastError)
      .then(function () {
        state.lore.saving = false;
      });
  }

  function toggleLoreEntry(entry) {
    Api.put("/api/worldbook/" + entry.id, { enabled: !entry.enabled })
      .then(function (updated) {
        if (updated && updated.id) {
          var index = state.lore.entries.findIndex(function (item) {
            return item.id === updated.id;
          });
          if (index >= 0) state.lore.entries.splice(index, 1, updated);
        } else {
          entry.enabled = !entry.enabled;
        }
        toast("success", entry.enabled ? "条目已启用" : "条目已停用");
      })
      .catch(toastError);
  }

  function removeLoreEntry(entry) {
    if (!window.confirm("删除世界书条目？该操作不可撤销。")) return;
    Api.del("/api/worldbook/" + entry.id)
      .then(function () {
        toast("success", "条目已删除");
        return loadWorldbook(state.lore.personaId);
      })
      .catch(toastError);
  }

  function runLorePreview() {
    if (!state.lore.personaId) {
      toast("warn", "请先选择角色");
      return;
    }
    var text = String(state.lore.previewText || "").trim();
    if (!text) {
      toast("warn", "请输入用于命中测试的文本");
      return;
    }
    state.lore.previewLoading = true;
    Api.post("/api/personas/" + state.lore.personaId + "/worldbook/preview", {
      text: text,
      token_budget: Number(state.lore.previewBudget) || 0
    })
      .then(function (data) {
        /* 兜底归一化：模板直接读 stats.*，避免后端字段缺失时渲染报错 */
        var payload = data || {};
        var raw = payload.stats || {};
        payload.stats = {
          candidates: Number(raw.candidates || 0),
          injected: Number(raw.injected || 0),
          budget: Number(raw.budget || 0),
          used: Number(raw.used || 0),
          skipped_budget: Array.isArray(raw.skipped_budget) ? raw.skipped_budget : [],
          constant_injected: Number(raw.constant_injected || 0),
          keyword_injected: Number(raw.keyword_injected || 0)
        };
        payload.items = Array.isArray(payload.items) ? payload.items : [];
        state.lore.preview = payload;
        var stats = payload.stats;
        toast("success", "命中 " + (stats.injected || 0) + " 条 / 候选 " + (stats.candidates || 0) + " 条");
      })
      .catch(toastError)
      .then(function () {
        state.lore.previewLoading = false;
      });
  }

  /* 后端备份导入返回的 created / skipped / remapped 是「按表分组」的对象，这里拍平成可读统计 */
  var BACKUP_TABLE_LABELS = {
    personas: "角色",
    sessions: "会话",
    messages: "消息",
    memories: "记忆",
    worldbook: "世界书",
    worldbook_entries: "世界书",
    feedbacks: "反馈",
    settings: "设置"
  };

  function backupCount(bucket) {
    if (bucket === null || bucket === undefined) return 0;
    if (typeof bucket === "number") return bucket;
    if (typeof bucket === "string") return Number(bucket) || 0;
    var total = 0;
    Object.keys(bucket).forEach(function (key) {
      total += Number(bucket[key] || 0);
    });
    return total;
  }

  function backupDetail(bucket) {
    if (!bucket || typeof bucket !== "object") return "";
    var parts = [];
    Object.keys(bucket).forEach(function (key) {
      var count = Number(bucket[key] || 0);
      if (count > 0) parts.push((BACKUP_TABLE_LABELS[key] || key) + " " + count);
    });
    return parts.join(" · ");
  }

  function exportBackup() {
    state.backup.exporting = true;
    downloadFromApi("/api/backup/export", "cyber-girlfriend-backup-" + dateStamp() + ".json")
      .then(function () {
        toast("success", "备份文件已导出");
      })
      .catch(toastError)
      .then(function () {
        state.backup.exporting = false;
      });
  }

  function onBackupFileChange(event) {
    var file = event.target.files && event.target.files[0];
    if (!file) return;
    var input = event.target;
    var strategy = state.backup.strategy || "merge_by_id";
    state.backup.importing = true;
    state.backup.result = null;
    uploadFormData("/api/backup/import?strategy=" + encodeURIComponent(strategy), file)
      .then(function (data) {
        state.backup.result = data || null;
        toast("success", "备份导入完成");
        return loadPersonas().then(loadSettings);
      })
      .catch(toastError)
      .then(function () {
        state.backup.importing = false;
        input.value = "";
      });
  }

  /* ---------------- 导入批次 ---------------- */
  function loadBatches() {
    state.batchesLoading = true;
    return Api.get("/api/import/batches")
      .then(function (list) {
        state.batches = (list || []).slice(0, 12);
      })
      .catch(toastError)
      .then(function () {
        state.batchesLoading = false;
      });
  }

  function useBatch(batch) {
    return Api.get("/api/import/batches/" + batch.id)
      .then(function (detail) {
        state.wizard.batch = detail || batch;
        state.wizard.speaker = "";
        state.wizard.step = 2;
      })
      .catch(toastError);
  }

  function removeBatch(batch) {
    if (!window.confirm("删除这个导入批次？（只删解析记录，已生成的人格不受影响）")) return;
    Api.del("/api/import/batches/" + batch.id)
      .then(function () {
        toast("success", "批次已删除");
        return loadBatches();
      })
      .catch(toastError);
  }

  /* ======================================================================
   * 4.1 设置
   * ==================================================================== */
  function loadSettings() {
    return Api.get("/api/settings")
      .then(function (data) {
        state.settings = data || {};
        state.settingsForm = {
          llm_provider: data.llm_provider || "mock",
          llm_base_url: data.llm_base_url || "",
          llm_api_key: data.llm_api_key_masked || "",
          llm_model: data.llm_model || "",
          llm_temperature: typeof data.llm_temperature === "number" ? data.llm_temperature : 0.8,
          memory_top_k: data.memory_top_k || 5,
          recent_window: data.recent_window || 12,
          reflect_every: data.reflect_every || 6,
          lore_enabled: data.lore_enabled !== false,
          lore_budget: typeof data.lore_budget === "number" ? data.lore_budget : 512,
          lore_scan_window: typeof data.lore_scan_window === "number" ? data.lore_scan_window : 6,
          desensitize_enabled: data.desensitize_enabled !== false,
          desensitize_blacklist: data.desensitize_blacklist || ""
        };
      })
      .catch(toastError);
  }

  function saveSettings() {
    var form = state.settingsForm;
    if (!form) return;
    state.settingsSaving = true;
    state.settingsSaved = false;
    Api.put("/api/settings", {
      llm_provider: form.llm_provider,
      llm_base_url: form.llm_base_url,
      llm_api_key: form.llm_api_key,
      llm_model: form.llm_model,
      llm_temperature: Number(form.llm_temperature),
      memory_top_k: Number(form.memory_top_k),
      recent_window: Number(form.recent_window),
      reflect_every: Number(form.reflect_every),
      lore_enabled: !!form.lore_enabled,
      lore_budget: Number(form.lore_budget) || 0,
      lore_scan_window: Number(form.lore_scan_window) || 0,
      desensitize_enabled: !!form.desensitize_enabled,
      desensitize_blacklist: form.desensitize_blacklist || ""
    })
      .then(function (data) {
        state.settings = data || {};
        state.settingsForm.llm_api_key = data.llm_api_key_masked || "";
        state.settingsForm.desensitize_enabled = data.desensitize_enabled !== false;
        state.settingsSaved = true;
        toast("success", "配置已保存，立即生效");
        setTimeout(function () {
          state.settingsSaved = false;
        }, 2600);
      })
      .catch(toastError)
      .then(function () {
        state.settingsSaving = false;
      });
  }

  /** 导入预览页 / 设置页共用：快速关闭脱敏并写回 settings */
  function disableDesensitize() {
    Api.put("/api/settings", { desensitize_enabled: false })
      .then(function () {
        if (state.settingsForm) state.settingsForm.desensitize_enabled = false;
        toast("success", "已关闭导入脱敏，后续导入将保留原文");
      })
      .catch(toastError);
  }

  /** 从导入预览页的统计块跳转到设置页，方便逐项调整 */
  function gotoDesensitizeSettings() {
    go("settings");
    setTimeout(function () {
      var panel = document.getElementById("panel-desens");
      if (panel && panel.scrollIntoView) {
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 260);
  }

  /* ======================================================================
   * 5. hash 路由
   * ==================================================================== */
  var ROUTES = {
    wall: 1,
    import: 1,
    chat: 1,
    persona: 1,
    memory: 1,
    cards: 1,
    lore: 1,
    backup: 1,
    settings: 1
  };

  function parseHash() {
    var raw = String(location.hash || "").replace(/^#\/?/, "");
    var parts = raw.split("?");
    var name = parts[0] || "wall";
    var query = {};
    if (parts[1]) {
      parts[1].split("&").forEach(function (pair) {
        var seg = pair.split("=");
        if (seg[0]) {
          query[decodeURIComponent(seg[0])] = decodeURIComponent(seg[1] || "");
        }
      });
    }
    if (!ROUTES[name]) name = "wall";
    return { name: name, query: query };
  }

  function go(name, query) {
    var qs = Object.keys(query || {})
      .map(function (key) {
        return key + "=" + encodeURIComponent(query[key]);
      })
      .join("&");
    location.hash = "#/" + name + (qs ? "?" + qs : "");
  }

  function handleHash() {
    var route = parseHash();
    state.view = route.name;

    if (route.name === "wall") {
      loadPersonas();
    } else if (route.name === "import") {
      loadPersonas();
    } else if (route.name === "chat") {
      if (route.query.persona_id) {
        openChat(Number(route.query.persona_id));
      } else if (route.query.session_id) {
        state.activeSessionId = Number(route.query.session_id);
        loadSessions()
          .then(loadMessages)
          .then(function () {
            if (state.activeSessionId) loadChatMemories();
          });
      } else if (state.activePersonaId) {
        loadSessions(state.activePersonaId).then(loadMessages);
      } else {
        loadSessions().then(function () {
          if (state.sessions.length) {
            state.activePersonaId = state.sessions[0].persona_id;
            state.activeSessionId = state.sessions[0].id;
            loadMessages();
            loadChatMemories();
          }
        });
      }
    } else if (route.name === "persona") {
      loadPersonas().then(function () {
        loadPersonaForm(route.query.persona_id ? Number(route.query.persona_id) : null);
      });
    } else if (route.name === "memory") {
      if (route.query.persona_id) {
        state.memFilterPersonaId = Number(route.query.persona_id);
      }
      loadPersonas().then(loadMemories);
    } else if (route.name === "settings") {
      loadSettings();
    } else if (route.name === "cards") {
      loadPersonas();
    } else if (route.name === "lore") {
      loadPersonas().then(function () {
        if (route.query.persona_id) state.lore.personaId = Number(route.query.persona_id);
        return loadWorldbook(state.lore.personaId);
      });
    } else if (route.name === "backup") {
      loadBatches();
    }
  }

  function chatWith(personaId) {
    go("chat", { persona_id: personaId });
  }

  function editPersona(personaId) {
    go("persona", { persona_id: personaId });
  }

  function openMemoryFor(personaId) {
    go("memory", { persona_id: personaId });
  }

  /* 删除人格（级联清理其会话 / 消息 / 记忆 / 反馈） */
  function removePersona(persona) {
    var name = (persona && persona.name) || "该人格";
    if (!window.confirm("删除「" + name + "」？其会话、消息与长期记忆会一并删除，且不可恢复。")) {
      return;
    }
    Api.del("/api/personas/" + persona.id)
      .then(function () {
        toast("ok", "已删除人格「" + name + "」");
        if (state.activePersonaId === persona.id) {
          state.activePersonaId = 0;
          state.activeSessionId = 0;
        }
        if (state.personaForm && state.personaForm.id === persona.id) {
          state.personaForm = emptyPersonaForm();
        }
        return loadPersonas();
      })
      .catch(function (err) {
        toastError(err);
      });
  }

  /* ======================================================================
   * 6. 视图模板
   * ==================================================================== */
  var TEMPLATE = [
    '<div class="app-shell">',
    '  <div class="toast-stack">',
    '    <div v-for="t in state.toasts" :key="t.id" class="toast" :class="\'toast-\' + t.type">{{ t.text }}</div>',
    "  </div>",

    '  <aside class="sidebar">',
    '    <div class="brand">',
    '      <div class="brand-logo">💜</div>',
    '      <div class="brand-text">',
    '        <div class="brand-title">赛博女友</div>',
    '        <div class="brand-sub">CyberGirlfriend</div>',
    "      </div>",
    "    </div>",
    '    <nav class="nav">',
    '      <button v-for="item in navItems" :key="item.key" class="nav-item" :class="{ active: state.view === item.key }" @click="go(item.key)">',
    '        <span class="nav-icon">{{ item.icon }}</span>',
    '        <span class="nav-label">{{ item.label }}</span>',
    "      </button>",
    "    </nav>",
    '    <div class="sidebar-foot">',
    '      <div class="mode-chip" :class="isDemoMode ? \'chip-warn\' : \'chip-ok\'">{{ isDemoMode ? \'演示模式（mock）\' : \'真实模型\' }}</div>',
    '      <div class="sidebar-tip">v0.1.0 · demo</div>',
    "    </div>",
    "  </aside>",

    '  <main class="main">',

    /* ---------------- 角色墙 ---------------- */
    '    <section class="view" v-show="state.view === \'wall\'">',
    '      <header class="view-head">',
    "        <div>",
    "          <h1>角色墙</h1>",
    '          <p class="muted">挑一个 TA 开始聊天，或导入你们的聊天记录生成专属人格</p>',
    "        </div>",
    '        <div class="head-actions">',
    '          <button class="btn btn-ghost" @click="openCreatePersona">＋ 新建人格</button>',
    '          <button class="btn btn-primary" @click="go(\'import\')">导入聊天记录</button>',
    "        </div>",
    "      </header>",

    '      <div class="persona-grid" v-if="state.personas.length">',
    '        <article class="persona-card" v-for="p in state.personas" :key="p.id" @click="chatWith(p.id)">',
    '          <div class="pc-top">',
    '            <div class="avatar avatar-lg">{{ p.avatar_emoji }}</div>',
    '            <div class="pc-id">',
    '              <div class="pc-name">{{ p.name }}</div>',
    '              <div class="tag-row">',
    '                <span class="tag tag-rel">{{ p.relation }}</span>',
    '                <span class="tag" :class="p.source === \'imported\' ? \'tag-import\' : \'tag-manual\'">{{ p.source === \'imported\' ? \'导入生成\' : \'手动创建\' }}</span>',
    "              </div>",
    "            </div>",
    "          </div>",
    '          <p class="pc-desc">{{ p.summary_text || \'还没有人设描述，去人设编辑里补一段吧\' }}</p>',
    '          <div class="pc-traits">',
    '            <span class="trait" v-for="k in traitTags(p)" :key="k">{{ sliderLabels[k] }}</span>',
    "          </div>",
    '          <div class="pc-foot">',
    '            <span class="muted small">{{ sampleCountText(p) }}</span>',
    '            <span class="pc-cta">进入聊天 →</span>',
    "          </div>",
    '          <div class="pc-tools">',
    '            <button class="icon-btn" title="编辑人设" @click.stop="editPersona(p.id)">✏️</button>',
    '            <button class="icon-btn" title="查看记忆" @click.stop="openMemoryFor(p.id)">🧠</button>',
    '            <button class="icon-btn" title="删除人格" @click.stop="removePersona(p)">🗑</button>',
    "          </div>",
    "        </article>",
    "      </div>",

    '      <div class="empty" v-else>',
    '        <div class="empty-emoji">🌙</div>',
    "        <h3>角色墙还是空的</h3>",
    '        <p class="muted">先新建一个人格，或导入一段聊天记录让 TA 自己长出人设</p>',
    '        <div class="head-actions">',
    '          <button class="btn btn-ghost" @click="openCreatePersona">＋ 新建人格</button>',
    '          <button class="btn btn-primary" @click="go(\'import\')">导入聊天记录</button>',
    "        </div>",
    "      </div>",
    "    </section>",

    /* ---------------- 导入向导 ---------------- */
    '    <section class="view" v-show="state.view === \'import\'">',
    '      <header class="view-head">',
    "        <div>",
    "          <h1>导入向导</h1>",
    '          <p class="muted">支持微信 / QQ 导出的 txt、Telegram 导出的 json、通用 csv；文件仅在本地解析</p>',
    "        </div>",
    '        <div class="head-actions">',
    '          <button class="btn btn-ghost" @click="resetWizard">重新开始</button>',
    "        </div>",
    "      </header>",

    '      <div class="steps">',
    '        <div class="step" v-for="(label, index) in wizardSteps" :key="label" :class="{ active: state.wizard.step === index + 1, done: state.wizard.step > index + 1 }">',
    '          <div class="step-dot">{{ state.wizard.step > index + 1 ? \'✓\' : index + 1 }}</div>',
    '          <div class="step-label">{{ label }}</div>',
    '          <div class="step-line" v-if="index < wizardSteps.length - 1"></div>',
    "        </div>",
    "      </div>",

    '      <div class="panel" v-if="state.wizard.step === 1">',
    "        <h2>第 1 步 · 上传聊天记录</h2>",
    '        <p class="muted">选择导出的 .txt / .json / .csv 文件（上限 24MB）。解析全部在本地完成，不会上传到第三方服务。</p>',
    '        <label class="upload-box">',
    '          <input type="file" accept=".txt,.json,.csv" @change="onFileChange" />',
    '          <span class="upload-icon">📄</span>',
    '          <span class="upload-text">点击选择文件</span>',
    '          <span class="muted small">支持微信 txt / QQ txt / Telegram json / 通用 csv</span>',
    "        </label>",
    '        <div class="muted" v-if="state.wizard.uploading">正在解析文件…</div>',
    '        <div class="batch-box" v-if="state.batches.length">',
    '          <div class="batch-head">',
    '            <h3>最近导入批次</h3>',
    '            <button class="btn btn-mini btn-ghost" @click="loadBatches">刷新</button>',
    "          </div>",
    '          <div class="batch-row" v-for="b in state.batches" :key="b.id">',
    '            <div class="batch-main">',
    '              <div class="batch-name">{{ b.filename }}</div>',
    '              <div class="muted small">{{ b.fmt }} · {{ b.message_count }} 条 · {{ fmtClock(b.created_at) }}</div>',
    "            </div>",
    '            <span class="tag tag-mini" v-if="b.desensitize_enabled === false">脱敏关</span>',
    '            <button class="btn btn-mini" @click="useBatch(b)">复用</button>',
    '            <button class="icon-btn" title="删除批次" @click="removeBatch(b)">🗑</button>',
    "          </div>",
    "        </div>",
    '        <h3>支持的格式示例</h3>',
    '        <div class="fmt-grid">',
    '          <div class="fmt-card" v-for="fmt in formatHelp" :key="fmt.name">',
    '            <div class="fmt-name">{{ fmt.name }}</div>',
    '            <pre class="fmt-sample">{{ fmt.sample }}</pre>',
    '            <p class="muted small">{{ fmt.tip }}</p>',
    "          </div>",
    "        </div>",
    "      </div>",

    '      <div class="panel" v-if="state.wizard.step === 2 && state.wizard.batch">',
    "        <h2>第 2 步 · 解析结果</h2>",
    '        <div class="tag-row">',
    '          <span class="tag">格式：{{ state.wizard.batch.fmt }}</span>',
    '          <span class="tag">文件：{{ state.wizard.batch.filename }}</span>',
    '          <span class="tag">共 {{ state.wizard.batch.message_count }} 条消息</span>',
    '          <span class="tag">发言人 {{ batchSpeakers.length }} 人</span>',
    "        </div>",

    '        <div class="desens-card" v-if="state.wizard.batch.desensitize">',
    '          <div class="desens-head">',
    '            <span class="desens-title">🔒 脱敏处理</span>',
    '            <span class="tag" :class="state.wizard.batch.desensitize.enabled ? \'tag-import\' : \'tag-manual\'">{{ state.wizard.batch.desensitize.enabled ? \'已启用\' : \'已关闭\' }}</span>',
    "          </div>",
    '          <p class="muted small">{{ desensTotalText(state.wizard.batch) }}</p>',
    '          <div class="desens-grid">',
    '            <div class="desens-cell" v-for="row in desensRows(state.wizard.batch)" :key="row.key">',
    '              <div class="desens-num">{{ row.count }}</div>',
    '              <div class="desens-label">{{ row.label }}</div>',
    "            </div>",
    '            <div class="desens-cell" v-if="!desensRows(state.wizard.batch).length">',
    '              <div class="desens-num">0</div>',
    '              <div class="desens-label">未命中敏感信息</div>',
    "            </div>",
    "          </div>",
    '          <div class="desens-foot">',
    '            <span class="muted small">{{ desensDropText(state.wizard.batch) }}</span>',
    '            <span class="foot-actions">',
    '              <button class="btn btn-mini btn-ghost" v-if="state.wizard.batch.desensitize.enabled" @click="disableDesensitize">关闭脱敏</button>',
    '              <button class="btn btn-mini" @click="gotoDesensitizeSettings">脱敏设置</button>',
    "            </span>",
    "          </div>",
    "        </div>",

    "        <h3>发言人统计</h3>",
    '        <table class="table">',
    "          <thead><tr><th>发言人</th><th>消息数</th><th>占比</th><th>操作</th></tr></thead>",
    "          <tbody>",
    '            <tr v-for="sp in batchSpeakers" :key="sp.name">',
    "              <td>{{ sp.name }}</td>",
    "              <td>{{ sp.count }}</td>",
    '              <td>{{ percent(sp.count, state.wizard.batch.message_count) }}</td>',
    '              <td><button class="btn btn-mini" :class="{ \'btn-primary\': state.wizard.speaker === sp.name }" @click="chooseSpeaker(sp.name)">选 TA</button></td>',
    "            </tr>",
    "          </tbody>",
    "        </table>",
    "        <h3>最近消息预览</h3>",
    '        <div class="preview-list">',
    '          <div class="preview-item" v-for="(item, index) in state.wizard.batch.preview" :key="index">',
    '            <span class="preview-speaker">{{ item.speaker }}</span>',
    '            <span class="preview-text">{{ item.content }}</span>',
    "          </div>",
    "        </div>",
    '        <div class="panel-actions">',
    '          <button class="btn btn-ghost" @click="state.wizard.step = 1">上一步</button>',
    '          <button class="btn btn-primary" :disabled="!state.wizard.speaker" @click="state.wizard.step = 3">下一步</button>',
    "        </div>",
    "      </div>",

    '      <div class="panel" v-if="state.wizard.step === 3">',
    "        <h2>第 3 步 · TA 是谁？</h2>",
    '        <p class="muted">从发言人里挑一个作为要建模的对象（其余人的发言会作为「你」的上下文参与样例提取）。</p>',
    '        <div class="speaker-pick">',
    '          <button v-for="sp in batchSpeakers" :key="sp.name" class="pick-card" :class="{ active: state.wizard.speaker === sp.name }" @click="chooseSpeaker(sp.name)">',
    '            <div class="pick-name">{{ sp.name }}</div>',
    '            <div class="muted small">{{ sp.count }} 条消息</div>',
    "          </button>",
    "        </div>",
    '        <div class="form-grid">',
    '          <label class="field">人格名称<input class="input" v-model="state.wizard.name" placeholder="留空则使用发言人名字" /></label>',
    '          <label class="field">头像 emoji<input class="input" v-model="state.wizard.emoji" maxlength="4" /></label>',
    '          <label class="field">关系<select class="input" v-model="state.wizard.relation"><option v-for="r in relations" :key="r" :value="r">{{ r }}</option></select></label>',
    '          <label class="field">对你的称呼<input class="input" v-model="state.wizard.nickname" /></label>',
    "        </div>",
    '        <div class="panel-actions">',
    '          <button class="btn btn-ghost" @click="state.wizard.step = 2">上一步</button>',
    '          <button class="btn btn-primary" :disabled="!state.wizard.speaker || state.wizard.generating" @click="generatePersona">{{ state.wizard.generating ? \'生成中…\' : \'生成人格并保存\' }}</button>',
    "        </div>",
    "      </div>",

    '      <div class="panel" v-if="state.wizard.step === 4 && state.wizard.result">',
    "        <h2>第 4 步 · 人格已生成</h2>",
    '        <div class="persona-hero">',
    '          <div class="avatar avatar-xl">{{ state.wizard.result.avatar_emoji }}</div>',
    "          <div>",
    '            <div class="hero-name">{{ state.wizard.result.name }}</div>',
    '            <div class="tag-row">',
    '              <span class="tag tag-rel">{{ state.wizard.result.relation }}</span>',
    '              <span class="tag tag-import">导入生成</span>',
    "            </div>",
    '            <p class="muted">{{ state.wizard.result.summary_text }}</p>',
    "          </div>",
    "        </div>",
    '        <h3>风格滑块（启发式评分）</h3>',
    '        <div class="slider-preview">',
    '          <div class="sp-row" v-for="key in sliderKeys" :key="key">',
    '            <span class="sp-label">{{ sliderLabels[key] }}</span>',
    '            <div class="meter-bar"><div class="meter-fill" :style="{ width: ((state.wizard.result.sliders[key] || 0)) + \'%\' }"></div></div>',
    '            <span class="sp-val">{{ state.wizard.result.sliders[key] || 0 }}</span>',
    "          </div>",
    "        </div>",
    '        <h3>样例对话（{{ resultDialogues.length }} 组）</h3>',
    '        <div class="dlg-list">',
    '          <div class="dlg-item" v-for="(dlg, index) in resultDialogues" :key="index">',
    '            <div class="dlg-user">{{ dlg.user }}</div>',
    '            <div class="dlg-reply">{{ dlg.reply }}</div>',
    "          </div>",
    "        </div>",
    '        <h3>口癖高频片段</h3>',
    '        <div class="tag-row">',
    '          <span class="tag" v-for="phrase in resultPhrases" :key="phrase">{{ phrase }}</span>',
    '          <span class="muted small" v-if="!resultPhrases.length">样本太少，暂未提取出口癖</span>',
    "        </div>",
    '        <div class="panel-actions">',
    '          <button class="btn btn-ghost" @click="go(\'wall\')">返回角色墙</button>',
    '          <button class="btn btn-primary" @click="chatWith(state.wizard.result.id)">开始聊天</button>',
    "        </div>",
    "      </div>",
    "    </section>",

    /* ---------------- 角色卡 ---------------- */
    '    <section class="view" v-show="state.view === \'cards\'">',
    '      <header class="view-head">',
    "        <div>",
    "          <h1>角色卡</h1>",
    '          <p class="muted">兼容 SillyTavern 角色卡（V2/V3 JSON 与内嵌 PNG），可导入也可导出</p>',
    "        </div>",
    '        <div class="head-actions">',
    '          <button class="btn btn-ghost" @click="go(\'wall\')">返回角色墙</button>',
    "        </div>",
    "      </header>",

    '      <div class="panel">',
    "        <h2>导入角色卡</h2>",
    '        <p class="muted">选择 .json 或 .png 角色卡文件（PNG 会读取其中的 chara / ccv3 元数据）。解析在本地完成。</p>',
    '        <label class="upload-box">',
    '          <input type="file" accept=".json,.png,application/json,image/png" @change="onCardFileChange" />',
    '          <span class="upload-icon">🃏</span>',
    '          <span class="upload-text">{{ state.cards.pending ? state.cards.pending.name : \'点击选择角色卡文件\' }}</span>',
    '          <span class="muted small">支持 .json / .png</span>',
    "        </label>",
    '        <div class="muted" v-if="state.cards.parsing">正在解析角色卡…</div>',
    '        <div class="panel-actions" v-if="state.cards.pending">',
    '          <button class="btn btn-primary" :disabled="state.cards.importing || state.cards.parsing" @click="importCard">{{ state.cards.importing ? \'导入中…\' : \'导入为角色\' }}</button>',
    "        </div>",

    '        <div class="card-summary" v-if="state.cards.parseResult">',
    '          <div class="card-summary-head">',
    '            <h3>{{ state.cards.parseIsImport ? \'导入摘要\' : \'解析摘要\' }}</h3>',
    '            <span class="tag tag-import" v-if="state.cards.parseResult.spec">{{ state.cards.parseResult.spec }}{{ state.cards.parseResult.spec_version ? \' \' + state.cards.parseResult.spec_version : \'\' }}</span>',
    "          </div>",
    '          <div class="kv-grid">',
    '            <div class="kv"><span class="kv-k">来源格式</span><span class="kv-v">{{ state.cards.parseResult.source_format || \'—\' }}</span></div>',
    '            <div class="kv"><span class="kv-k">PNG 元数据键</span><span class="kv-v">{{ state.cards.parseResult.png_keyword || \'—\' }}</span></div>',
    '            <div class="kv"><span class="kv-k">问候语</span><span class="kv-v">{{ state.cards.parseResult.greeting_length || 0 }} 字</span></div>',
    '            <div class="kv"><span class="kv-k">样例对话</span><span class="kv-v">{{ state.cards.parseResult.sample_dialogue_count || 0 }} 组</span></div>',
    '            <div class="kv"><span class="kv-k">备选问候</span><span class="kv-v">{{ state.cards.parseResult.alternate_greeting_count || 0 }} 条</span></div>',
    '            <div class="kv"><span class="kv-k">世界书条目</span><span class="kv-v">{{ state.cards.parseResult.worldbook_entry_count || 0 }} 条{{ state.cards.parseResult.worldbook_saved ? \'（已保存）\' : \'\' }}</span></div>',
    "          </div>",
    '          <div class="tag-row" v-if="(state.cards.parseResult.fields_hit || []).length">',
    '            <span class="tag tag-import" v-for="f in state.cards.parseResult.fields_hit" :key="f">✓ {{ f }}</span>',
    "          </div>",
    '          <div class="tag-row" v-if="(state.cards.parseResult.fields_missing || []).length">',
    '            <span class="tag tag-manual" v-for="f in state.cards.parseResult.fields_missing" :key="f">✗ {{ f }}</span>',
    "          </div>",
    '          <div class="desens-card" v-if="state.cards.parseResult.desensitize">',
    '            <div class="desens-head">',
    '              <span class="desens-title">🔒 脱敏处理</span>',
    '              <span class="tag" :class="state.cards.parseResult.desensitize.enabled ? \'tag-import\' : \'tag-manual\'">{{ state.cards.parseResult.desensitize.enabled ? \'已启用\' : \'已关闭\' }}</span>',
    "            </div>",
    '            <p class="muted small">{{ desensTotalText(state.cards.parseResult) }}</p>',
    '            <div class="desens-grid">',
    '              <div class="desens-cell" v-for="row in desensRows(state.cards.parseResult)" :key="row.key">',
    '                <div class="desens-num">{{ row.count }}</div>',
    '                <div class="desens-label">{{ row.label }}</div>',
    "              </div>",
    "            </div>",
    '            <div class="desens-foot">',
    '              <span class="muted small">{{ desensDropText(state.cards.parseResult) }}</span>',
    '              <button class="btn btn-mini btn-ghost" v-if="state.cards.parseResult.desensitize.enabled" @click="disableDesensitize">关闭脱敏</button>',
    "            </div>",
    "          </div>",
    '          <ul class="warn-list" v-if="(state.cards.parseResult.warnings || []).length">',
    '            <li v-for="(w, i) in state.cards.parseResult.warnings" :key="i">{{ w }}</li>',
    "          </ul>",
    '          <div class="panel-actions" v-if="state.cards.parseIsImport">',
    '            <button class="btn btn-primary" @click="go(\'lore\')">去配置世界书</button>',
    '            <button class="btn btn-ghost" @click="go(\'wall\')">查看角色</button>',
    "          </div>",
    "        </div>",
    "      </div>",

    '      <div class="panel">',
    "        <h2>导出角色卡</h2>",
    '        <p class="muted">导出为 SillyTavern 可识别的 JSON 卡，或生成内嵌元数据的 PNG 卡。</p>',
    '        <div class="inline-form">',
    '          <select class="input input-sm" v-model.number="state.cards.personaId">',
    '            <option v-for="p in state.personas" :key="p.id" :value="p.id">{{ p.avatar_emoji }} {{ p.name }}</option>',
    "          </select>",
    '          <button class="btn btn-ghost" :disabled="state.cards.exporting === \'json\' || !state.personas.length" @click="exportCard(\'json\')">{{ state.cards.exporting === \'json\' ? \'导出中…\' : \'导出 JSON 卡\' }}</button>',
    '          <button class="btn btn-ghost" :disabled="state.cards.exporting === \'png\' || !state.personas.length" @click="exportCard(\'png\')">{{ state.cards.exporting === \'png\' ? \'导出中…\' : \'导出 PNG 卡\' }}</button>',
    "        </div>",
    '        <div class="empty-mini" v-if="!state.personas.length">还没有角色，先去角色墙创建或导入一个</div>',
    "      </div>",
    "    </section>",

    /* ---------------- 世界书 ---------------- */
    '    <section class="view" v-show="state.view === \'lore\'">',
    '      <header class="view-head">',
    "        <div>",
    "          <h1>世界书</h1>",
    '          <p class="muted">关键词触发的设定条目，命中后会按优先级注入到提示词中（Lorebook）</p>',
    "        </div>",
    '        <div class="head-actions">',
    '          <select class="input input-sm" :value="state.lore.personaId || \'\'" @change="onLorePersonaChange">',
    '            <option value="" disabled>选择角色</option>',
    '            <option v-for="p in state.personas" :key="p.id" :value="p.id">{{ p.avatar_emoji }} {{ p.name }}</option>',
    "          </select>",
    '          <button class="btn btn-primary" :disabled="!state.personas.length" @click="openLoreEditor(null)">＋ 新建条目</button>',
    "        </div>",
    "      </header>",

    '      <div class="panel">',
    "        <h2>条目列表</h2>",
    '        <div class="muted" v-if="state.lore.loading">加载中…</div>',
    '        <div class="lore-list" v-if="state.lore.entries.length">',
    '          <div class="lore-item" v-for="e in state.lore.entries" :key="e.id" :class="{ off: e.enabled === false }">',
    '            <div class="lore-top">',
    '              <div class="lore-keys">',
    '                <span class="tag tag-mini" v-for="k in e.keys" :key="k">{{ k }}</span>',
    '                <span class="tag tag-mini tag-const" v-if="e.constant">常驻</span>',
    '                <span class="muted small" v-if="!(e.keys || []).length && !e.constant">无关键词</span>',
    "              </div>",
    '              <div class="lore-actions">',
    '                <label class="switch">',
    '                  <input type="checkbox" :checked="e.enabled !== false" @change="toggleLoreEntry(e)" />',
    "                  <span></span>",
    "                </label>",
    '                <button class="icon-btn" title="编辑" @click="openLoreEditor(e)">✏️</button>',
    '                <button class="icon-btn" title="删除" @click="removeLoreEntry(e)">🗑</button>',
    "              </div>",
    "            </div>",
    '            <div class="lore-content">{{ e.content }}</div>',
    '            <div class="lore-meta">',
    '              <span class="tag tag-mini">优先级 {{ e.priority }}</span>',
    '              <span class="tag tag-mini">{{ lorePosLabel(e.position) }}{{ e.position === \'at_depth\' ? \' · 深度 \' + e.depth : \'\' }}</span>',
    '              <span class="tag tag-mini" v-if="e.token_budget">预算 {{ e.token_budget }}</span>',
    '              <span class="tag tag-mini" v-if="e.case_sensitive">区分大小写</span>',
    '              <span class="muted small" v-if="e.comment">{{ e.comment }}</span>',
    "            </div>",
    "          </div>",
    "        </div>",
    '        <div class="empty-mini" v-else>还没有世界书条目。写一条「当提到 XX 时，TA 的背景是…」，让角色记得更多设定。</div>',
    "      </div>",

    '      <div class="panel">',
    "        <h2>命中测试</h2>",
    '        <p class="muted">输入一段话，预览哪些条目会被触发、实际占用多少 token 预算。</p>',
    '        <textarea class="input" rows="3" v-model="state.lore.previewText" placeholder="例如：周末一起去海边看日落吧"></textarea>',
    '        <div class="inline-form">',
    '          <label class="field field-inline">Token 预算<input class="input input-sm" type="number" min="0" v-model.number="state.lore.previewBudget" placeholder="0 = 用全局设置" /></label>',
    '          <button class="btn btn-primary" :disabled="state.lore.previewLoading" @click="runLorePreview">{{ state.lore.previewLoading ? \'测试中…\' : \'开始测试\' }}</button>',
    "        </div>",
    '        <div class="preview-stats" v-if="state.lore.preview">',
    '          <div class="stat-cell"><div class="stat-num">{{ state.lore.preview.stats.candidates }}</div><div class="stat-label">候选</div></div>',
    '          <div class="stat-cell"><div class="stat-num">{{ state.lore.preview.stats.injected }}</div><div class="stat-label">命中注入</div></div>',
    '          <div class="stat-cell"><div class="stat-num">{{ state.lore.preview.stats.used }}</div><div class="stat-label">消耗 token</div></div>',
    '          <div class="stat-cell"><div class="stat-num">{{ state.lore.preview.stats.budget }}</div><div class="stat-label">预算</div></div>',
    '          <div class="stat-cell"><div class="stat-num">{{ state.lore.preview.stats.skipped_budget.length }}</div><div class="stat-label">超预算跳过</div></div>',
    "        </div>",
    '        <div class="hit-list" v-if="state.lore.preview && (state.lore.preview.items || []).length">',
    '          <div class="hit-item" v-for="it in state.lore.preview.items" :key="it.entry_id">',
    '            <div class="hit-head">',
    '              <span class="tag tag-mini tag-import">命中</span>',
    '              <span class="tag tag-mini tag-const" v-if="it.constant">常驻</span>',
    '              <span class="tag tag-mini" v-for="k in (it.matched_keys || [])" :key="k">{{ k }}</span>',
    '              <span class="muted small">优先级 {{ it.priority }} · 约 {{ it.cost }} token</span>',
    "            </div>",
    '            <div class="lore-content">{{ it.content }}</div>',
    "          </div>",
    "        </div>",
    '        <div class="empty-mini" v-if="state.lore.preview && !(state.lore.preview.items || []).length">没有条目被命中</div>',
    "      </div>",
    "    </section>",

    /* ---------------- 备份 ---------------- */
    '    <section class="view" v-show="state.view === \'backup\'">',
    '      <header class="view-head">',
    "        <div>",
    "          <h1>备份与恢复</h1>",
    '          <p class="muted">导出全量数据为 JSON；恢复时可按策略合并或跳过已存在的数据</p>',
    "        </div>",
    '        <div class="head-actions">',
    '          <button class="btn btn-ghost" @click="go(\'settings\')">去设置</button>',
    "        </div>",
    "      </header>",

    '      <div class="panel">',
    "        <h2>导出备份</h2>",
    '        <p class="muted">包含角色、会话、消息、长期记忆、世界书与设置。导出文件请妥善保管。</p>',
    '        <div class="panel-actions">',
    '          <button class="btn btn-primary" :disabled="state.backup.exporting" @click="exportBackup">{{ state.backup.exporting ? \'导出中…\' : \'一键导出备份\' }}</button>',
    "        </div>",
    "      </div>",

    '      <div class="panel">',
    "        <h2>从备份恢复</h2>",
    '        <div class="form-grid">',
    '          <label class="field">冲突策略',
    '            <select class="input" v-model="state.backup.strategy">',
    '              <option v-for="(label, key) in backupStrategies" :key="key" :value="key">{{ label }}</option>',
    "            </select>",
    "          </label>",
    "        </div>",
    '        <label class="upload-box">',
    '          <input type="file" accept=".json,application/json" @change="onBackupFileChange" />',
    '          <span class="upload-icon">📦</span>',
    '          <span class="upload-text">点击选择备份文件</span>',
    '          <span class="muted small">.json 备份文件</span>',
    "        </label>",
    '        <div class="muted" v-if="state.backup.importing">正在恢复…</div>',
    '        <div class="backup-result" v-if="state.backup.result">',
    '          <div class="tag-row">',
    '            <span class="tag tag-import">策略 {{ state.backup.result.strategy }}</span>',
    '            <span class="tag">新增 {{ backupCount(state.backup.result.created) }}</span>',
    '            <span class="tag">跳过 {{ backupCount(state.backup.result.skipped) }}</span>',
    '            <span class="tag" v-if="backupCount(state.backup.result.remapped)">重编号 {{ backupCount(state.backup.result.remapped) }}</span>',
    "          </div>",
    '          <div class="kv-grid" v-if="backupDetail(state.backup.result.created)">',
    '            <div class="kv"><span class="kv-k">新增明细</span><span class="kv-v">{{ backupDetail(state.backup.result.created) }}</span></div>',
    '            <div class="kv" v-if="backupDetail(state.backup.result.skipped)"><span class="kv-k">跳过明细</span><span class="kv-v">{{ backupDetail(state.backup.result.skipped) }}</span></div>',
    "          </div>",
    '          <ul class="warn-list" v-if="(state.backup.result.warnings || []).length">',
    '            <li v-for="(w, i) in state.backup.result.warnings" :key="i">{{ w }}</li>',
    "          </ul>",
    "        </div>",
    "      </div>",
    "    </section>",

    /* ---------------- 聊天 ---------------- */
    '    <section class="view view-chat" v-show="state.view === \'chat\'">',
    '      <div class="banner" v-if="isDemoMode">',
    '        <span>当前为演示模式（mock 模型），可在设置中配置真实模型</span>',
    '        <button class="btn btn-mini" @click="go(\'settings\')">去设置</button>',
    "      </div>",

    '      <div class="chat-layout" :class="{ \'with-memory\': state.memorySideOpen }">',

    '        <aside class="col sess-col">',
    '          <div class="col-head">',
    "            <span>会话</span>",
    '            <button class="btn btn-mini btn-primary" @click="createSession">＋ 新建</button>',
    "          </div>",
    '          <div class="sess-list">',
    '            <div class="sess-item" v-for="s in chatSessions" :key="s.id" :class="{ active: s.id === state.activeSessionId }" @click="switchSession(s.id)">',
    '              <div class="avatar avatar-sm">{{ s.persona_emoji }}</div>',
    '              <div class="sess-body">',
    '                <div class="sess-title">{{ s.title }}</div>',
    '                <div class="sess-last">{{ s.last_message || \'还没有消息\' }}</div>',
    "              </div>",
    '              <button class="icon-btn" title="删除会话" @click.stop="removeSession(s.id)">🗑</button>',
    "            </div>",
    '            <div class="empty-mini" v-if="!chatSessions.length">还没有会话，点「＋ 新建」开始</div>',
    "          </div>",
    '          <div class="col-foot">',
    '            <select class="input input-sm" :value="state.activePersonaId || \'\'" @change="onPersonaSwitch">',
    '              <option value="" disabled>选择角色</option>',
    '              <option v-for="p in state.personas" :key="p.id" :value="p.id">{{ p.avatar_emoji }} {{ p.name }}</option>',
    "            </select>",
    "          </div>",
    "        </aside>",

    '        <div class="col chat-col">',
    '          <header class="chat-head" v-if="activeSession">',
    '            <div class="chat-who">',
    '              <div class="avatar avatar-sm">{{ activeSession.persona_emoji }}</div>',
    "              <div>",
    '                <div class="chat-name">{{ activeSession.persona_name }}</div>',
    '                <div class="muted small">{{ activeSession.message_count }} 条消息 · {{ activeSession.summary ? \'已生成会话摘要\' : \'暂无摘要\' }}</div>',
    "              </div>",
    "            </div>",
    '            <div class="meters">',
    '              <div class="meter">',
    '                <span class="meter-label">心情</span>',
    '                <div class="meter-bar"><div class="meter-fill mood" :style="{ width: (activeSession.mood || 0) + \'%\' }"></div></div>',
    '                <span class="meter-val">{{ activeSession.mood }}</span>',
    "              </div>",
    '              <div class="meter">',
    '                <span class="meter-label">好感</span>',
    '                <div class="meter-bar"><div class="meter-fill affection" :style="{ width: (activeSession.affection || 0) + \'%\' }"></div></div>',
    '                <span class="meter-val">{{ activeSession.affection }}</span>',
    "              </div>",
    "            </div>",
    '            <button class="btn btn-ghost btn-sm" @click="state.memorySideOpen = !state.memorySideOpen">{{ state.memorySideOpen ? \'收起记忆\' : \'记忆侧栏\' }}</button>',
    "          </header>",

    '          <div class="msgs">',
    '            <div class="alert alert-warn" v-for="(notice, index) in state.notices" :key="index">{{ notice.message }}</div>',
    '            <div class="alert alert-error" v-if="state.streamError">{{ state.streamError }}</div>',
    '            <div class="msg" v-for="msg in state.messages" :key="msg.id" :class="msg.role === \'user\' ? \'msg-user\' : \'msg-ai\'">',
    '              <div class="bubble" @click="onMarkdownClick">',
    '                <div class="bubble-text md" v-html="renderMarkdown(msg.content)"></div>',
    '                <span class="caret" v-if="msg.pending"></span>',
    "              </div>",
    '              <div class="msg-ops" v-if="!msg.pending">',
    '                <span class="msg-time">{{ fmtClock(msg.created_at) }}</span>',
    '                <template v-if="msg.role === \'assistant\'">',
    '                  <button class="op" :class="{ on: msg.feedback === 1 }" title="点赞" @click="sendFeedback(msg, \'like\')">👍</button>',
    '                  <button class="op" :class="{ on: msg.feedback === -1 }" title="踩" @click="sendFeedback(msg, \'dislike\')">👎</button>',
    '                  <button class="op" title="改写这条回复" @click="openRewrite(msg)">✏️</button>',
    '                  <button class="op" v-if="isLastAssistant(msg)" title="重新生成" @click="regenerateMessage(msg)">🔄</button>',
    '                  <button class="op" title="复制" @click="copyMessage(msg)">📋</button>',
    '                  <span class="tag tag-mini" v-if="msg.rewritten">已改写</span>',
    "                </template>",
    "                <template v-else>",
    '                  <button class="op" title="编辑后重发" @click="openEditMessage(msg)">✏️</button>',
    '                  <button class="op" title="复制" @click="copyMessage(msg)">📋</button>',
    '                  <span class="tag tag-mini" v-if="msg.edited">已编辑</span>',
    "                </template>",
    "              </div>",
    "            </div>",
    '            <div class="empty-mini" v-if="!state.messages.length">还没有消息，先在下面说点什么吧</div>',
    "          </div>",

    '          <footer class="composer">',
    '            <textarea class="input composer-input" rows="2" v-model="state.inputText" placeholder="说点什么…（Enter 发送 / Shift+Enter 换行）" @keydown="onComposerKeydown"></textarea>',
    '            <div class="composer-actions">',
    '              <button class="btn btn-ghost" v-if="state.streaming" @click="stopGeneration">停止生成</button>',
    '              <button class="btn btn-primary" :disabled="state.streaming || !canSend" @click="sendMessage">{{ state.streaming ? \'生成中…\' : \'发送\' }}</button>',
    "            </div>",
    "          </footer>",
    "        </div>",

    '        <aside class="col mem-col" v-show="state.memorySideOpen">',
    '          <div class="col-head">',
    "            <span>长期记忆</span>",
    '            <button class="btn btn-mini" @click="loadChatMemories">刷新</button>',
    "          </div>",
    '          <div class="mem-list">',
    '            <div class="mem-item" v-for="m in state.chatMemories" :key="m.id">',
    '              <div class="mem-content">{{ m.content }}</div>',
    '              <div class="mem-meta">',
    '                <span class="tag tag-mini">{{ kindLabel(m.kind) }}</span>',
    '                <span class="muted small">重要度 {{ fmtImportance(m.importance) }}</span>',
    '                <span class="muted small">命中 {{ m.access_count }} 次</span>',
    '                <button class="icon-btn" title="删除记忆" @click="removeMemory(m.id, true)">🗑</button>',
    "              </div>",
    "            </div>",
    '            <div class="empty-mini" v-if="!state.chatMemories.length">还没有长期记忆。多聊几轮，TA 会自己记住你的事。</div>',
    "          </div>",
    "        </aside>",
    "      </div>",
    "    </section>",

    /* ---------------- 人设编辑 ---------------- */
    '    <section class="view" v-show="state.view === \'persona\'">',
    '      <header class="view-head">',
    "        <div>",
    "          <h1>人设编辑</h1>",
    '          <p class="muted">调整参数后右侧会实时预览最终注入模型的 system prompt</p>',
    "        </div>",
    '        <div class="head-actions">',
    '          <select class="input input-sm" :value="state.personaForm.id === null ? \'\' : state.personaForm.id" @change="onPersonaFormSwitch">',
    '            <option value="">＋ 新建人格</option>',
    '            <option v-for="p in state.personas" :key="p.id" :value="p.id">{{ p.avatar_emoji }} {{ p.name }}</option>',
    "          </select>",
    '          <button class="btn btn-primary" :disabled="state.personaForm.saving" @click="savePersona">{{ state.personaForm.saving ? \'保存中…\' : \'保存\' }}</button>',
    "        </div>",
    "      </header>",

    '      <div class="editor-layout">',
    '        <div class="editor-main">',
    '          <div class="panel">',
    "            <h3>基础信息</h3>",
    '            <div class="form-grid">',
    '              <label class="field">名称<input class="input" v-model="state.personaForm.name" placeholder="例如 林晚" /></label>',
    '              <label class="field">头像 emoji<input class="input" v-model="state.personaForm.avatar_emoji" maxlength="4" /></label>',
    '              <label class="field">关系<select class="input" v-model="state.personaForm.relation"><option v-for="r in relations" :key="r" :value="r">{{ r }}</option></select></label>',
    '              <label class="field">对你的称呼<input class="input" v-model="state.personaForm.nickname_for_user" /></label>',
    "            </div>",
    '            <div class="emoji-row">',
    '              <button v-for="emoji in emojiChoices" :key="emoji" class="emoji-btn" :class="{ on: state.personaForm.avatar_emoji === emoji }" @click="state.personaForm.avatar_emoji = emoji">{{ emoji }}</button>',
    "            </div>",
    "          </div>",

    '          <div class="panel">',
    "            <h3>风格滑块</h3>",
    '            <div class="slider-row" v-for="key in sliderKeys" :key="key">',
    '              <span class="sp-label">{{ sliderLabels[key] }}</span>',
    '              <input type="range" min="0" max="100" class="range" v-model.number="state.personaForm.sliders[key]" />',
    '              <span class="sp-val">{{ state.personaForm.sliders[key] }}</span>',
    "            </div>",
    '            <p class="muted small">数值越高，对应性格特征在提示词中的权重越强。</p>',
    "          </div>",

    '          <div class="panel">',
    "            <h3>高级设置</h3>",
    '            <label class="field">口癖（逗号分隔）<input class="input" v-model="state.personaForm.phrases" placeholder="嗯嗯, 其实吧, 慢慢来" /></label>',
    '            <label class="field">人设补充描述<textarea class="input" rows="3" v-model="state.personaForm.description" placeholder="例如：习惯在深夜聊天，语速慢，先肯定对方再给建议"></textarea></label>',
    '            <label class="field">开场白<textarea class="input" rows="2" v-model="state.personaForm.greeting" placeholder="新建会话时 TA 说的第一句话"></textarea></label>',
    '            <div class="tag-row" v-if="state.personaForm.sample_dialogues.length">',
    '              <span class="tag">已有 {{ state.personaForm.sample_dialogues.length }} 组样例对话（导入生成时保留）</span>',
    "            </div>",
    "          </div>",
    "        </div>",

    '        <div class="editor-preview">',
    '          <div class="panel panel-prompt">',
    "            <h3>System Prompt 实时预览</h3>",
    '            <pre class="prompt">{{ state.previewPrompt || \'（预览生成中…）\' }}</pre>',
    '            <div class="muted small">预览按心情 72 / 好感 58 与两条示例记忆组装，仅用于查看效果，不影响真实对话。</div>',
    "          </div>",
    "        </div>",
    "      </div>",
    "    </section>",

    /* ---------------- 记忆库 ---------------- */
    '    <section class="view" v-show="state.view === \'memory\'">',
    '      <header class="view-head">',
    "        <div>",
    "          <h1>记忆库</h1>",
    '          <p class="muted">记忆按人格隔离；召回得分 = 词法相似度 × 时间衰减 × 重要度</p>',
    "        </div>",
    '        <div class="head-actions">',
    '          <select class="input input-sm" :value="state.memFilterPersonaId || \'\'" @change="onMemFilterChange">',
    '            <option value="0">全部人格</option>',
    '            <option v-for="p in state.personas" :key="p.id" :value="p.id">{{ p.avatar_emoji }} {{ p.name }}</option>',
    "          </select>",
    '          <button class="btn btn-primary" @click="startAddMemory" :disabled="!state.personas.length">＋ 新增记忆</button>',
    "        </div>",
    "      </header>",

    '      <div class="panel" v-if="state.memEditId !== null">',
    '        <h3>{{ state.memEditId ? \'编辑记忆\' : \'新增记忆\' }}</h3>',
    '        <div class="form-grid">',
    '          <label class="field">人格<select class="input" v-model.number="state.memForm.persona_id" :disabled="!!state.memEditId"><option v-for="p in state.personas" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>',
    '          <label class="field">类型<select class="input" v-model="state.memForm.kind"><option v-for="kind in memoryKinds" :key="kind" :value="kind">{{ kindLabel(kind) }}</option></select></label>',
    '          <label class="field">重要度（0~1）<input class="input" type="number" step="0.05" min="0" max="1" v-model.number="state.memForm.importance" /></label>',
    '          <label class="field span-2">内容<textarea class="input" rows="2" v-model="state.memForm.content" placeholder="例如：用户喜欢在深夜聊天"></textarea></label>',
    "        </div>",
    '        <div class="panel-actions">',
    '          <button class="btn btn-ghost" @click="cancelMemoryEdit">取消</button>',
    '          <button class="btn btn-primary" :disabled="!state.memForm.content.trim()" @click="submitMemory">保存</button>',
    "        </div>",
    "      </div>",

    '      <div class="panel">',
    "        <h3>记忆列表（{{ state.memories.length }} 条）</h3>",
    '        <table class="table">',
    "          <thead><tr><th>内容</th><th>类型</th><th>重要度</th><th>创建时间</th><th>命中</th><th>操作</th></tr></thead>",
    "          <tbody>",
    '            <tr v-for="m in state.memories" :key="m.id">',
    '              <td class="cell-content">{{ m.content }}</td>',
    '              <td><span class="tag tag-mini">{{ kindLabel(m.kind) }}</span></td>',
    "              <td>{{ fmtImportance(m.importance) }}</td>",
    '              <td class="muted small">{{ fmtTime(m.created_at) }}</td>',
    '              <td class="muted small">{{ m.access_count }}</td>',
    '              <td class="row-ops">',
    '                <button class="btn btn-mini" @click="startEditMemory(m)">编辑</button>',
    '                <button class="btn btn-mini btn-danger" @click="removeMemory(m.id, false)">删除</button>',
    "              </td>",
    "            </tr>",
    '            <tr v-if="!state.memories.length"><td colspan="6" class="muted">暂无记忆，聊天几轮后 TA 会自动总结</td></tr>',
    "          </tbody>",
    "        </table>",
    "      </div>",

    '      <div class="panel">',
    "        <h3>记忆检索测试</h3>",
    '        <div class="search-row">',
    '          <input class="input" v-model="state.memTestQuery" placeholder="输入一句话，看看会召回哪些记忆" @keydown.enter="runMemoryTest" />',
    '          <select class="input input-sm" v-model.number="state.memTestPersonaId"><option v-for="p in state.personas" :key="p.id" :value="p.id">{{ p.name }}</option></select>',
    '          <button class="btn btn-primary" :disabled="state.memTestLoading || !state.memTestQuery.trim()" @click="runMemoryTest">{{ state.memTestLoading ? \'检索中…\' : \'测试召回\' }}</button>',
    "        </div>",
    '        <div v-if="state.memTestResult">',
    '          <p class="muted small">查询「{{ state.memTestResult.query }}」命中 {{ state.memTestResult.count }} 条</p>',
    '          <div class="mem-item" v-for="item in state.memTestResult.items" :key="item.memory.id">',
    '            <div class="mem-content">{{ item.memory.content }}</div>',
    '            <div class="mem-meta">',
    '              <span class="tag tag-mini">{{ kindLabel(item.memory.kind) }}</span>',
    '              <span class="muted small">得分 {{ item.score }}</span>',
    "            </div>",
    "          </div>",
    '          <div class="empty-mini" v-if="!state.memTestResult.count">没有召回结果，试试更贴近记忆内容的说法</div>',
    "        </div>",
    "      </div>",
    "    </section>",

    /* ---------------- 设置 ---------------- */
    '    <section class="view" v-show="state.view === \'settings\'">',
    '      <header class="view-head">',
    "        <div>",
    "          <h1>设置</h1>",
    '          <p class="muted">不填任何 API Key 也能完整体验（mock 演示模式）；配置保存在本地数据库，仅本机生效</p>',
    "        </div>",
    "      </header>",

    '      <div class="panel" v-if="state.settingsForm">',
    "        <h3>模型接入</h3>",
    '        <div class="form-grid">',
    '          <label class="field">提供方<select class="input" v-model="state.settingsForm.llm_provider"><option v-for="provider in providers" :key="provider" :value="provider">{{ providerLabel(provider) }}</option></select></label>',
    '          <label class="field">Base URL<input class="input" v-model="state.settingsForm.llm_base_url" placeholder="https://api.openai.com/v1 或 http://localhost:11434" /></label>',
    '          <label class="field">API Key<input class="input" type="password" name="llm_api_key" autocomplete="new-password" v-model="state.settingsForm.llm_api_key" :placeholder="state.settings.llm_api_key_set ? \'已配置（保持掩码表示不修改）\' : \'未配置，可留空\'" /></label>',
    '          <label class="field">模型名<input class="input" v-model="state.settingsForm.llm_model" placeholder="gpt-4o-mini / qwen2.5:7b" /></label>',
    '          <label class="field">温度<input class="input" type="number" step="0.1" min="0" max="2" v-model.number="state.settingsForm.llm_temperature" /></label>',
    '          <label class="field">记忆召回条数<input class="input" type="number" min="1" v-model.number="state.settingsForm.memory_top_k" /></label>',
    '          <label class="field">最近对话窗口<input class="input" type="number" min="1" v-model.number="state.settingsForm.recent_window" /></label>',
    '          <label class="field">记忆反思间隔（条）<input class="input" type="number" min="1" v-model.number="state.settingsForm.reflect_every" /></label>',
    "        </div>",
    "        <h3>世界书（Lorebook）</h3>",
    '        <div class="form-grid">',
    '          <label class="field field-check">',
    '            <span class="check-line"><input type="checkbox" v-model="state.settingsForm.lore_enabled" /> 启用世界书注入</span>',
    '            <span class="muted small">关闭后所有条目都不会注入到对话中</span>',
    "          </label>",
    '          <label class="field">注入 Token 预算<input class="input" type="number" min="0" v-model.number="state.settingsForm.lore_budget" /></label>',
    '          <label class="field">扫描窗口（条消息）<input class="input" type="number" min="1" v-model.number="state.settingsForm.lore_scan_window" /></label>',
    "        </div>",
    '        <p class="muted small">世界书条目在「世界书」页维护；这里控制全局开关与预算上限。</p>',
    '        <div class="panel-actions">',
    '          <span class="save-hint" v-if="state.settingsSaved">已保存 ✓</span>',
    '          <button class="btn btn-ghost" @click="go(\'lore\')">去维护世界书</button>',
    '          <button class="btn btn-primary" :disabled="state.settingsSaving" @click="saveSettings">{{ state.settingsSaving ? \'保存中…\' : \'保存配置\' }}</button>',
    "        </div>",
    "      </div>",

    '      <div class="panel" id="panel-desens" v-if="state.settingsForm">',
    "        <h3>隐私与脱敏</h3>",
    '        <div class="form-grid">',
    '          <label class="field field-check">',
    '            <span class="check-line"><input type="checkbox" v-model="state.settingsForm.desensitize_enabled" /> 导入时自动脱敏</span>',
    '            <span class="muted small">替换手机号 / 身份证 / 邮箱 / 银行卡 / 链接 / IP / QQ 号</span>',
    "          </label>",
    "        </div>",
    '        <label class="field">敏感词黑名单（每行一个 / 逗号分隔，命中整条消息丢弃）',
    '          <textarea class="input" rows="4" v-model="state.settingsForm.desensitize_blacklist" placeholder="例如：&#10;某某公司&#10;家庭住址"></textarea>',
    "        </label>",
    '        <div class="panel-actions">',
    '          <span class="save-hint" v-if="state.settingsSaved">已保存 ✓</span>',
    '          <button class="btn btn-ghost" @click="loadSettings">重新读取</button>',
    '          <button class="btn btn-primary" :disabled="state.settingsSaving" @click="saveSettings">{{ state.settingsSaving ? \'保存中…\' : \'保存配置\' }}</button>',
    "        </div>",
    "      </div>",

    '      <div class="panel">',
    "        <h3>当前状态</h3>",
    '        <div class="kv-list">',
    '          <div class="kv"><span>运行模式</span><b>{{ isDemoMode ? \'演示模式（mock，无需 Key）\' : \'真实模型\' }}</b></div>',
    '          <div class="kv"><span>API Key</span><b>{{ state.settings.llm_api_key_masked || \'未配置\' }}</b></div>',
    '          <div class="kv"><span>数据库</span><b>backend/data/cyber_gf.db（SQLite，本地）</b></div>',
    '          <div class="kv"><span>模型名</span><b>{{ state.settings.llm_model || \'—\' }}</b></div>',
    "        </div>",
    '        <p class="muted small">提示：openai 模式填写任意 OpenAI 兼容网关（含 base_url 与模型名）；ollama 模式填 http://localhost:11434 与本地已拉取的模型名。未配置完整时会自动降级为 mock，保证对话不中断。</p>',
    "      </div>",
    "    </section>",
    "  </main>",

    /* ---------------- 新建人格弹窗 ---------------- */
    '  <div class="modal-mask" v-if="state.createVisible" @click.self="state.createVisible = false">',
    '    <div class="modal">',
    '      <div class="modal-head"><h3>新建人格</h3><button class="icon-btn" @click="state.createVisible = false">✕</button></div>',
    '      <div class="modal-body">',
    '        <label class="field">名称<input class="input" v-model="state.createForm.name" placeholder="例如 阿离" /></label>',
    '        <div class="form-grid">',
    '          <label class="field">头像 emoji<input class="input" v-model="state.createForm.avatar_emoji" maxlength="4" /></label>',
    '          <label class="field">关系<select class="input" v-model="state.createForm.relation"><option v-for="r in relations" :key="r" :value="r">{{ r }}</option></select></label>',
    "        </div>",
    '        <label class="field">对你的称呼<input class="input" v-model="state.createForm.nickname_for_user" /></label>',
    '        <label class="field">开场白<textarea class="input" rows="2" v-model="state.createForm.greeting" placeholder="留空则自动生成"></textarea></label>',
    '        <div class="emoji-row">',
    '          <button v-for="emoji in emojiChoices" :key="emoji" class="emoji-btn" :class="{ on: state.createForm.avatar_emoji === emoji }" @click="state.createForm.avatar_emoji = emoji">{{ emoji }}</button>',
    "        </div>",
    "      </div>",
    '      <div class="modal-foot">',
    '        <button class="btn btn-ghost" @click="state.createVisible = false">取消</button>',
    '        <button class="btn btn-primary" :disabled="state.createSaving" @click="submitCreatePersona">{{ state.createSaving ? \'创建中…\' : \'创建并进入人设编辑\' }}</button>',
    "      </div>",
    "    </div>",
    "  </div>",

    /* ---------------- 改写弹窗 ---------------- */
    '  <div class="modal-mask" v-if="state.rewriteVisible" @click.self="state.rewriteVisible = false">',
    '    <div class="modal">',
    '      <div class="modal-head"><h3>改写这条回复</h3><button class="icon-btn" @click="state.rewriteVisible = false">✕</button></div>',
    '      <div class="modal-body">',
    '        <p class="muted small">改写内容会覆盖该条 AI 消息，并作为「偏好样本」记录，用于后续让 TA 越来越贴合你。</p>',
    '        <textarea class="input" rows="6" v-model="state.rewriteText"></textarea>',
    "      </div>",
    '      <div class="modal-foot">',
    '        <button class="btn btn-ghost" @click="state.rewriteVisible = false">取消</button>',
    '        <button class="btn btn-primary" :disabled="state.rewriteSaving" @click="submitRewrite">{{ state.rewriteSaving ? \'提交中…\' : \'确认改写\' }}</button>',
    "      </div>",
    "    </div>",
    "  </div>",

    /* ---------------- 消息编辑后重发弹窗 ---------------- */
    '  <div class="modal-mask" v-if="state.editVisible" @click.self="closeEditMessage">',
    '    <div class="modal">',
    '      <div class="modal-head"><h3>编辑后重发</h3><button class="icon-btn" @click="closeEditMessage">✕</button></div>',
    '      <div class="modal-body">',
    '        <p class="muted small">修改后将以此内容重新提问，并生成一条新的回复。</p>',
    '        <textarea class="input" rows="5" v-model="state.editText"></textarea>',
    "      </div>",
    '      <div class="modal-foot">',
    '        <button class="btn btn-ghost" @click="closeEditMessage">取消</button>',
    '        <button class="btn btn-primary" @click="submitEditMessage">重发</button>',
    "      </div>",
    "    </div>",
    "  </div>",

    /* ---------------- 世界书条目编辑弹窗 ---------------- */
    '  <div class="modal-mask" v-if="state.lore.editVisible" @click.self="closeLoreEditor">',
    '    <div class="modal modal-wide">',
    '      <div class="modal-head"><h3>{{ state.lore.editing && state.lore.editing.id ? \'编辑世界书条目\' : \'新建世界书条目\' }}</h3><button class="icon-btn" @click="closeLoreEditor">✕</button></div>',
    '      <div class="modal-body" v-if="state.lore.editing">',
    '        <label class="field">触发关键词（逗号分隔）<input class="input" v-model="state.lore.editing.keys" placeholder="海边, 日落, 夏天" /></label>',
    '        <label class="field">条目内容<textarea class="input" rows="4" v-model="state.lore.editing.content" placeholder="当命中时注入给模型的设定描述"></textarea></label>',
    '        <div class="form-grid">',
    '          <label class="field">注入位置',
    '            <select class="input" v-model="state.lore.editing.position">',
    '              <option v-for="(label, key) in lorePositions" :key="key" :value="key">{{ label }}</option>',
    "            </select>",
    "          </label>",
    '          <label class="field">优先级（越大越先注入）<input class="input" type="number" v-model.number="state.lore.editing.priority" /></label>',
    '          <label class="field">深度（at_depth 时生效）<input class="input" type="number" min="0" v-model.number="state.lore.editing.depth" /></label>',
    '          <label class="field">单条 Token 预算（0 = 不限）<input class="input" type="number" min="0" v-model.number="state.lore.editing.token_budget" /></label>',
    "        </div>",
    '        <div class="switch-row">',
    '          <label class="check"><input type="checkbox" v-model="state.lore.editing.enabled" /> 启用</label>',
    '          <label class="check"><input type="checkbox" v-model="state.lore.editing.constant" /> 常驻（无需关键词）</label>',
    '          <label class="check"><input type="checkbox" v-model="state.lore.editing.case_sensitive" /> 区分大小写</label>',
    "        </div>",
    '        <label class="field">备注<input class="input" v-model="state.lore.editing.comment" placeholder="可选" /></label>',
    "      </div>",
    '      <div class="modal-foot">',
    '        <button class="btn btn-ghost" @click="closeLoreEditor">取消</button>',
    '        <button class="btn btn-primary" :disabled="state.lore.saving" @click="saveLoreEntry">{{ state.lore.saving ? \'保存中…\' : \'保存\' }}</button>',
    "      </div>",
    "    </div>",
    "  </div>",
    "</div>"
  ].join("\n");

  /* ======================================================================
   * 7. 应用装配
   * ==================================================================== */
  var app = Vue.createApp({
    setup: function () {
      var activePersona = computed(function () {
        return (
          state.personas.find(function (item) {
            return item.id === state.activePersonaId;
          }) || null
        );
      });

      var activeSession = computed(function () {
        return (
          state.sessions.find(function (item) {
            return item.id === state.activeSessionId;
          }) || null
        );
      });

      var chatSessions = computed(function () {
        return state.sessions.filter(function (item) {
          return !state.activePersonaId || item.persona_id === state.activePersonaId;
        });
      });

      var batchSpeakers = computed(function () {
        var batch = state.wizard.batch;
        if (!batch) return [];
        return (batch.speakers || []).slice().sort(function (a, b) {
          return (b.count || 0) - (a.count || 0);
        });
      });

      var resultCard = computed(function () {
        var result = state.wizard.result;
        return (result && result.persona_card) || {};
      });

      var resultDialogues = computed(function () {
        return (resultCard.value.sample_dialogues || []).slice(0, 12);
      });

      var resultPhrases = computed(function () {
        return (resultCard.value.top_phrases || []).slice(0, 12);
      });

      var isDemoMode = computed(function () {
        return !!(state.settings.demo_mode || state.meta.demo_mode);
      });

      var canSend = computed(function () {
        return !!(state.inputText || "").trim() && !!state.activeSessionId;
      });

      function traitTags(persona) {
        var sliders = persona.sliders || {};
        var picked = SLIDER_KEYS.filter(function (key) {
          return Number(sliders[key] || 0) >= 60;
        });
        if (!picked.length) {
          picked = SLIDER_KEYS.slice()
            .sort(function (a, b) {
              return Number(sliders[b] || 0) - Number(sliders[a] || 0);
            })
            .slice(0, 2);
        }
        return picked.slice(0, 3);
      }

      function sampleCountText(persona) {
        var card = persona.persona_card || {};
        var count = Number(card.message_count || 0);
        return count > 0 ? "样本 " + count + " 条" : "新人格";
      }

      function onMemFilterChange(event) {
        state.memFilterPersonaId = Number(event.target.value) || 0;
        loadMemories();
      }

      /* 人设表单变化 → 防抖刷新提示词预览 */
      watch(
        function () {
          return JSON.stringify(state.personaForm);
        },
        function (value, oldValue) {
          if (value === oldValue) return;
          if (state.view !== "persona") return;
          schedulePreview();
        }
      );

      /* 首屏启动 */
      function boot() {
        Api.get("/api/meta")
          .then(function (meta) {
            state.meta = meta || {};
          })
          .catch(function () {
            /* 元信息非关键，忽略 */
          })
          .then(loadSettings)
          .then(loadPersonas)
          .then(function () {
            if (!location.hash || location.hash === "#") {
              location.hash = "#/wall";
            }
            handleHash();
            window.addEventListener("hashchange", handleHash);
            state.ready = true;
          });
      }

      boot();

      return {
        state: state,
        navItems: NAV_ITEMS,
        sliderKeys: SLIDER_KEYS,
        sliderLabels: SLIDER_LABELS,
        memoryKinds: MEMORY_KINDS,
        relations: RELATIONS,
        providers: PROVIDERS,
        emojiChoices: EMOJI_CHOICES,
        wizardSteps: WIZARD_STEPS,
        formatHelp: FORMAT_HELP,

        activePersona: activePersona,
        activeSession: activeSession,
        chatSessions: chatSessions,
        batchSpeakers: batchSpeakers,
        resultDialogues: resultDialogues,
        resultPhrases: resultPhrases,
        isDemoMode: isDemoMode,
        canSend: canSend,

        go: go,
        chatWith: chatWith,
        editPersona: editPersona,
        openMemoryFor: openMemoryFor,
        removePersona: removePersona,

        loadPersonas: loadPersonas,
        openCreatePersona: openCreatePersona,
        submitCreatePersona: submitCreatePersona,

        resetWizard: resetWizard,
        onFileChange: onFileChange,
        chooseSpeaker: chooseSpeaker,
        generatePersona: generatePersona,
        percent: percent,

        openChat: openChat,
        createSession: createSession,
        switchSession: switchSession,
        removeSession: removeSession,
        onPersonaSwitch: onPersonaSwitch,
        onComposerKeydown: onComposerKeydown,
        sendMessage: sendMessage,
        stopGeneration: stopGeneration,
        sendFeedback: sendFeedback,
        openRewrite: openRewrite,
        submitRewrite: submitRewrite,

        loadMemories: loadMemories,
        loadChatMemories: loadChatMemories,
        startAddMemory: startAddMemory,
        startEditMemory: startEditMemory,
        cancelMemoryEdit: cancelMemoryEdit,
        submitMemory: submitMemory,
        removeMemory: removeMemory,
        runMemoryTest: runMemoryTest,
        onMemFilterChange: onMemFilterChange,

        savePersona: savePersona,
        onPersonaFormSwitch: onPersonaFormSwitch,

        loadSettings: loadSettings,
        saveSettings: saveSettings,
        disableDesensitize: disableDesensitize,
        gotoDesensitizeSettings: gotoDesensitizeSettings,

        /* 角色卡 */
        onCardFileChange: onCardFileChange,
        importCard: importCard,
        exportCard: exportCard,
        findPersona: findPersona,

        /* 世界书 */
        loadWorldbook: loadWorldbook,
        lorePositions: LORE_POSITION_LABELS,
        lorePosLabel: lorePosLabel,
        backupStrategies: BACKUP_STRATEGY_LABELS,
        onLorePersonaChange: onLorePersonaChange,
        openLoreEditor: openLoreEditor,
        closeLoreEditor: closeLoreEditor,
        saveLoreEntry: saveLoreEntry,
        toggleLoreEntry: toggleLoreEntry,
        removeLoreEntry: removeLoreEntry,
        runLorePreview: runLorePreview,

        /* 备份与批次 */
        exportBackup: exportBackup,
        onBackupFileChange: onBackupFileChange,
        backupCount: backupCount,
        backupDetail: backupDetail,
        loadBatches: loadBatches,
        useBatch: useBatch,
        removeBatch: removeBatch,

        /* 消息操作与渲染 */
        regenerateMessage: regenerateMessage,
        openEditMessage: openEditMessage,
        closeEditMessage: closeEditMessage,
        submitEditMessage: submitEditMessage,
        isLastAssistant: isLastAssistant,
        copyMessage: function (message) {
          copyText(String((message && message.content) || ""));
        },
        copyCode: function (encoded) {
          copyText(decodeURIComponent(encoded));
        },
        renderMarkdown: renderMarkdown,
        onMarkdownClick: onMarkdownClick,
        fmtClock: fmtClock,
        desensStats: desensStats,
        desensRows: desensRows,
        desensTotalText: desensTotalText,
        desensDropText: desensDropText,

        traitTags: traitTags,
        sampleCountText: sampleCountText,
        kindLabel: kindLabel,
        providerLabel: providerLabel,
        fmtTime: fmtTime,
        fmtImportance: fmtImportance
      };
    },
    template: TEMPLATE
  });

  app.mount("#app");
})();
