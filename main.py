"""
DeepSeek V4 + 微信 智能机器人
架构：轮询主线程 → 独立队列 → Worker → 发送队列 → 发送线程
"""

import os, re, sys, time, random, logging, threading, queue, hashlib, unicodedata
from pathlib import Path
from datetime import datetime, timedelta

_ERR = []
try: from dotenv import load_dotenv
except Exception as e: _ERR.append(f"dotenv: {e}")
try: from openai import OpenAI
except Exception as e: _ERR.append(f"openai: {e}")
try: from wxauto4 import WeChat; from wxauto4.msgs import SelfMessage
except Exception as e: _ERR.append(f"wxauto4: {e}")
try: import easyocr
except Exception as e: _ERR.append(f"easyocr: {e}")
if _ERR:
    for e in _ERR: print(f"❌ {e}")
    input("按 Enter 退出"); sys.exit(1)

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("wxbot.log", encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ==== 配置 ====
C = lambda k, d: os.getenv(k, d)
DEEPSEEK_KEY = C("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE = C("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
PROMPT_PATH = Path(__file__).parent / "prompt.txt"

# 内置重要规则（prompt.txt 不存在时使用，prompt.txt 可覆盖）
DEFAULT_SYSTEM_PROMPT = """你是deepseek。所有回答使用中文。

【写作规范】
- 语气自然平实，杜绝机械AI行文感
- 短句为主，不使用标点符号，用空格分隔
- 回复简洁，不啰嗦
- 不带有任何地方方言腔调
- 不使用"你好"等问候语开头

【行为规则】
- 用户发送 /help 可查看可用指令
- 不要主动提及自己是 AI 或模型
- 不要使用 Markdown 格式（微信不支持）
- 代码用纯文本展示，不要用代码块标记
- 每条回复末尾加上 --ds自动回复. 查看命令详情: /help

1. 句式错落自然，摒弃刻板排比、对称句式与固定总分格式，不刻意追求行文工整
2. 用词采用通用平实表达，舍弃官方套话、浮夸修饰词，禁用综上所述、由此可见、不难看出这类制式衔接语(除非专业性知识)
3. 拆分冗长复合语句，语句节奏贴合正常人思考表达习惯，逻辑顺畅即可，无需过度严谨闭环(除非专业性知识)
4. 以常规客观视角结合实际感受表述，措辞通俗通用，语气平和沉稳，不使用地域特色口语、俚语
5. 删减无效铺垫与冗余内容，只保留核心信息，段落划分随性自然，不套用统一模板框架
6. 整体表达贴近普通人日常交流、分析叙述的常态风格，语气稍冷，但是机械感需要完全消除
7. 如果不是用户主动提出要求建议，则不主动提供建议，仅回答问题，不要有多余的话和问候
8. 不需要使用任何敬语。对于打招呼的信息仅回答：你好呀！
9. 短句子不允许使用句号逗号,允许问号，注意!:在词义表达通畅的情况下优先省略主语，其次删冗余谓语，少动宾语
10. 在日常对话下尽量少用书面语言，当用户询问专业问题时必须保证其专业性(允许使用官方术语)
11. 当用户发出你不能理解的话时,允许使用一个单独的问号表示不理解(部分场景:不合理的要求,用户要求你喊爸爸也可以用)允许单独使用。当用户说出什么惊为天人让人无语的话允许使用"。。？"
【消息拆分】
回复中的每个换行段落会被作为一条独立消息依次发送。
需要发送多条消息时，用换行分隔每个段落即可。
短句子可以用换行拆成多条发送，使对话更自然。

【保留格式】
如果某段内容需要整条发送不被拆分（如代码），用 $$$ 包裹：
开头说明$$$代码内容
可以换行$$$后续内容
被 $$$ 包裹的部分会整条发出，不会按换行拆分。

--ds自动回复. 查看命令详情: /help 单独作为一段发出。""".strip()

SYSTEM_PROMPT = PROMPT_PATH.read_text("utf-8").strip() if PROMPT_PATH.exists() else DEFAULT_SYSTEM_PROMPT
MAX_HISTORY = int(C("MAX_HISTORY_LENGTH", "10"))
TIMEOUT = int(C("REPLY_TIMEOUT", "120"))
DISABLE_GROUPS = C("DISABLE_GROUPS", "true").lower() == "true"
POLL_MIN = float(C("POLL_MIN", "1.5"))
POLL_MAX = float(C("POLL_MAX", "3.0"))
IDLE_MULT = float(C("IDLE_MULT", "2.0"))  # 空闲时轮询间隔倍数
MAX_SEND_PER_FLUSH = int(C("MAX_SEND_PER_FLUSH", "3"))
SEND_QUEUE_MAXSIZE = int(C("SEND_QUEUE_MAXSIZE", "500"))
SEEN_TTL = int(C("SEEN_TTL", "3600"))  # seen 条目存活秒数
IMG_DIR = Path(C("IMG_DIR", "./images"))
# 多消息拆分（按换行，≥15 行不拆分）
MAX_AI_PARTS = int(C("MAX_AI_PARTS", "5"))
MIN_PART_LEN = int(C("MIN_PART_LEN", "2"))
SEND_PART_DELAY_MIN = float(C("SEND_PART_DELAY_MIN", "0.5"))
SEND_PART_DELAY_MAX = float(C("SEND_PART_DELAY_MAX", "1.2"))
ENABLE_AI_SPLIT = C("ENABLE_AI_SPLIT", "true").lower() == "true"  # 按换行拆分开关
DEFAULT_N_LEN = int(C("DEFAULT_N_LEN", "15"))  # 默认换行拆分阈值
DEFAULT_SHOW_THINKING = False
# 聊天授权：控制用户是否能使用 AI
DEFAULT_CHAT_ENABLED = C("DEFAULT_CHAT_ENABLED", "false").lower() == "true"
# 顶层会话扫描：只读左侧会话列表前 N 项，成本极低
TOP_SESSION_SCAN = int(C("TOP_SESSION_SCAN", "5"))
# 本地控制通道文件（JSONL），用于自己的命令及时送达
CONTROL_FILE = Path(__file__).parent / "control.jsonl"
# 控制通道轮询间隔（秒）
CONTROL_POLL_SEC = float(C("CONTROL_POLL_SEC", "1.0"))
# 当前会话定点补偿（第3层）：只读当前打开会话末尾消息，默认关闭
COMPENSATE_CURRENT_CHAT = C("COMPENSATE_CURRENT_CHAT", "0") == "1"
# AI / OCR 队列上限，防止被刷爆
AI_QUEUE_MAXSIZE = int(C("AI_QUEUE_MAXSIZE", "50"))
OCR_QUEUE_MAXSIZE = int(C("OCR_QUEUE_MAXSIZE", "20"))
# OCR 图片提交并发上限
OCR_SUBMIT_CONCURRENCY = int(C("OCR_SUBMIT_CONCURRENCY", "2"))
# control.jsonl 认证 token；为空则禁用本地 control.jsonl 控制通道
CONTROL_TOKEN = C("CONTROL_TOKEN", "")
# 未开放会话不进入聊天窗口（非授权版核心优化）
START_FROM_CONTROL_ONLY = C("START_FROM_CONTROL_ONLY", "true").lower() == "true"
# 微信控制终端：用固定会话（如文件传输助手）当控制面板
ENABLE_WXTERM = C("ENABLE_WXTERM", "true").lower() == "true"
WXTERM_NAME = C("WXTERM_NAME", "文件传输助手")
WXTERM_POLL_SEC = float(C("WXTERM_POLL_SEC", "3.0"))
# 指令防抖 TTL（秒），防止 wxauto 重复读到同一条指令
CMD_DEDUPE_TTL = float(C("CMD_DEDUPE_TTL", "20"))
# 普通文本防抖 TTL（秒），防止同一条消息被重复提交 AI
TEXT_DEDUPE_TTL = float(C("TEXT_DEDUPE_TTL", "10"))
WHITELIST = [x.strip() for x in C("WHITELIST", "").split(",") if x.strip()]
BLACKLIST_FILE = Path(__file__).parent / "blacklist.txt"

# ==== 全局状态 ====
_st = threading.Lock()
ai_client: OpenAI | None = None
ocr_reader: easyocr.Reader | None = None
ocr_ready = threading.Event()
history: dict[str, list[dict]] = {}
history_ts: dict[str, float] = {}
seen: dict[str, float] = {}  # mid → 添加时间
session_ts: dict[str, str] = {}
BLACKLIST: list[str] = []
# 每个会话独立配置
chat_cfg: dict[str, dict] = {}
# 顶层会话 fingerprint 快照（name → fp），用于检测左侧列表变化
top_session_fp: dict[str, str] = {}
# control.jsonl 已读字节偏移
_control_offset: int = 0
# control.jsonl 半行缓冲区（防止读到不完整 JSON 导致丢命令）
_control_tail: str = ""
# OCR 提交并发控制
ocr_submit_sem = threading.Semaphore(OCR_SUBMIT_CONCURRENCY)
# 微信终端已读消息 ID 集合
wxterm_seen: set[str] = set()
# 指令防抖表：chat_name|sender|text_lower → 过期时间
recent_cmd_seen: dict[str, float] = {}
# 普通文本防抖表：sha1(chat_name|sender|norm_text) → 过期时间
recent_text_seen: dict[str, float] = {}
# 提示词收集模式：chat_name → {"lines": list[str], "append": bool}
prompt_collecting: dict[str, dict] = {}

# ==== 三个独立队列 ====
ai_queue = queue.Queue(maxsize=AI_QUEUE_MAXSIZE)    # (fn, on_done) → AI Worker 消费
ocr_queue = queue.Queue(maxsize=OCR_QUEUE_MAXSIZE)   # (img_path, reply_queue) → OCR Worker 消费
CHAT_CFG_FILE = Path(__file__).parent / "chat_cfg.json"
send_queue = queue.Queue(maxsize=SEND_QUEUE_MAXSIZE)  # 有界队列
_current_chat = None
_last_msg_at = 0.0  # 最后收到新消息的时间（用于动态轮询）
# 懒加载会话初始化：首次进入某聊天窗口时标记历史消息为 seen
primed_chats: set[str] = set()
PRIME_HISTORY_LIMIT = int(C("PRIME_HISTORY_LIMIT", "20"))

BOT_START_TS = 0.0
# 只处理最近 N 秒内的消息，默认 10 分钟
MSG_MAX_AGE_SEC = int(C("MSG_MAX_AGE_SEC", "600"))
# 微信有时只给到分钟，严格按秒判断会误杀同一分钟内的新消息
STARTUP_TIME_TOLERANCE_SEC = float(C("STARTUP_TIME_TOLERANCE_SEC", "60"))

# ==== 工具 ====
def atomic_write(path: Path, text: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, "utf-8")
    tmp.replace(path)

# ==== 黑名单 ====
def _load_blacklist():
    global BLACKLIST
    if BLACKLIST_FILE.exists():
        BLACKLIST = [x.strip() for x in BLACKLIST_FILE.read_text("utf-8").splitlines() if x.strip()]

def _save_blacklist():
    atomic_write(BLACKLIST_FILE, "\n".join(BLACKLIST))

def add_black(name: str) -> bool:
    if name and name not in BLACKLIST: BLACKLIST.append(name); _save_blacklist(); return True
    return False

def del_black(name: str) -> bool:
    if name in BLACKLIST: BLACKLIST.remove(name); _save_blacklist(); return True
    return False

def is_allowed(chat: str, sender: str) -> bool:
    if chat in BLACKLIST or sender in BLACKLIST: return False
    if WHITELIST and chat not in WHITELIST and sender not in WHITELIST: return False
    return True

def get_chat_cfg(chat_name: str) -> dict:
    """获取会话配置（不存在则用默认值创建）"""
    with _st:
        if chat_name not in chat_cfg:
            chat_cfg[chat_name] = {
                "enabled": DEFAULT_CHAT_ENABLED,
                "show_thinking": DEFAULT_SHOW_THINKING,
                "online": False,
                "n_len": DEFAULT_N_LEN,
                "prompt": None,
            }
        return chat_cfg[chat_name]

def get_chat_cfg_snapshot(chat_name: str) -> dict:
    """获取会话配置快照（用于 AI 请求，避免排队期间配置变化）"""
    with _st:
        cfg = chat_cfg.get(chat_name)
        if cfg is None:
            cfg = {
                "enabled": DEFAULT_CHAT_ENABLED,
                "show_thinking": DEFAULT_SHOW_THINKING,
                "online": False,
                "n_len": DEFAULT_N_LEN,
                "prompt": None,
            }
            chat_cfg[chat_name] = cfg
        return cfg.copy()

_load_blacklist()

# ==== seen 管理（TTL dict，不再粗暴 clear）====
def mark_seen(mid: str) -> bool:
    with _st:
        if mid in seen: return False
        seen[mid] = time.time()
        return True

def cleanup_seen():
    now = time.time()
    with _st:
        for k, t in list(seen.items()):
            if now - t > SEEN_TTL:
                seen.pop(k, None)

def _msg_id(msg, chat_name: str) -> str:
    """
    混合指纹：文本内容 + 微信原始 id/hash + 时间 + 发送者。
    wxauto 的 id/hash 可能不稳定，仅作为辅助字段避免同一分钟重复文本被吞。
    """
    sender = getattr(msg, "sender", "")
    mtime = getattr(msg, "time", "") or getattr(msg, "create_time", "")
    mtype = getattr(msg, "type", "")
    content = str(getattr(msg, "content", ""))[:500]
    raw_id = getattr(msg, "id", "") or getattr(msg, "hash", "") or ""

    stable = f"{chat_name}|{sender}|{mtype}|{mtime}|{raw_id}|{content}"
    h = hashlib.sha1(stable.encode("utf-8", errors="ignore")).hexdigest()
    return f"fb|{h}"

# ==== 微信时间解析 & 运行时消息过滤 ====
def _parse_wx_ts(value) -> float | None:
    """
    解析 wxauto 可能返回的时间格式。
    支持：2026-05-24 17:04:33 / 05-24 17:04 / 今天 17:04 / 昨天 17:04 / 17:04
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None

    s = str(value).strip()
    if not s:
        return None

    now_dt = datetime.now()

    full_formats = [
        "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
        "%Y年%m月%d日 %H:%M:%S", "%Y年%m月%d日 %H:%M",
    ]
    for fmt in full_formats:
        try:
            return datetime.strptime(s, fmt).timestamp()
        except Exception:
            pass

    md_formats = ["%m-%d %H:%M:%S", "%m-%d %H:%M"]
    for fmt in md_formats:
        try:
            dt = datetime.strptime(s, fmt)
            dt = dt.replace(year=now_dt.year)
            return dt.timestamp()
        except Exception:
            pass

    m = re.search(r"昨天\s*(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if m:
        h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        dt = (now_dt - timedelta(days=1)).replace(hour=h, minute=mi, second=sec, microsecond=0)
        return dt.timestamp()

    m = re.search(r"今天\s*(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if m:
        h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        dt = now_dt.replace(hour=h, minute=mi, second=sec, microsecond=0)
        return dt.timestamp()

    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if m:
        h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        dt = now_dt.replace(hour=h, minute=mi, second=sec, microsecond=0)
        return dt.timestamp()

    return None


def _msg_ts(msg) -> float | None:
    for attr in ("time", "create_time", "timestamp"):
        ts = _parse_wx_ts(getattr(msg, attr, None))
        if ts is not None:
            return ts
    return None


def _mark_seen_raw(chat_name: str, msg):
    mid = _msg_id(msg, chat_name)
    with _st:
        seen[mid] = time.time()


def _is_runtime_msg(chat_name: str, msg) -> bool:
    """
    只允许处理：
    - 机器人启动后的消息
    - 最近 MSG_MAX_AGE_SEC 秒内的消息
    无法解析时间的消息不直接丢弃，避免 wxauto 不给时间时吞新消息。
    """
    ts = _msg_ts(msg)
    if ts is None:
        return True

    now = time.time()

    if MSG_MAX_AGE_SEC > 0 and now - ts > MSG_MAX_AGE_SEC:
        _mark_seen_raw(chat_name, msg)
        return False

    if BOT_START_TS > 0 and ts < BOT_START_TS - STARTUP_TIME_TOLERANCE_SEC:
        _mark_seen_raw(chat_name, msg)
        return False

    return True


def filter_runtime_msgs(chat_name: str, msgs):
    return [m for m in msgs if _is_runtime_msg(chat_name, m)]

# ==== 多消息拆分（按换行）====
SPLIT_RULE = f"""
【消息拆分规则】
系统根据回复中的换行自动拆分消息发送。
- 每个换行段落为一条独立消息
- 换行数达到阈值则整条一次发出，不拆分
- 过短段落（少于 {MIN_PART_LEN} 字）自动合并到相邻段落
- 最多拆成 {MAX_AI_PARTS} 条，超出部分合并到末尾

【代码 / 保留格式】
需要某段内容整条发送不被拆分时，用 $$$ 包裹：
  开头说明$$$
  代码内容
  可以换行
  $$$后续内容
被 $$$ 包裹的内容将作为一整条消息发出，不会按换行拆分。
这个机制适用于代码、表格、或任何需要保留换行的场景。
""".strip()

def _extract_quoted_blocks(text: str):
    """提取 $$$ 包裹的块，返回 [(type, content)]，type='normal' 或 'preserve'"""
    parts = []
    remaining = text
    while True:
        idx = remaining.find('$$$')
        if idx == -1:
            if remaining.strip():
                parts.append(('normal', remaining.strip()))
            break
        before = remaining[:idx].strip()
        if before:
            parts.append(('normal', before))
        rest = remaining[idx + 3:]
        end_idx = rest.find('$$$')
        if end_idx == -1:
            if rest.strip():
                parts.append(('normal', rest.strip()))
            break
        inner = rest[:end_idx].strip()
        if inner:
            parts.append(('preserve', inner))
        remaining = rest[end_idx + 3:]
    return parts

def split_ai_reply(text: str, n_len: int = 15) -> list[str]:
    """
    按换行拆分，换行 >= n_len 则不拆分。
    支持 $$$...$$$ 包裹的块，内部内容作为整条消息发送（不拆分）。
    """
    if not text: return []
    text = text.strip()
    if not text: return []

    blocks = _extract_quoted_blocks(text)
    result = []

    for btype, content in blocks:
        if btype == 'preserve':
            # $$$ 内整条保留，不拆分
            result.append(content)
        else:
            # 普通文本按换行拆分
            if content.count('\n') >= n_len:
                result.append(content)
            else:
                lines = [l.strip() for l in content.split('\n') if l.strip()]
                lines = [l for l in lines if len(l) >= MIN_PART_LEN]
                if not lines:
                    result.append(content)
                elif len(lines) > MAX_AI_PARTS:
                    head = lines[:MAX_AI_PARTS - 1]
                    tail = "\n".join(lines[MAX_AI_PARTS - 1:])
                    result.extend(head)
                    result.append(tail)
                else:
                    result.extend(lines)
    return result

def enqueue_reply(chat_name: str, text: str, split: bool = False):
    if not text: return
    if split and ENABLE_AI_SPLIT:
        cfg = get_chat_cfg_snapshot(chat_name)
        n_len = cfg.get("n_len", DEFAULT_N_LEN)
        parts = split_ai_reply(text, n_len)
    else:
        parts = [text.strip()]
    for part in parts:
        if not part: continue
        try:
            send_queue.put_nowait((chat_name, part))
        except queue.Full:
            logger.warning(f"发送队列满，丢弃: {part[:80]}")

def clean_split_token(text: str) -> str:
    return text.strip() if text else ""

def _norm_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

# ==== Worker: AI（只消费 ai_queue）====
def ai_worker():
    while True:
        task = ai_queue.get()
        if task is None: break
        fn, on_done = task
        try: result = fn()
        except Exception as e:
            logger.error(f"AI err: {e}")
            result = f"AI 繁忙 ({type(e).__name__})", ""
        if on_done:
            try: on_done(result)
            except Exception as e: logger.error(f"AI callback: {e}")
        ai_queue.task_done()

def _do_ask(msg: str, hist: list[dict] | None, show_thinking: bool, online: bool, custom_prompt: str | None = None):
    if ai_client is None: return "❌ 未初始化", ""
    system_content = custom_prompt if custom_prompt else SYSTEM_PROMPT
    if ENABLE_AI_SPLIT:
        system_content += "\n\n" + SPLIT_RULE
    if online:
        system_content += "\n\n如果当前模型或服务端具备联网能力，请优先获取实时信息；否则请明确说明无法确认最新信息。"
    msgs = [{"role": "system", "content": system_content}]
    if hist: msgs.extend(hist[-(MAX_HISTORY * 2):])
    msgs.append({"role": "user", "content": msg})
    model = "deepseek-v4-pro" if show_thinking else "deepseek-v4-flash"
    extra = {"thinking": {"type": "enabled"}} if show_thinking else {}
    r = ai_client.chat.completions.create(model=model, messages=msgs, timeout=TIMEOUT, extra_body=extra)
    c = r.choices[0]
    content = (c.message.content or "").strip()
    reasoning = ""
    if show_thinking:
        if hasattr(c.message, "reasoning_content"): reasoning = (c.message.reasoning_content or "").strip()
        elif hasattr(c.message, "model_extra"): reasoning = c.message.model_extra.get("reasoning_content", "").strip()
    return content, reasoning

def submit_ai(msg: str, hist: list[dict] | None, chat_name: str, on_done):
    cfg = get_chat_cfg_snapshot(chat_name)
    show_thinking = cfg["show_thinking"]
    online = cfg.get("online", False)
    custom_prompt = cfg.get("prompt")

    try:
        ai_queue.put_nowait((lambda: _do_ask(msg, hist, show_thinking, online, custom_prompt), on_done))
    except queue.Full:
        enqueue_reply(chat_name, "⚠️ AI 队列繁忙，请稍后再试")

# ==== Worker: OCR（只消费 ocr_queue）====
def ocr_worker():
    global ocr_reader
    logger.info("🔧 加载 EasyOCR (CPU)...")
    try:
        ocr_reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
        logger.info("✅ OCR 就绪")
        ocr_ready.set()
    except Exception as e:
        logger.error(f"OCR 加载失败: {e}"); return

    while True:
        task = ocr_queue.get()
        if task is None: break
        img_path, reply_queue = task
        text = ""
        try:
            r = ocr_reader.readtext(img_path)
            text = "\n".join(t for _, t, c in r if c > 0.35 and len(t.strip()) > 1).strip()
        except Exception as e:
            logger.error(f"OCR: {e}")
        finally:
            try: os.remove(img_path)
            except Exception: pass
        reply_queue.put(text)
        ocr_queue.task_done()

def submit_ocr(img_path: str) -> str:
    """同步等待 OCR（在 Worker 线程中调用，不阻塞主线程）"""
    reply_queue = queue.Queue()
    try:
        ocr_queue.put_nowait((img_path, reply_queue))
    except queue.Full:
        # 队列满时清理图片文件，避免残留
        try:
            os.remove(img_path)
        except Exception:
            pass
        return ""

    try:
        return reply_queue.get(timeout=30)
    except queue.Empty:
        return ""

# ==== 懒加载会话初始化 ====
def prime_chat_if_needed(
    chat_name: str,
    msgs,
    session_new_count=0,
    session_isnew=False,
    session_changed=False,
):
    """
    第一次遇到某个会话时：
    - 把旧历史消息标记为 seen
    - 如果 wxauto 明确报告新消息，保留最后 n 条
    - 如果 wxauto 没报告 new_count，但 session time 变了，至少保留最后 1 条
    """
    if not msgs:
        return []

    with _st:
        if chat_name in primed_chats:
            return msgs[-5:]
        primed_chats.add(chat_name)

    try:
        n = int(session_new_count or 0)
    except Exception:
        n = 0

    # 情况 1：wxauto 明确告诉我们有 n 条新消息
    if session_isnew and n > 0:
        n = max(1, min(n, 5, len(msgs)))
        old_msgs = msgs[:-n]
        new_msgs = msgs[-n:]

        with _st:
            for m in old_msgs[-PRIME_HISTORY_LIMIT:]:
                seen[_msg_id(m, chat_name)] = time.time()

        logger.info(
            f"🔥 [{chat_name}] 首次初始化："
            f"跳过 {len(old_msgs[-PRIME_HISTORY_LIMIT:])} 条旧消息，"
            f"保留 {len(new_msgs)} 条新消息"
        )
        return new_msgs

    # 情况 2：wxauto 没给 new_count，但会话时间确实变化了
    # 这通常说明最后一条是新消息，保留最后 1 条，避免吞掉用户第一条消息
    if session_changed:
        old_msgs = msgs[:-1]
        new_msgs = msgs[-1:]

        with _st:
            for m in old_msgs[-PRIME_HISTORY_LIMIT:]:
                seen[_msg_id(m, chat_name)] = time.time()

        logger.info(
            f"🔥 [{chat_name}] 首次初始化："
            f"new_count 不可靠，跳过 {len(old_msgs[-PRIME_HISTORY_LIMIT:])} 条旧消息，"
            f"保留最后 1 条新活动"
        )
        return new_msgs

    # 情况 3：没有任何新活动信号，整批视为历史
    with _st:
        for m in msgs[-PRIME_HISTORY_LIMIT:]:
            seen[_msg_id(m, chat_name)] = time.time()

    logger.info(
        f"🔥 [{chat_name}] 首次初始化："
        f"标记 {min(len(msgs), PRIME_HISTORY_LIMIT)} 条历史消息"
    )
    return []

# ==== 顶层会话 fingerprint ====
def _session_fp(s) -> str:
    """计算某个会话对象的 fingerprint，用于检测左侧列表是否变化"""
    keys = [
        "name",
        "time",
        "new_count",
        "isnew",
        "content",
        "last_msg",
        "last_message",
        "text",
        "remark",
    ]
    parts = []
    for k in keys:
        try:
            v = getattr(s, k, "")
            if callable(v):
                v = v()
        except Exception:
            v = ""
        parts.append(f"{k}={v}")
    return "|".join(parts)


def init_top_session_snapshot(wx):
    """启动时建立顶层会话 fingerprint 快照，防止把历史会话当新消息"""
    try:
        sessions = wx.GetSession()
    except Exception as e:
        logger.warning(f"初始化顶层会话快照失败: {e}")
        return

    for s in sessions[:TOP_SESSION_SCAN]:
        try:
            top_session_fp[s.name] = _session_fp(s)
        except Exception:
            pass

    logger.info(f"✅ 已初始化顶部 {min(len(sessions), TOP_SESSION_SCAN)} 个会话快照")


# ==== 会话轮询 ====
def _process_one_session(wx, s, top_fp_changed: bool = False) -> bool:
    """
    进入指定会话、读取消息并分发处理。
    返回 True 表示处理了新消息（用于更新 _last_msg_at）。
    top_fp_changed=True 时放宽时间过滤，并把活动信号传给 prime_chat_if_needed。
    """
    name = s.name
    s_time = getattr(s, "time", "")

    # 非授权版：未开放会话不进入聊天窗口
    if START_FROM_CONTROL_ONLY:
        cfg = get_chat_cfg(name)
        if not cfg.get("enabled", DEFAULT_CHAT_ENABLED):
            return False

    s_ts = _parse_wx_ts(s_time)

    # 关键：顶层 fingerprint 变化时，不要完全相信 s.time
    if s_ts is not None and not top_fp_changed:
        now = time.time()

        if MSG_MAX_AGE_SEC > 0 and now - s_ts > MSG_MAX_AGE_SEC:
            return False

        if BOT_START_TS > 0 and s_ts < BOT_START_TS - STARTUP_TIME_TOLERANCE_SEC:
            return False

    try:
        session_new_count = int(getattr(s, "new_count", 0) or 0)
    except Exception:
        session_new_count = 0

    session_isnew = bool(getattr(s, "isnew", False))
    prev_s_time = session_ts.get(name)
    session_changed = (s_time != prev_s_time)

    if not top_fp_changed:
        if not session_changed and not session_isnew and session_new_count <= 0:
            return False

    session_ts[name] = s_time

    logger.info(f"🔔 {name}" + (" [fp]" if top_fp_changed else ""))
    try:
        wx.ChatWith(name)
        time.sleep(0.3)
        msgs = wx.GetAllMessage()
    except Exception:
        return False
    if not msgs:
        return False

    global _current_chat, _last_msg_at
    _current_chat = name
    _last_msg_at = time.time()

    # 顶层指纹变化也视为活动信号，防止首次进入时吞掉最后一条消息
    activity_changed = session_changed or top_fp_changed

    candidate_msgs = prime_chat_if_needed(
        name,
        msgs,
        session_new_count=session_new_count,
        session_isnew=session_isnew,
        session_changed=activity_changed,
    )

    if not candidate_msgs:
        return False

    candidate_msgs = filter_runtime_msgs(name, candidate_msgs)
    if not candidate_msgs:
        return False

    for msg in candidate_msgs[-5:]:
        handle_message(msg, name)

    return True


def poll_sessions(wx):
    processed: set[str] = set()

    # ---- 第 1 层：顶层会话 fingerprint 变化检测 ----
    try:
        sessions = wx.GetSession()
    except Exception:
        sessions = []

    if sessions:
        for s in sessions[:TOP_SESSION_SCAN]:
            try:
                name = s.name
                fp = _session_fp(s)
                old_fp = top_session_fp.get(name)
                if old_fp is not None and fp != old_fp:
                    top_session_fp[name] = fp
                    if _process_one_session(wx, s, top_fp_changed=True):
                        processed.add(name)
                elif old_fp is None:
                    # 新出现的会话：记录指纹但不处理（避免启动时误触发）
                    top_session_fp[name] = fp
            except Exception:
                pass

    # ---- 第 2 层：全量会话时间/new_count/isnew 检测 ----
    for s in sessions:
        name = s.name
        if name in processed:
            continue

        # 更新顶层指纹（不论是否触发）
        try:
            top_session_fp[name] = _session_fp(s)
        except Exception:
            pass

        if _process_one_session(wx, s):
            processed.add(name)


# ==== 本地控制通道（control.jsonl）====
def write_control(chat_name: str, text: str, sender: str = ""):
    """
    向 control.jsonl 写入一条控制命令。
    chat_name: 目标会话名
    text: 指令文本（如 "/start"、"你好"）
    sender: 发送者（留空则视为自己）
    """
    import json
    entry = {
        "chat_name": chat_name,
        "sender": sender or chat_name,
        "text": text,
    }
    if CONTROL_TOKEN:
        entry["token"] = CONTROL_TOKEN
    with open(CONTROL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _handle_control_input(chat_name: str, sender: str, text: str, out_chat_name: str | None = None):
    """处理来自 control.jsonl / 微信终端的控制输入"""
    sender = sender or "__control__"
    text = text.strip()
    if not text:
        return

    # 提示词收集模式：非指令消息直接收集
    with _st:
        pdata = prompt_collecting.get(chat_name)
    if pdata is not None and not text.startswith("/"):
        pdata["lines"].append(text)
        logger.info(f"📝 [control] [{chat_name}] 收集提示词: {text[:60]}")
        return

    if text.startswith("/"):
        # 指令防抖：防止 wxauto id/hash 不稳定导致重复执行
        if is_duplicate_command(chat_name, sender, text):
            logger.info(f"♻️ [control] [{chat_name}] 重复指令已忽略: {sender}: {text[:60]}")
            return

        _route_command(
            text=text,
            chat_name=chat_name,
            is_self=True,
            sender=sender,
            out_chat_name=out_chat_name,
        )
        return

    _submit_text_to_ai(text, chat_name, sender)


def _poll_control_file():
    """
    第 2 层触发：读取 control.jsonl 新增行，作为自己的控制命令输入。
    格式每行一个 JSON：{"chat_name": "...", "sender": "...", "text": "...", "token": "..."}
    支持 CONTROL_TOKEN 认证；支持半行缓冲防止读断。
    """
    global _control_offset, _control_tail
    if _control_offset == -1:  # control 已禁用
        return
    if not CONTROL_FILE.exists():
        return

    try:
        size = CONTROL_FILE.stat().st_size

        # 文件被截断（清空/轮转），重置偏移和半行缓冲
        if size < _control_offset:
            logger.info("control.jsonl 被截断，重置读取偏移")
            _control_offset = 0
            _control_tail = ""

        if size == _control_offset:
            return

        with open(CONTROL_FILE, "r", encoding="utf-8") as f:
            f.seek(_control_offset)
            chunk = f.read()
            _control_offset = f.tell()

        data = _control_tail + chunk

        # 保留最后不完整的行，等下次补全
        if not data.endswith("\n"):
            lines = data.splitlines()
            _control_tail = lines.pop() if lines else data
        else:
            lines = data.splitlines()
            _control_tail = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                import json
                entry = json.loads(line)
            except Exception:
                logger.warning(f"control.jsonl 行无法解析: {line[:80]}")
                continue

            # token 认证
            if CONTROL_TOKEN:
                token = str(entry.get("token", ""))
                if token != CONTROL_TOKEN:
                    logger.warning("control.jsonl token 不匹配，已拒绝")
                    continue

            chat_name = entry.get("chat_name", "")
            sender = entry.get("sender", "")
            text = entry.get("text", "")
            if not chat_name or not text:
                continue

            logger.info(f"📡 [control] {chat_name} | {sender}: {text[:60]}")
            _handle_control_input(chat_name, sender, text)

    except Exception as e:
        logger.error(f"control.jsonl 读取错误: {e}")


# ==== 微信控制终端（文件传输助手）====
def _parse_wxterm_command(text: str):
    """
    解析终端命令格式：
    @张三 /start
    @张三 /stop
    返回 (target, cmd) 或 (None, None)
    非命令文本直接作为普通消息发送给 AI。
    """
    text = (text or "").strip()
    if not text.startswith("@"):
        return None, None

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None, None

    target = parts[0][1:].strip()
    cmd = parts[1].strip()

    if not target or not cmd:
        return None, None

    return target, cmd


def _poll_wx_terminal(wx):
    """定时读取微信终端（固定会话）中的 SelfMessage 命令"""
    if not ENABLE_WXTERM:
        return

    global _current_chat

    try:
        if _current_chat != WXTERM_NAME:
            wx.ChatWith(WXTERM_NAME)
            _current_chat = WXTERM_NAME
            time.sleep(0.2)

        msgs = wx.GetAllMessage()
    except Exception as e:
        logger.warning(f"微信终端读取失败: {e}")
        return

    if not msgs:
        return

    # 只看最后几条，避免历史刷屏
    for msg in msgs[-5:]:
        try:
            if not isinstance(msg, SelfMessage):
                continue

            if getattr(msg, "type", "") != "text":
                continue

            mid = _msg_id(msg, WXTERM_NAME)
            if mid in wxterm_seen:
                continue
            wxterm_seen.add(mid)

            text = (getattr(msg, "content", "") or "").strip()
            target, cmd = _parse_wxterm_command(text)
            if not target or not cmd:
                continue

            logger.info(f"🖥 微信终端命令: [{target}] {cmd}")

            _handle_control_input(
                chat_name=target,
                sender="__control__",
                text=cmd,
                out_chat_name=WXTERM_NAME,
            )

        except Exception as e:
            logger.warning(f"微信终端命令处理失败: {e}")


def init_wxterm_snapshot(wx):
    """启动时标记微信终端历史消息，避免执行旧命令"""
    if not ENABLE_WXTERM:
        return

    global _current_chat

    try:
        if _current_chat != WXTERM_NAME:
            wx.ChatWith(WXTERM_NAME)
            _current_chat = WXTERM_NAME
            time.sleep(0.2)

        msgs = wx.GetAllMessage()
    except Exception as e:
        logger.warning(f"初始化微信终端快照失败: {e}")
        return

    n = 0
    for msg in msgs[-20:]:
        try:
            if isinstance(msg, SelfMessage) and getattr(msg, "type", "") == "text":
                wxterm_seen.add(_msg_id(msg, WXTERM_NAME))
                n += 1
        except Exception:
            pass

    logger.info(f"✅ 已初始化微信终端历史消息 {n} 条")


# ==== 当前会话定点补偿（第3层：可选）====
def _poll_current_chat_compensation(wx):
    """
    第 3 层触发：只读当前打开会话末尾消息。
    不扫所有会话，不遍历消息树。

    默认关闭，设置 COMPENSATE_CURRENT_CHAT=1 开启。

    注意：如果用户手动切换了微信当前窗口，_current_chat 可能不是实际窗口，
    GetAllMessage() 读到的内容会被错误归到旧会话名下。
    """
    if not COMPENSATE_CURRENT_CHAT:
        return

    global _current_chat
    if not _current_chat:
        return

    try:
        msgs = wx.GetAllMessage()
    except Exception:
        return
    if not msgs:
        return

    msg = msgs[-1]

    if not _is_runtime_msg(_current_chat, msg):
        return

    # 不提前写 seen，交给 handle_message() 统一处理
    handle_message(msg, _current_chat)


# ==== 消息分发 ====
def handle_message(msg, chat_name: str):
    # 保险：再次过滤启动前/超时消息
    if not _is_runtime_msg(chat_name, msg):
        return

    is_self = isinstance(msg, SelfMessage)
    sender = getattr(msg, "sender", chat_name)
    mid = _msg_id(msg, chat_name)
    if not mark_seen(mid): return

    if not is_self:
        ci = getattr(msg, "chat_info", None)
        if callable(ci):
            ci = ci()
        if isinstance(ci, dict) and ci.get("chat_type") == "group" and DISABLE_GROUPS:
            return

    if msg.type == "image": return _handle_image(msg, chat_name, sender, is_self)
    if msg.type == "text": return _handle_text(msg, chat_name, sender, is_self)

# ==== 图片 ====
def _handle_image(msg, chat_name, sender, is_self):
    if is_self or not is_allowed(chat_name, sender):
        return

    cfg = get_chat_cfg(chat_name)

    if not cfg.get("enabled", DEFAULT_CHAT_ENABLED):
        logger.info(f"🚫 [{chat_name}] 未开放，忽略图片: {sender}")
        return

    if not ocr_ready.is_set():
        enqueue_reply(chat_name, "⏳ OCR 尚未就绪，请稍后")
        return

    # 先抢信号量，抢不到直接拒绝，不创建新线程
    if not ocr_submit_sem.acquire(blocking=False):
        enqueue_reply(chat_name, "⚠️ OCR 正在繁忙，请稍后再发图片")
        return

    logger.info(f"📸 [{chat_name}] [图片]")
    enqueue_reply(chat_name, "🔍 OCR 识别中...")

    # 下载放主线程，wxauto UI 操作线程安全
    saved = msg.download(str(IMG_DIR))
    if not saved:
        ocr_submit_sem.release()
        enqueue_reply(chat_name, "❌ 图片下载失败")
        return

    def do_ocr():
        try:
            try:
                text = submit_ocr(str(saved))
            except Exception as e:
                logger.error(f"OCR: {e}")
                text = ""

            if not text:
                enqueue_reply(chat_name, "❌ 未识别到文字")
                return

            def after_ai(result):
                reply, _ = result
                enqueue_reply(chat_name, reply, split=True)

            submit_ai(f"用户发来一张图片，以下是OCR提取的文字：\n\n{text}", None, chat_name, after_ai)
        finally:
            ocr_submit_sem.release()

    threading.Thread(target=do_ocr, daemon=True).start()


def is_duplicate_command(chat_name: str, sender: str, text: str) -> bool:
    """
    防止 wxauto 重复读到同一条指令时反复执行。
    这是 seen 的第二层保险，因为 wxauto 的 msg.id/hash 可能不稳定。
    """
    norm = _norm_text(text)
    low = norm.lower()

    key = f"{chat_name}|{sender}|{low}"
    now = time.time()

    with _st:
        exp = recent_cmd_seen.get(key, 0)

        if exp > now:
            # 重复读到时顺手续期，避免同一条旧命令过几十秒又触发
            recent_cmd_seen[key] = now + CMD_DEDUPE_TTL
            return True

        recent_cmd_seen[key] = now + CMD_DEDUPE_TTL
        return False


def is_duplicate_user_text(chat_name: str, sender: str, text: str) -> bool:
    """
    防止同一条普通消息被 wxauto 重复读取后反复提交 AI。
    """
    norm = _norm_text(text)
    if not norm:
        return True

    key_src = f"{chat_name}|{sender}|{norm}"
    key = hashlib.sha1(key_src.encode("utf-8", errors="ignore")).hexdigest()
    now = time.time()

    with _st:
        exp = recent_text_seen.get(key, 0)

        if exp > now:
            recent_text_seen[key] = now + TEXT_DEDUPE_TTL
            return True

        recent_text_seen[key] = now + TEXT_DEDUPE_TTL
        return False


# ==== 文本 ====
def _submit_text_to_ai(text: str, chat_name: str, sender: str):
    """提交用户消息到 AI Worker（公共入口）"""
    logger.info(f"📩 [{chat_name}] {sender}: {text[:60]}")
    key = f"{chat_name}|{sender}"

    with _st:
        hist = list(history.get(key, []))
        history.setdefault(key, []).append({"role": "user", "content": text})
        history_ts[key] = time.time()

    def on_ai(result):
        reply, reasoning = result
        if reasoning:
            enqueue_reply(chat_name, f"🧠 思考过程：\n{reasoning}")

        enqueue_reply(chat_name, reply, split=True)

        with _st:
            history.setdefault(key, []).append({
                "role": "assistant",
                "content": clean_split_token(reply)
            })

    submit_ai(text, hist, chat_name, on_ai)


def _handle_text(msg, chat_name, sender, is_self):
    text = msg.content.strip()
    if not text:
        return

    # 黑名单用户（非自己）直接跳过，包括指令
    if not is_self and not is_allowed(chat_name, sender):
        return

    # 提示词收集模式：非指令消息直接收集
    with _st:
        pdata = prompt_collecting.get(chat_name)
    if pdata is not None:
        if not text.startswith("/"):
            pdata["lines"].append(text)
            logger.info(f"📝 [{chat_name}] 收集提示词: {text[:60]}")
            return
        # 指令仍按正常流程处理（/p_end 在其中）

    # 指令优先处理
    if text.startswith("/"):
        if is_duplicate_command(chat_name, sender, text):
            logger.info(f"♻️ [{chat_name}] 重复指令已忽略: {sender}: {text[:60]}")
            return

        _route_command(text, chat_name, is_self, sender)
        return

    # 自己发的普通文本不进入 AI
    if is_self:
        return

    cfg = get_chat_cfg(chat_name)

    chat_enabled = bool(cfg.get("enabled", DEFAULT_CHAT_ENABLED))
    if not chat_enabled:
        logger.info(f"🚫 [{chat_name}] 未开放，忽略普通消息: {sender}: {text[:60]}")
        return

    # 已开放：自动回复
    if is_duplicate_user_text(chat_name, sender, text):
        logger.info(f"♻️ [{chat_name}] 重复普通消息已忽略: {sender}: {text[:60]}")
        return

    _submit_text_to_ai(text, chat_name, sender)


# ==== 指令路由 ====
def is_privileged_command_sender(is_self: bool, sender: str) -> bool:
    """判断是否为管理员：自己发的 或 来自 control.jsonl 控制通道"""
    return is_self or sender == "__control__"


def _route_command(text: str, chat_name: str, is_self: bool, sender: str, out_chat_name: str | None = None):
    reply_target = out_chat_name or chat_name
    out = lambda t: enqueue_reply(reply_target, t)
    cmd = text.split()[0] if text else text
    cfg = get_chat_cfg(chat_name)  # 当前会话配置
    privileged = is_privileged_command_sender(is_self, sender)

    # ---- 系统 ----
    if cmd in ("/重置", "/清除", "/reset", "/clear"):
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        with _st:
            pfx = f"{chat_name}|"
            for k in list(history.keys()):
                if k.startswith(pfx): del history[k]
        out("✅ 当前会话上下文已重置"); return

    if cmd in ("/帮助", "/help"):
        out(
            "🤖 可用指令：\n"
            "/start — 管理员开放会话（仅文件传输助手使用，格式：@目标 /start）\n"
            "/stop — 管理员关闭会话（仅文件传输助手使用，格式：@目标 /stop）\n"
            "/fast · /r — 切换模型模式\n"
            "/online · /offline — 联网搜索\n"
            "/status — 查看状态\n"
            "/history — 上下文条数\n"
            "/clear_seen — 清去重缓存\n"
            "/n_len N — 换行拆分阈值\n"
            "/prompt — 进入提示词设置模式\n"
            "/prompt -a — 进入提示词追加模式\n"
            "/prompt -show — 查看当前个人提示词\n"
            "/p_end — 结束提示词收集\n"
            "/black 名称 — 拉黑\n"
            "/del_black — 取消拉黑\n"
            "/重置 — 清上下文"
        ); return

    if cmd in ("/start", "/Start"):
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return

        # /start 只能在微信终端（文件传输助手）中使用
        if out_chat_name is None:
            out("⛔ /start 仅限在文件传输助手中使用，格式：@目标 /start")
            return

        cfg["enabled"] = True
        _save_chat_cfg()
        out("✅ 当前会话已开放：后续普通消息会自动回复")
        return

    if cmd in ("/stop", "/Stop"):
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return

        # /stop 只能在微信终端（文件传输助手）中使用
        if out_chat_name is None:
            out("⛔ /stop 仅限在文件传输助手中使用，格式：@目标 /stop")
            return

        cfg["enabled"] = False
        _save_chat_cfg()
        out("⛔ 当前会话已关闭：已删除开放标记，普通用户不能再聊天")
        return

    # ---- 状态 ----
    if cmd == "/status":
        enabled = "✅ 已开放" if cfg.get("enabled", DEFAULT_CHAT_ENABLED) else "⛔ 未开放"
        mode = "🧠 推理 (v4-pro)" if cfg["show_thinking"] else "💬 快速 (v4-flash)"
        online = "🌐 开" if cfg.get("online") else "📴 关"

        bl = "是" if chat_name in BLACKLIST or sender in BLACKLIST else "否"
        n_len = cfg.get("n_len", DEFAULT_N_LEN)
        prompt_status = "✅ 自定义" if cfg.get("prompt") else "📄 默认(prompt.txt)"

        out(
            f"📊 状态：\n"
            f"开放状态: {enabled}\n"
            f"模式: {mode}\n"
            f"联网: {online}\n"
            f"换行拆分: {n_len} 行\n"
            f"个人提示词: {prompt_status}\n"
            f"被拉黑: {bl}"
        ); return

    if cmd == "/mode":
        out(f"当前: {'🧠 v4-pro 推理模式' if cfg['show_thinking'] else '💬 v4-flash 快速模式'}\n切换: /fast 或 /r"); return

    if cmd == "/history":
        with _st:
            n = len(history.get(f"{chat_name}|{sender}", []))
            total = len(history)
        out(f"📝 当前会话: {n} 条上下文\n全部会话: {total} 条"); return

    if cmd == "/clear_seen":
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        with _st:
            n = len(seen); seen.clear()
        out(f"⚠️ 已清理 {n} 条去重缓存，旧消息可能被重复处理"); return

    # ---- 模式 ----
    if cmd in ("/fast", "/Fast"):
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        cfg["show_thinking"] = False
        _save_chat_cfg()
        out("💬 当前会话已切换快速模式 (v4-flash)"); return

    if cmd in ("/r", "/R", "/Thinking", "/thinking", "/Reasoning", "/reasoning"):
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        cfg["show_thinking"] = True
        _save_chat_cfg()
        out("🧠 当前会话已切换推理模式 (v4-pro)"); return

    # ---- 联网 ----
    if cmd in ("/online", "/Online"):
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        cfg["online"] = True
        _save_chat_cfg()
        out("🌐 当前会话已开启联网搜索"); return

    if cmd in ("/offline", "/Offline"):
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        cfg["online"] = False
        _save_chat_cfg()
        out("📴 当前会话已关闭联网搜索"); return

    # ---- 一键工作/休闲 ----
    if cmd in ("/work", "/Work"):
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        cfg["show_thinking"] = True
        cfg["online"] = True
        _save_chat_cfg()
        out("🚀 工作模式：推理 + 联网已开启"); return

    if cmd in ("/notwork", "/Notwork"):
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        cfg["show_thinking"] = False
        cfg["online"] = False
        _save_chat_cfg()
        out("☕ 休闲模式：快速回复 + 无联网"); return

    # ---- 个人提示词 ----
    if cmd == "/prompt":
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        args = text.split(maxsplit=1)
        low_args = args[1].strip().lower() if len(args) > 1 else ""

        # /prompt -show: 显示当前个人提示词
        if low_args in ("-show", "-s", "show"):
            cur = cfg.get("prompt")
            if cur:
                out(f"📝 当前会话个人提示词：\n{cur}")
            else:
                out("📝 当前会话未设置个人提示词（使用 prompt.txt 默认）")
            return

        # /prompt -a: 追加模式（无现有提示词时当做普通覆盖）
        append_mode = low_args in ("-a", "-append", "append")
        existing = cfg.get("prompt")
        # 无现有提示词时 -a 退化为覆盖
        if append_mode and not existing:
            append_mode = False

        with _st:
            prompt_collecting[chat_name] = {"lines": [], "append": append_mode}
        if append_mode:
            out("🎤 进入提示词追加模式，发送的消息将追加到现有提示词，发送 /p_end 结束")
        else:
            out("🎤 进入提示词设置模式，发送的消息将作为新提示词，发送 /p_end 结束")
        return

    if cmd == "/p_end":
        with _st:
            pdata = prompt_collecting.pop(chat_name, None)
        if pdata is None:
            out("⚠️ 当前未在提示词收集模式")
            return

        lines = pdata.get("lines", [])
        append_mode = pdata.get("append", False)

        if not lines:
            out("⚠️ 未收集到任何内容，提示词未更改")
            return

        new_text = "。".join(lines)
        if append_mode:
            old_prompt = cfg.get("prompt") or ""
            cfg["prompt"] = old_prompt + "\n" + new_text
            _save_chat_cfg()
            out(f"✅ 已追加到当前会话提示词（共 {len(cfg['prompt'])} 字）")
        else:
            cfg["prompt"] = new_text
            _save_chat_cfg()
            out(f"✅ 当前会话提示词已设置（共 {len(new_text)} 字）")
        return

    # ---- 换行拆分阈值 ----
    if cmd == "/n_len":
        if not privileged:
            out("⚠️ 该指令仅管理员可用")
            return
        args = text.split()
        try:
            v = int(args[1])
            cfg["n_len"] = max(1, min(v, 200))
            _save_chat_cfg()
            out(f"📏 当前会话换行拆分阈值已设为 {cfg['n_len']} 行")
        except (IndexError, ValueError):
            out(f"📏 当前换行拆分阈值: {cfg.get('n_len', DEFAULT_N_LEN)} 行\n用法: /n_len N (1~200)")
        return

    # ---- 黑名单 ----
    if cmd == "/black":
        args = text.split(maxsplit=1)
        # 只有管理员可以指定目标；其他人只能拉黑当前会话
        if len(args) > 1:
            if not privileged:
                out("⚠️ 你只能拉黑当前会话，不能指定其他目标")
                return
            tgt = args[1].strip()
        else:
            tgt = chat_name
        out(f"🚫 {tgt} 已加入黑名单" if add_black(tgt) else f"⚠️ {tgt} 已在黑名单中"); return

    if cmd in ("/del_black", "/unblack"):
        if not privileged:
            out("⚠️ 解除黑名单仅管理员可用")
            return
        args = text.split(maxsplit=1)
        tgt = args[1].strip() if len(args) > 1 else chat_name
        out(f"✅ {tgt} 已移出黑名单" if del_black(tgt) else f"⚠️ {tgt} 不在黑名单中"); return

    # ---- 未知指令 ----
    out("❓ 未知指令，发送 /help 查看可用指令")

# ==== chat_cfg 持久化 ====
def _load_chat_cfg():
    global chat_cfg
    if CHAT_CFG_FILE.exists():
        try:
            import json
            chat_cfg = json.loads(CHAT_CFG_FILE.read_text("utf-8"))
        except Exception: return
    # 校验字段
    with _st:
        for name, cfg in list(chat_cfg.items()):
            if not isinstance(cfg, dict):
                chat_cfg[name] = {
                    "enabled": DEFAULT_CHAT_ENABLED,
                    "show_thinking": DEFAULT_SHOW_THINKING,
                    "online": False,
                    "n_len": DEFAULT_N_LEN,
                }
                continue
            cfg.setdefault("enabled", DEFAULT_CHAT_ENABLED)
            cfg.setdefault("show_thinking", DEFAULT_SHOW_THINKING)
            cfg.setdefault("online", False)
            cfg.setdefault("n_len", DEFAULT_N_LEN)
            cfg.setdefault("prompt", None)
            cfg["enabled"] = bool(cfg["enabled"])
            cfg["show_thinking"] = bool(cfg["show_thinking"])
            cfg["online"] = bool(cfg["online"])
            try: cfg["n_len"] = max(1, int(cfg["n_len"]))
            except Exception: cfg["n_len"] = DEFAULT_N_LEN
            if cfg.get("prompt") is not None and not isinstance(cfg["prompt"], str):
                cfg["prompt"] = None

def update_chat_cfg(chat_name: str, **kwargs):
    """线程安全地更新会话配置字段"""
    with _st:
        cfg = chat_cfg.get(chat_name)
        if cfg is None:
            cfg = {
                "enabled": DEFAULT_CHAT_ENABLED,
                "show_thinking": DEFAULT_SHOW_THINKING,
                "online": False,
                "n_len": DEFAULT_N_LEN,
                "prompt": None,
            }
            chat_cfg[chat_name] = cfg
        for k, v in kwargs.items():
            cfg[k] = v
    _save_chat_cfg()

def _save_chat_cfg():
    import json
    with _st:
        data = json.dumps(chat_cfg, ensure_ascii=False, indent=2)
    atomic_write(CHAT_CFG_FILE, data)

_load_chat_cfg()

# ==== 发送线程（唯一调用 wx.SendMsg 的地方）====
def _flush_send(wx):
    """主线程：每次最多发 MAX_SEND_PER_FLUSH 条，避免阻塞轮询"""
    global _current_chat
    sent = 0
    # 发送重试计数器：key=(target, msg) → retry_count
    # 使用全局 dict 避免每次重建
    if not hasattr(_flush_send, "retry_map"):
        _flush_send.retry_map = {}
    retry_map = _flush_send.retry_map

    MAX_RETRIES = 3  # 每条消息最多重试 3 轮
    try:
        while sent < MAX_SEND_PER_FLUSH:
            target, msg = send_queue.get_nowait()
            msg_key = (target, msg)

            # 检查重试次数
            retry_count = retry_map.get(msg_key, 0)
            if retry_count >= MAX_RETRIES:
                logger.error(f"发送到 {target} 已重试 {MAX_RETRIES} 次，丢弃: {msg[:80]}")
                retry_map.pop(msg_key, None)
                continue  # 跳过，继续下一条

            try:
                if _current_chat != target:
                    wx.ChatWith(target)
                    _current_chat = target
                    time.sleep(0.08)

                send_ok = False
                last_err = None
                for attempt in range(2):
                    try:
                        for i in range(0, len(msg), 2000):
                            chunk = msg[i:i + 2000]
                            wx.SendMsg(chunk)

                            if i + 2000 < len(msg): time.sleep(0.05)
                        send_ok = True
                        break
                    except Exception as e:
                        last_err = e
                        logger.warning(f"发送到 {target} 失败 (第{attempt+1}次): {e}")
                        # 恢复：重新切换会话再试
                        try:
                            wx.ChatWith(target)
                            _current_chat = target
                            time.sleep(0.3)
                        except Exception:
                            _current_chat = None

                if not send_ok:
                    retry_map[msg_key] = retry_count + 1
                    logger.error(f"发送到 {target} 失败 (累计重试{retry_count+1}/{MAX_RETRIES}): {last_err}")
                    # 放回队列末尾，等下一轮重试
                    try:
                        send_queue.put_nowait((target, msg))
                    except queue.Full:
                        logger.warning(f"发送队列满，无法放回: {msg[:80]}")
                        retry_map.pop(msg_key, None)
                    _current_chat = None
                    break  # 暂停本批发送，等下一轮
                else:
                    # 发送成功，清除重试记录
                    retry_map.pop(msg_key, None)

                sent += 1
                time.sleep(random.uniform(SEND_PART_DELAY_MIN, SEND_PART_DELAY_MAX))
            except Exception as e:
                # 取出的消息在 ChatWith / 其他环节异常退出，必须放回或丢弃
                logger.error(f"发送到 {target} 异常失败: {e}")
                retry_map[msg_key] = retry_count + 1
                if retry_count + 1 >= MAX_RETRIES:
                    logger.error(f"发送到 {target} 已重试 {MAX_RETRIES} 次，丢弃: {msg[:80]}")
                    retry_map.pop(msg_key, None)
                else:
                    try:
                        send_queue.put_nowait((target, msg))
                    except queue.Full:
                        logger.warning(f"发送队列满，无法放回: {msg[:80]}")
                        retry_map.pop(msg_key, None)
                _current_chat = None
    except queue.Empty:
        pass

# ==== TTL 清理 ====
_ttl_count = 0
def _maybe_cleanup():
    global _ttl_count
    _ttl_count += 1
    if _ttl_count % 30 != 0: return
    now = time.time()
    with _st:
        stale = [k for k, t in history_ts.items() if now - t > 1800]
        for k in stale: history.pop(k, None); history_ts.pop(k, None)
    cleanup_seen()
    now2 = time.time()
    with _st:
        # 清理过期的指令防抖
        for k, exp in list(recent_cmd_seen.items()):
            if exp <= now2:
                recent_cmd_seen.pop(k, None)
        # 清理过期的普通文本防抖
        for k, exp in list(recent_text_seen.items()):
            if exp <= now2:
                recent_text_seen.pop(k, None)
    logger.info(f"🧹 清理了 {len(stale)} 个会话")

# ==== 主入口 ====
def main():
    global ai_client, _control_offset, _last_msg_at, BOT_START_TS

    print("🔧 初始化 DeepSeek...")
    try: ai_client = OpenAI(api_key=DEEPSEEK_KEY, base_url=DEEPSEEK_BASE); print("✅")
    except Exception as e: print(f"❌ {e}"); return

    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # 启动 Worker 线程
    threading.Thread(target=ocr_worker, daemon=True).start()
    threading.Thread(target=ai_worker, daemon=True).start()
    time.sleep(0.3)

    print("🔧 连接微信...")
    try: wx = WeChat(ads=False)
    except Exception as e: print(f"❌ {e}"); return

    for s in wx.GetSession(): session_ts[s.name] = getattr(s, "time", "")

    # 初始化顶层会话 fingerprint 快照（必须在 session_ts 之后，防止启动误触发）
    init_top_session_snapshot(wx)

    # 初始化 control.jsonl 读取偏移（跳过已有历史，只处理启动后新增行）
    if CONTROL_FILE.exists():
        _control_offset = CONTROL_FILE.stat().st_size
    else:
        _control_offset = 0

    # CONTROL_TOKEN 安全检查
    if not CONTROL_TOKEN:
        logger.warning("⚠️ CONTROL_TOKEN 未设置，本地控制通道已禁用")
        print("⚠️ CONTROL_TOKEN 未设置，本地控制通道已禁用（请配置 .env 中的 CONTROL_TOKEN）")
        _control_offset = -1  # 标记禁用，不再轮询 control.jsonl

    # 初始化微信终端已读缓存，避免启动后执行历史命令
    init_wxterm_snapshot(wx)

    BOT_START_TS = time.time()
    _last_msg_at = BOT_START_TS

    logger.info(f"⏱ 机器人启动时间: {datetime.fromtimestamp(BOT_START_TS).strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("✅ 启动完成")
    print("🤖 DeepSeek V4 | Ctrl+C 停止")

    next_poll_at = time.time() + random.uniform(POLL_MIN, POLL_MAX)
    next_control_poll = time.time() + CONTROL_POLL_SEC
    next_wxterm_poll = time.time() + WXTERM_POLL_SEC
    try:
        while True:
            try:
                time.sleep(0.15)
                _flush_send(wx)

                now = time.time()

                # 控制通道轮询（高频，独立于会话轮询）
                if now >= next_control_poll:
                    next_control_poll = now + CONTROL_POLL_SEC
                    _poll_control_file()

                # 微信终端轮询（低频，避免抢 UI）
                if now >= next_wxterm_poll:
                    next_wxterm_poll = now + WXTERM_POLL_SEC
                    _poll_wx_terminal(wx)

                # 第3层：当前会话定点补偿（每个主循环 tick 都跑，极轻量）
                _poll_current_chat_compensation(wx)

                if now >= next_poll_at:
                    # 动态间隔：活跃时快，空闲时慢
                    since_msg = now - _last_msg_at
                    p_min, p_max = (POLL_MIN, POLL_MAX) if since_msg < 30 else (POLL_MIN * IDLE_MULT, POLL_MAX * IDLE_MULT)
                    next_poll_at = now + random.uniform(p_min, p_max)
                    _maybe_cleanup()
                    poll_sessions(wx)
                    _flush_send(wx)
            except Exception as e:
                logger.error(f"主循环错误: {e}")
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n👋 已停止")
        try:
            ai_queue.put_nowait(None)
        except queue.Full:
            pass
        try:
            ocr_queue.put_nowait(None)
        except queue.Full:
            pass

if __name__ == "__main__":
    main()
