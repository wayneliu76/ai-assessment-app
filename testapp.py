import streamlit as st
import google.generativeai as genai
import json
import time
import urllib.parse
import random
import uuid
import hashlib

# ==========================================
# 系統設定與學術常數定義
# ==========================================

st.set_page_config(page_title="教育適性化評量系統", page_icon="🎓", layout="centered")

# [重要] API Key 設定
try:
    if "GOOGLE_API_KEY" in st.secrets:
        API_KEY = st.secrets["GOOGLE_API_KEY"]
        genai.configure(api_key=API_KEY)
    else:
        st.error("❌ 未偵測到 API Key。請設定 secrets.toml (本地) 或 Secrets (雲端)。")
        st.stop() 
except FileNotFoundError:
    st.error("❌ 找不到 secrets 檔案。請在專案根目錄建立 .streamlit/secrets.toml")
    st.stop()
except Exception as e:
    st.error(f"❌ 金鑰設定發生錯誤: {str(e)}")
    st.stop()

# [評量類型定義] 包含詳細的出題策略與理論基礎
ASSESSMENT_TYPES = {
    'placement': {
        'label': '安置性評量 (Placement)',
        'desc': '教學前評量，了解學生的起點行為與先備知識。',
        'prompt_instruction': """
        **核心目標**：檢測「先備知識 (Prerequisite Knowledge)」。
        **出題策略**：
        1. 請勿直接測驗本單元的新知識，而是測驗「學習本單元之前必須具備的舊經驗或技能」。
        2. 例如：若單元是「長除法」，請測驗「九九乘法」與「減法」能力。
        3. 難度設定：基礎 (Basic)。重點在於確認學生是否準備好進入新課程。
        """
    },
    'diagnostic': {
        'label': '診斷性評量 (Diagnostic)',
        'desc': '發現學生學習困難的成因與迷思概念。',
        'prompt_instruction': """
        **核心目標**：偵測「迷思概念 (Misconceptions)」。
        **出題策略**：
        1. 題目的重點在於「誘答項 (Distractors)」的設計。
        2. 錯誤選項不能是隨機產生的，必須對應學生常見的特定錯誤邏輯。
        3. 難度設定：中等，但強調鑑別度。
        """
    },
    'formative_small': {
        'label': '形成性評量-小單元 (Post-Lesson Check)',
        'desc': '剛上完課的即時檢測，確認基礎概念吸收，強調高成功率。',
        'prompt_instruction': """
        **核心目標**：檢核理解 (Check for Understanding) - 短週期評量。
        **理論依據**：Rosenshine 的高成功率原則。
        **出題策略**：
        1. 範圍鎖定於「剛教完」的特定小概念，不涉及跨單元整合。
        2. 難度設定：中等偏易 (Medium-Easy)。
        3. 目標是讓認真上課的學生能有 80% 以上的答對率，建立信心。
        4. 詳解重點在於「立即確認觀念正確性」。
        """
    },
    'formative_large': {
        'label': '形成性評量-大單元 (Unit Review)',
        'desc': '單元結束前的綜合練習，整合概念並加深記憶，難度較高。',
        'prompt_instruction': """
        **核心目標**：鞏固與整合 (Consolidation) - 中週期評量。
        **理論依據**：Bjork 的合適困難度 (Desirable Difficulties)。
        **出題策略**：
        1. 範圍涵蓋整個大單元，題目應包含跨概念的比較與整合。
        2. 難度設定：中偏難 (Medium-Hard)。需給予學生適度挑戰。
        3. 詳解重點在於「鷹架引導 (Scaffolding)」，教導學生如何串聯不同觀念解題。
        """
    },
    'summative': {
        'label': '總結性評量 (Summative)',
        'desc': '教學結束後，評斷學習成就與教學目標達成度。',
        'prompt_instruction': """
        **核心目標**：驗證「精熟程度 (Mastery)」。
        **出題策略**：
        1. 題目應涵蓋本單元的所有重要概念（廣度）。
        2. 包含應用題與跨概念的綜合題（深度）。
        3. 難度分佈：混合基礎題與進階挑戰題，以鑑別不同程度的學生。
        """
    }
}

# ==========================================
# 初始化 Session State
# ==========================================
if 'app_state' not in st.session_state:
    st.session_state.app_state = 'input' 
if 'questions' not in st.session_state:
    st.session_state.questions = []
if 'current_q_index' not in st.session_state:
    st.session_state.current_q_index = 0
if 'history' not in st.session_state:
    st.session_state.history = []
if 'show_explanation' not in st.session_state:
    st.session_state.show_explanation = False
if 'user_answer' not in st.session_state:
    st.session_state.user_answer = None
if 'generated_diagnosis' not in st.session_state:
    st.session_state.generated_diagnosis = ""
if 'config' not in st.session_state:
    st.session_state.config = {}
if 'student_name' not in st.session_state:
    st.session_state.student_name = "Unknown"
if 'num_questions' not in st.session_state:
    st.session_state.num_questions = 5

# [CSS 重構] 現代化 UI/UX 設計 - 高對比度與易讀性優化
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    :root {
        --primary-color: #4F46E5;
        --primary-hover: #4338CA;
        --bg-color: #F3F4F6;
        --card-bg: #FFFFFF;
        --text-main: #1F2937;
        --text-sub: #4B5563;
    }
    html, body, [class*="css"]:not([data-baseweb="menu"]):not([data-baseweb="popover"]) {
        font-family: 'Inter', sans-serif;
        color: var(--text-main) !important; 
        background-color: var(--bg-color);
    }
    .stApp {
        background-color: var(--bg-color);
        background-image: radial-gradient(#E5E7EB 1px, transparent 1px);
        background-size: 20px 20px;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #111827 !important;
        font-weight: 700;
        letter-spacing: -0.025em;
    }
    p, div, span {
        color: var(--text-main);
    }
    div[data-testid="stForm"], div[data-testid="stVerticalBlock"] > div[style*="background-color"] {
        background-color: var(--card-bg);
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        border: 1px solid #E5E7EB;
        margin-bottom: 1.5rem;
    }
    /* 輸入框高對比度修正 */
    div[data-baseweb="input"] > div {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D5DB !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="input"] input {
        color: #000000 !important;
        caret-color: #000000 !important;
        font-weight: 500 !important;
    }
    /* 代碼區塊高對比度修正 */
    div[data-testid="stCodeBlock"] {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D5DB !important;
        border-radius: 8px !important;
    }
    div[data-testid="stCodeBlock"] code {
        color: #000000 !important;
        font-family: 'Courier New', Courier, monospace !important;
    }
    /* 下拉選單 — 觸發框 */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #111827 !important;
        border: 2px solid #D1D5DB !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] div[class*="placeholder"],
    div[data-baseweb="select"] div[class*="singleValue"] {
        color: #111827 !important;
        font-weight: 500 !important;
    }
</style>
""", unsafe_allow_html=True)

# 用 JS 將 dropdown 樣式注入到 document.head，才能覆蓋 Streamlit portal 層
st.markdown("""
<script>
(function() {
    const css = `
        div[data-baseweb="popover"] { z-index: 9999 !important; }
        div[data-baseweb="menu"],
        div[data-baseweb="menu"] > div,
        div[data-baseweb="menu"] ul {
            background-color: #FFFFFF !important;
            border: 2px solid #4F46E5 !important;
            border-radius: 10px !important;
            box-shadow: 0 8px 24px rgba(79,70,229,0.2) !important;
            overflow: hidden !important;
        }
        div[data-baseweb="menu"] li {
            background-color: #FFFFFF !important;
            color: #111827 !important;
            border-bottom: 1px solid #E5E7EB !important;
            padding: 10px 16px !important;
            font-size: 0.95rem !important;
            font-weight: 600 !important;
            transition: all 0.15s ease !important;
        }
        div[data-baseweb="menu"] li:last-child { border-bottom: none !important; }
        div[data-baseweb="menu"] li div,
        div[data-baseweb="menu"] li span,
        div[data-baseweb="menu"] li p,
        div[data-baseweb="menu"] li * {
            color: #111827 !important;
            background-color: transparent !important;
        }
        div[data-baseweb="menu"] li:hover {
            background-color: #4F46E5 !important;
            color: #FFFFFF !important;
        }
        div[data-baseweb="menu"] li:hover *,
        div[data-baseweb="menu"] li:hover div,
        div[data-baseweb="menu"] li:hover span {
            color: #FFFFFF !important;
            background-color: transparent !important;
        }
        div[data-baseweb="menu"] li[aria-selected="true"] {
            background-color: #EEF2FF !important;
        }
        div[data-baseweb="menu"] li[aria-selected="true"] *,
        div[data-baseweb="menu"] li[aria-selected="true"] div,
        div[data-baseweb="menu"] li[aria-selected="true"] span {
            color: #4F46E5 !important;
            font-weight: 700 !important;
            background-color: transparent !important;
        }
    `;
    const style = document.createElement('style');
    style.id = 'dropdown-fix';
    style.textContent = css;
    // 移除舊的避免重複
    const old = document.getElementById('dropdown-fix');
    if (old) old.remove();
    document.head.appendChild(style);
})();
</script>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    /* Radio Button 選項高對比度修正 */
    div[role="radiogroup"] label {
        background-color: #FFFFFF !important;
        padding: 12px 16px !important;
        border-radius: 8px !important;
        border: 1px solid #E5E7EB !important;
        color: #1F2937 !important;
        margin-bottom: 8px !important;
        transition: all 0.2s ease;
    }
    div[role="radiogroup"] label p {
        color: #1F2937 !important;
        font-weight: 500 !important;
        font-size: 1rem !important;
    }
    div[role="radiogroup"] label:hover {
        border-color: var(--primary-color) !important;
        background-color: #EEF2FF !important;
    }
    div[role="radiogroup"] label:hover p {
        color: var(--primary-color) !important;
    }
    /* 按鈕樣式 */
    div.stButton > button {
        border-radius: 8px;
        font-weight: 600;
        border: 1px solid transparent;
        transition: all 0.2s;
        padding: 0.6rem 1.2rem;
        background-color: var(--primary-color);
        color: white !important;
    }
    div.stButton > button p {
        color: white !important;
    }
    div.stButton > button:hover {
        background-color: var(--primary-hover);
        box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.3);
        transform: translateY(-1px);
    }
    /* 送出按鈕特別強化 */
    div[data-testid="stFormSubmitButton"] button {
        background-color: #111827 !important;
        color: white !important;
        width: 100%;
        border-radius: 8px;
        padding: 0.75rem;
    }
    div[data-testid="stFormSubmitButton"] button:hover {
        background-color: #000000 !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    div[data-testid="stFormSubmitButton"] button p {
        color: white !important;
    }
    .stProgress > div > div > div > div {
        background-color: var(--primary-color);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 核心邏輯函式
# ==========================================

def get_growth_mindset_feedback(correct_count, total_q):
    """根據成長型思維生成正向回饋"""
    if total_q == 0:
        return {"title": "測驗完成", "msg": "沒有題目數據。"}
        
    ratio = correct_count / total_q
    
    if ratio == 1.0:
        messages = [
            {"title": "🌟 完美的表現！你是這個單元的小小專家！", "msg": "你展現了非常扎實的理解能力，這代表你之前的努力都得到了回報。試著挑戰更難的題目，繼續擴展你的知識邊界吧！"},
            {"title": "🏆 太棒了！完全制霸！", "msg": "你的細心與專注讓你獲得了滿分。請保持這份學習的熱情，你是其他同學的好榜樣！"}
        ]
    elif ratio >= 0.8:
        messages = [
            {"title": "👍 表現優異！只差一點點就全對囉！", "msg": "你已經掌握了絕大部分的關鍵概念。只要再多一點點細心，下次一定能拿滿分。回頭看看那道錯題，那是你變更強的關鍵！"},
            {"title": "✨ 很棒的成果！", "msg": "你的觀念非常清晰，大部分的問題都難不倒你。把那一點點小錯誤修正過來，你的知識網就完整了！"}
        ]
    elif ratio >= 0.6:
        messages = [
            {"title": "🙂 做得不錯！基礎已經建立起來了！", "msg": "你已經懂了一半以上的內容，這是一個很好的開始。複習一下錯的題目，釐清那些模糊的觀念，你會進步神速喔！"},
            {"title": "🌱 持續進步中！", "msg": "學習就像馬拉松，你已經跑了一半了。現在是停下來檢查裝備的好時機，把不清楚的地方弄懂，下半場會跑得更順！"}
        ]
    else:
        messages = [
            {"title": "📖 很好的學習機會！我們一起從基礎加油！", "msg": "別氣餒，每一個錯誤都是變聰明的機會。現在我們發現了哪些觀念還不熟，這比全部答對更有價值，因為我們知道該往哪裡努力了！"},
            {"title": "💡 發現問題是解決問題的開始！", "msg": "這次測驗幫我們照亮了盲點。先別急著做新題目，花點時間把詳解看懂，把基礎打穩，下一次你一定會不一樣！"}
        ]
    
    return random.choice(messages)

# ==========================================
# 全 Server 共享題庫（cache_resource = 跨所有 session 共用）
# 教師預先產生後，所有學生直接讀取，完全不打 API
# ==========================================

@st.cache_resource
def get_question_bank():
    """全 server 共享的題庫字典，key = 設定的 hash，value = 題目清單"""
    return {}

def _make_cache_key(subject, grade, unit, assess_type_key, num_questions):
    raw = f"{subject}|{grade}|{unit}|{assess_type_key}|{num_questions}"
    return hashlib.md5(raw.encode()).hexdigest()

def prefetch_question_bank(subject, grade, unit, assess_type_key, num_questions):
    """
    教師端主動呼叫：預先生成題庫並存入全 server 共享快取。
    之後所有學生 session 直接讀取，不再打 API。
    """
    bank = get_question_bank()
    key = _make_cache_key(subject, grade, unit, assess_type_key, num_questions)
    if key in bank:
        return True, "（已有快取，直接使用）"

    subject_map = {'chinese': '國語', 'math': '數學', 'science': '自然科學', 'social': '社會'}
    assess_info = ASSESSMENT_TYPES[assess_type_key]
    pool_size = max(num_questions * 3, 15)  # 題庫是需求量的 3 倍，最少 15 題

    prompt = f"""
    你是一位專業的台灣國小教師與教育測驗專家。請根據以下嚴格規範出 {pool_size} 題單選題作為題庫：

    1. **基本資訊**：
       - 對象：國小 {grade} 年級學生
       - 科目：{subject_map.get(subject, subject)}
       - 單元：{unit}
       - 語言：繁體中文 (台灣用語)

    2. **嚴格的課程綱要對齊 (Strict Curriculum Alignment)**：
       - **核心鐵律**：出題範圍必須嚴格限制在台灣教育部「十二年國民基本教育課程綱要」的 {grade} 年級學習內容。
       - **絕對禁止超綱**：
         - 自然科學 3-4 年級：嚴禁「電壓」「電阻」「化學式」「原子」等國中概念。
         - 數學 1-2 年級：嚴禁「分數」「小數」「除法」。3-4 年級：嚴禁「代數符號」「負數」「圓周率」。
       - 詞彙難度須符合 {grade} 年級認知發展階段。

    3. **評量類型專屬策略 (CRITICAL)**：
       這是一份「{assess_info['label']}」。請務必遵守以下出題邏輯：
       {assess_info['prompt_instruction']}

    4. **答案正確性自我驗證（CRITICAL — 最重要步驟）**：
       每出完一題，你必須在內心執行以下流程，再繼續下一題：
       - 步驟A【推導】：逐步寫出解題過程，得出答案。
       - 步驟B【核對】：確認你填入 "ans" 的索引（0=A, 1=B, 2=C, 3=D）對應的選項，確實等於步驟A得出的答案。
       - 步驟C【檢查誘答】：確認其他三個錯誤選項都確實是錯的。
       - **如果核對有誤，必須修正後才能輸出**。請將推導過程填入 "reasoning" 欄位（供教師審核用）。

    5. **數學符號規範**：請直接使用 Unicode（+, -, ×, ÷, =, >, <），嚴禁 LaTeX 語法。分數用 "1/2" 表示。

    請嚴格遵守以下 JSON 格式回傳，不要有任何 Markdown 標記：
    [
      {{
        "q": "題目內容",
        "options": ["選項A", "選項B", "選項C", "選項D"],
        "ans": 0,
        "reasoning": "【推導過程】逐步說明為何答案是選項A，以及其他三項為何錯誤。",
        "explanation": "詳細解析，針對學生錯誤提供鷹架引導。",
        "bloomLevel": "認知層次"
      }}
    ]
    """
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        questions = json.loads(text)
        # 數學科：用 Python 嘗試自動驗算，標記可疑題目
        if subject == 'math':
            questions = _verify_math_questions(questions)
        bank[key] = questions
        valid = sum(1 for q in questions if not q.get('_suspicious', False))
        return True, f"題庫已建立（共 {len(questions)} 題，其中 {valid} 題通過自動驗算）"
    except Exception as e:
        return False, f"生成失敗：{e}"

def _verify_math_questions(questions):
    """
    數學題自動驗算：嘗試用 Python eval 計算題目中的算式，
    若計算結果與標記答案不符，標記 _suspicious=True 供教師注意。
    """
    import re
    for q in questions:
        try:
            text = q['q']
            correct_option = q['options'][q['ans']]
            # 擷取題目中所有數字與算式，嘗試計算
            # 支援：加減乘除、括號
            expr_match = re.search(r'(\d+[\s]*[\+\-×÷\*\/][\s]*\d+(?:[\s]*[\+\-×÷\*\/][\s]*\d+)*)', text)
            if expr_match:
                expr = expr_match.group(1)
                expr_py = expr.replace('×', '*').replace('÷', '/').replace(' ', '')
                calculated = eval(expr_py)
                # 嘗試從正確選項中取出數字
                ans_num_match = re.search(r'(\d+(?:\.\d+)?)', correct_option)
                if ans_num_match:
                    ans_num = float(ans_num_match.group(1))
                    if abs(calculated - ans_num) > 0.01:
                        q['_suspicious'] = True
                        q['_verify_note'] = f"Python 計算 {expr_py} = {calculated}，但標記答案含 {ans_num}"
        except Exception:
            pass  # 無法解析的題目不標記，不影響流程
    return questions

def generate_questions(subject, grade, unit, assess_type_key, num_questions=5):
    """
    學生端取題：從全 server 共享題庫隨機抽取，不打 API。
    若題庫尚未建立（例如教師試用），則臨時生成。
    """
    if not API_KEY:
        st.error("未設定 API Key")
        return []

    bank = get_question_bank()
    key = _make_cache_key(subject, grade, unit, assess_type_key, num_questions)

    if key in bank:
        pool = bank[key].copy()
        random.shuffle(pool)
        return pool[:num_questions]

    # 題庫不存在（教師試用情境）→ 臨時生成，並順手存入快取
    ok, msg = prefetch_question_bank(subject, grade, unit, assess_type_key, num_questions)
    if ok and key in bank:
        pool = bank[key].copy()
        random.shuffle(pool)
        return pool[:num_questions]

    st.error("題目生成失敗，請稍後再試")
    return []
def generate_diagnosis(history_items, grade, subject, unit):
    """生成教師專用的簡短診斷"""
    if not API_KEY: return "未設定 API Key。"
    
    error_details = ""
    for idx, item in enumerate(history_items):
        q = item['question']
        error_details += f"錯題 {idx+1}: 題目[{q['q']}] 誤選[{q['options'][item['user_answer']]}] 正解[{q['options'][item['ans']]}]\n"

    prompt = f"""
    你是一位資深的教育心理學家。請根據以下學生的錯題紀錄，進行「極簡短」的診斷。
    
    背景：{grade}年級 {subject} ({unit})
    錯題紀錄：{error_details}

    **輸出要求**：
    請務必精簡，讓教師能在 **10秒內 (約30-50字)** 快速掌握重點。
    請直接使用以下格式列點：
    1. 核心迷思：(一句話點出最關鍵的錯誤觀念)
    2. 教學建議：(一句話提供具體解法)
    """
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        return model.generate_content(prompt).text
    except:
        return "無法生成診斷報告。"

# ==========================================
# 頁面渲染函式
# ==========================================

def render_teacher_input_screen():
    st.markdown("## 🎓 教育適性化評量系統 (教師端)")
    st.caption("設定評量參數並產生學生連結")

    with st.container(border=True):
        subject_map = {'chinese':'國語', 'math':'數學', 'science':'自然科學', 'social':'社會'}
        subject_keys = list(subject_map.keys())
        subject_labels = list(subject_map.values())
        subject_label = st.radio("科目領域", subject_labels, horizontal=True)
        subject = subject_keys[subject_labels.index(subject_label)]

        grade_labels = [f"{i} 年級" for i in range(1, 7)]
        grade_label = st.radio("年級", grade_labels, horizontal=True)
        grade = int(grade_label[0])
        
        unit = st.text_input("單元/主題關鍵字", placeholder="例如：分數的加減")
        
        num_questions = st.slider("題目數量", min_value=3, max_value=15, value=st.session_state.num_questions, step=1,
                                  help="設定本次測驗的題目總數（3～15 題）")
        st.session_state.num_questions = num_questions

        # 顯示評量類型的詳細說明，幫助教師選擇
        assess_type = st.radio("評量類型", 
                               options=['placement', 'diagnostic', 'formative_small', 'formative_large', 'summative'],
                               format_func=lambda x: f"{ASSESSMENT_TYPES[x]['label']} - {ASSESSMENT_TYPES[x]['desc']}")
        
        st.markdown("---")
        st.markdown("### 🔗 產生學生連結")
        
        with st.expander("❓ 如何讓學生使用？(必讀)"):
            st.markdown("""
            1. 此程式必須 **部署 (Deploy)** 到網路上 (如 Streamlit Cloud)。
            2. 部署後，您會獲得一個網址 (例如 `https://your-app.streamlit.app`)。
            3. 將該網址貼入下方欄位，即可產生專屬連結。
            4. 若您使用 `localhost`，學生將**無法**連線。
            """)

        base_url_input = st.text_input("請貼上您的應用程式網址 (例如 [https://....streamlit.app](https://....streamlit.app))", placeholder="請在此貼上瀏覽器上方的網址")
        
        if st.button("產生連結並預先建立題庫", type="primary", use_container_width=True):
            if not unit:
                st.warning("請輸入單元名稱")
                return
            
            if not base_url_input:
                st.error("⚠️ 請先填寫應用程式網址。如果您正在本機測試，可填入 http://localhost:8501")
                return

            # ── 步驟一：預先生成題庫（存入全 server 共享快取）──
            with st.spinner("⏳ 正在預先建立題庫，完成後學生才可掃碼進入..."):
                ok, msg = prefetch_question_bank(subject, grade, unit, assess_type, num_questions)

            if not ok:
                st.error(f"❌ 題庫建立失敗：{msg}，請重試。")
                return

            st.success(f"✅ 題庫已就緒！{msg} 現在可以將連結或 QR Code 發給學生。")

            # ── 步驟二：產生學生連結 ──
            base_url = base_url_input.rstrip("/")
            params = {
                "role": "student", "subject": subject, "grade": grade, "unit": unit, "type": assess_type,
                "num_q": num_questions
            }
            query_string = urllib.parse.urlencode(params)
            full_url = f"{base_url}/?{query_string}"
            
            st.code(full_url, language="text")
            
            # ── 步驟三：顯示 QR Code（無需安裝套件）──
            encoded_url = urllib.parse.quote(full_url, safe='')
            qr_img_url = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={encoded_url}&margin=10&color=1F2937&bgcolor=FFFFFF"
            col_qr1, col_qr2, col_qr3 = st.columns([1, 1, 1])
            with col_qr2:
                st.image(qr_img_url, caption="📱 學生掃描此 QR Code 即可開始測驗", width=240)
            st.caption("所有學生掃碼後將直接讀取已建立的題庫，不再重複呼叫 API。")
            
        st.markdown("---")
        st.markdown("### 🔍 題庫審核（建議發布前檢查）")
        bank = get_question_bank()
        review_key = _make_cache_key(subject, grade, unit, assess_type, num_questions)
        if review_key in bank:
            pool = bank[review_key]
            suspicious = [q for q in pool if q.get('_suspicious')]
            if suspicious:
                st.warning(f"⚠️ 有 {len(suspicious)} 題被自動驗算標記為**可疑**，建議優先檢查。")
            with st.expander(f"📋 檢視並編輯題庫（共 {len(pool)} 題）", expanded=False):
                to_delete = []
                for i, q in enumerate(pool):
                    label_color = "🔴" if q.get('_suspicious') else "🟢"
                    with st.container(border=True):
                        st.markdown(f"**{label_color} 第 {i+1} 題**" + (" ⚠️ *自動驗算可疑*" if q.get('_suspicious') else ""))
                        if q.get('_verify_note'):
                            st.caption(f"驗算備註：{q['_verify_note']}")
                        # 可編輯題目文字
                        new_q = st.text_area(f"題目_{i}", value=q['q'], key=f"edit_q_{review_key}_{i}", label_visibility="collapsed")
                        pool[i]['q'] = new_q
                        # 顯示選項與正確答案
                        for j, opt in enumerate(q['options']):
                            marker = "✅" if j == q['ans'] else "　"
                            new_opt = st.text_input(f"選項_{i}_{j}", value=opt, key=f"edit_opt_{review_key}_{i}_{j}", label_visibility="collapsed")
                            pool[i]['options'][j] = new_opt
                            if j == q['ans']:
                                st.caption(f"{marker} 目前正確答案")
                        # 修改正確答案
                        new_ans = st.radio(
                            "正確答案", options=[0,1,2,3],
                            format_func=lambda x: f"{['A','B','C','D'][x]}. {pool[i]['options'][x]}",
                            index=q['ans'], key=f"edit_ans_{review_key}_{i}", horizontal=True
                        )
                        pool[i]['ans'] = new_ans
                        # 顯示 reasoning
                        if q.get('reasoning'):
                            st.caption(f"🧠 AI 推導：{q['reasoning']}")
                        # 刪除按鈕
                        if st.button(f"🗑️ 刪除此題", key=f"del_{review_key}_{i}"):
                            to_delete.append(i)
                if to_delete:
                    bank[review_key] = [q for idx, q in enumerate(pool) if idx not in to_delete]
                    st.success(f"已刪除 {len(to_delete)} 題，題庫剩餘 {len(bank[review_key])} 題。")
                    st.rerun()
        else:
            st.info("請先點擊「產生連結並預先建立題庫」，再進行審核。")

        st.markdown("---")
        st.markdown("### 🧪 教師試用")
        if st.button("教師自己先試做", use_container_width=True):
            if not unit:
                st.warning("請輸入單元名稱")
            else:
                st.session_state.config = {'subject': subject, 'grade': grade, 'unit': unit, 'assess_type': assess_type, 'num_questions': num_questions}
                start_quiz_generation()

def render_student_welcome_screen():
    st.markdown("## 👋 歡迎來到線上評量")
    
    cfg = st.session_state.config
    subject_map = {'chinese': '國語', 'math': '數學', 'science': '自然科學', 'social': '社會'}
    
    st.info(f"📋 測驗資訊：{cfg['grade']} 年級 {subject_map.get(cfg['subject'], '')} - {cfg['unit']}")
    st.caption("本測驗將由 AI 老師為您即時生成題目，請放輕鬆作答。")
    
    # [新增] 學生姓名輸入
    student_name = st.text_input("請輸入您的姓名或座號", placeholder="例如：01 王小明")
    
    if st.button("🚀 開始測驗", type="primary", use_container_width=True):
        if not student_name:
            st.warning("請輸入姓名才能開始喔！")
        else:
            st.session_state.student_name = student_name
            start_quiz_generation()

def start_quiz_generation():
    """開始生成題目並重置相關狀態"""
    cfg = st.session_state.config
    with st.spinner("正在準備試卷中..."):
        questions = generate_questions(cfg['subject'], cfg['grade'], cfg['unit'], cfg['assess_type'], cfg.get('num_questions', 5))
        if questions:
            # 重置所有與題目相關的狀態
            st.session_state.questions = questions
            st.session_state.current_q_index = 0
            st.session_state.history = []
            st.session_state.generated_diagnosis = ""
            
            # 強制重置解析狀態
            st.session_state.show_explanation = False 
            st.session_state.user_answer = None 
            
            st.session_state.app_state = 'quiz'
            st.rerun()

def render_quiz_screen():
    q_index = st.session_state.current_q_index
    questions = st.session_state.questions
    
    if q_index >= len(questions):
        st.session_state.app_state = 'result'
        st.rerun()
        return

    # 狀態防護
    if st.session_state.user_answer is None:
        st.session_state.show_explanation = False

    current_q = questions[q_index]
    total_q = len(questions)

    st.progress((q_index + 1) / total_q)
    st.markdown(f"### Q{q_index + 1} / {total_q}")
    st.caption(f"🧠 認知層次：{current_q.get('bloomLevel', '綜合')}")
    st.markdown(f"#### {current_q['q']}")
    
    disable_interaction = st.session_state.show_explanation

    with st.form(key=f"q_form_{q_index}"):
        user_choice = st.radio(
            "請選擇答案：", 
            current_q['options'], 
            index=st.session_state.user_answer,
            # 移除 timestamp key，確保提交後可保持選取狀態
            key=f"radio_q{q_index}", 
            disabled=disable_interaction
        )
        submitted = st.form_submit_button("送出答案", disabled=disable_interaction)
    
    if submitted:
        if user_choice is None:
            st.warning("請先選擇一個答案")
        else:
            st.session_state.user_answer = current_q['options'].index(user_choice)
            st.session_state.show_explanation = True
            st.rerun()

    if st.session_state.show_explanation:
        ans_idx = current_q['ans']
        user_idx = st.session_state.user_answer
        is_correct = (ans_idx == user_idx)
        
        if is_correct: st.success("🎉 答對了！")
        else: st.error(f"💪 加油！正確答案是：{current_q['options'][ans_idx]}")
            
        with st.container(border=True):
            st.markdown(f"**📖 解析：**\n\n{current_q['explanation']}")
        
        if st.button("下一題 ➡️", use_container_width=True):
            st.session_state.history.append({
                'question': current_q, 'user_answer': user_idx, 'ans': ans_idx, 'isCorrect': is_correct
            })
            if q_index < total_q - 1:
                st.session_state.current_q_index += 1
                st.session_state.show_explanation = False
                st.session_state.user_answer = None
                st.rerun()
            else:
                st.session_state.app_state = 'result'
                st.rerun()

def render_result_screen():
    history = st.session_state.history
    correct_count = sum(1 for h in history if h['isCorrect'])
    total_q = len(history)
    config = st.session_state.config

    if correct_count == total_q: st.balloons()

    # 確保 total_q 不為 0
    feedback = get_growth_mindset_feedback(correct_count, total_q) if total_q > 0 else {"title": "Error", "msg": "無題目數據"}

    st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
    st.title(feedback['title'])
    st.info(feedback['msg'])
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1: st.metric("答對題數", f"{correct_count}")
    with col2: st.metric("總題數", f"{total_q}")

    st.divider()

    # 教師專用診斷 (Lazy Generation)
    incorrect_items = [h for h in history if not h['isCorrect']]
    if st.session_state.generated_diagnosis == "":
        if incorrect_items:
            # 確保 config 有值
            grade = config.get('grade', 'unknown')
            subject = config.get('subject', 'unknown')
            unit = config.get('unit', 'unknown')

            with st.spinner("AI 正在分析學習斷層..."):
                diag = generate_diagnosis(incorrect_items, grade, subject, unit)
                st.session_state.generated_diagnosis = diag
        else:
            st.session_state.generated_diagnosis = "表現優異，無顯著迷思概念。"

    with st.expander("👨‍🏫 教師專用：學習診斷分析"):
        st.markdown(st.session_state.generated_diagnosis)

    st.divider()
    
    if incorrect_items:
        st.subheader("📝 錯題回顧")
        for item in incorrect_items:
            q = item['question']
            with st.container(border=True):
                st.markdown(f"**Q: {q['q']}**")
                st.markdown(f"❌ 你的答案: {q['options'][item['user_answer']]}")
                st.markdown(f"✅ 正確答案: {q['options'][item['ans']]}")
                st.markdown(f"💡 **解析**: {q['explanation']}")

    if st.query_params.get("role") == "student":
        if st.button("🔄 再練習一次 (相同單元)", type="primary", use_container_width=True):
            st.session_state.app_state = 'student_ready' 
            start_quiz_generation()
    else:
        if st.button("🔄 回到首頁", type="primary", use_container_width=True):
            # 回到首頁時，徹底清空所有狀態，防止殘留
            st.session_state.app_state = 'input'
            st.session_state.questions = []
            st.session_state.history = []
            st.session_state.current_q_index = 0
            st.session_state.show_explanation = False
            st.session_state.user_answer = None
            st.session_state.generated_diagnosis = ""
            st.rerun()

# ==========================================
# 主程式進入點
# ==========================================

def main():
    if "role" in st.query_params and st.query_params["role"] == "student":
        if st.session_state.app_state == 'input':
            try:
                st.session_state.config = {
                    "subject": st.query_params["subject"],
                    "grade": st.query_params["grade"],
                    "unit": st.query_params["unit"],
                    "assess_type": st.query_params["type"],
                    "num_questions": int(st.query_params.get("num_q", 5))
                }
                st.session_state.app_state = 'student_ready'
            except Exception:
                st.error("連結參數有誤，請聯繫教師。")
                return

    if st.session_state.app_state == 'input':
        render_teacher_input_screen()
    elif st.session_state.app_state == 'student_ready':
        render_student_welcome_screen()
    elif st.session_state.app_state == 'quiz':
        render_quiz_screen()
    elif st.session_state.app_state == 'result':
        render_result_screen()

if __name__ == "__main__":
    main()