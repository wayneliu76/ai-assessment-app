import streamlit as st
import google.generativeai as genai
import json
import time
import urllib.parse

# ==========================================
# 系統設定與學術常數定義
# ==========================================

st.set_page_config(page_title="教育適性化評量系統", page_icon="🎓", layout="centered")

# [重要] API Key 設定
# 在雲端部署時，建議優先使用 st.secrets["GOOGLE_API_KEY"]
# 若無設定 secrets (或本地無 secrets.toml 檔案)，則使用下方寫入的 Key
try:
    if "GOOGLE_API_KEY" in st.secrets:
        API_KEY = st.secrets["GOOGLE_API_KEY"]
    else:
        # 若 secrets 存在但沒有該 Key，使用預設
        API_KEY = "AIzaSyCZt5Qi9naXRTv6HfHAArM9CX4NaW34F70"
except Exception:
    # 本地測試與開發用的 Key (當找不到 secrets.toml 檔案時會進入這裡)
    API_KEY = "AIzaSyCZt5Qi9naXRTv6HfHAArM9CX4NaW34F70" 

if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    st.warning("⚠️ 系統未偵測到 API Key。請在 secrets.toml 或程式碼中設定。")

# 評量類型定義
ASSESSMENT_TYPES = {
    'placement': {
        'label': '安置性評量',
        'desc': '在教學前對學生的起點行為進行評量，以了解學生的基礎能力和學習特質。',
        'difficulty_strategy': '易 (Easy) 至 中偏易。主要為 DOK Level 1。目標是確認學生具備「門檻能力」。'
    },
    'diagnostic': {
        'label': '診斷性評量',
        'desc': '旨在發現學生學習困難的成因，以提供教師補救教學的參考。',
        'difficulty_strategy': '中 (Medium)。主要為 DOK Level 2。重點在於「鑑別度」，設計強誘答力 (High Distractor Power) 的選項。'
    },
    'formative': {
        'label': '形成性評量',
        'desc': '提供教師及學生連續性的回饋資料，幫助了解教學過程中的學習成敗原因。',
        'difficulty_strategy': '中偏難 (Medium-Hard)。符合 "Desirable Difficulty" 理論。主要為 DOK Level 2-3。需提供鷹架引導。'
    },
    'summative': {
        'label': '總結性評量',
        'desc': '在教學告一段落時，評斷學生的學習成就及教學目標達成的程度。',
        'difficulty_strategy': '混合分佈 (Mixed)。包含易、中、難。涵蓋 DOK Level 1-4。測試遷移與精熟程度。'
    }
}

# ==========================================
# 初始化 Session State
# ==========================================
if 'app_state' not in st.session_state:
    st.session_state.app_state = 'input' # input, student_ready, quiz, result
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

# ==========================================
# 核心邏輯函式
# ==========================================

def generate_questions(subject, grade, unit, assess_type_key):
    """
    呼叫 Gemini API 生成題目
    """
    if not API_KEY:
        st.error("未設定 API Key")
        return []

    subject_map = {'chinese': '國語', 'math': '數學', 'science': '自然科學', 'social': '社會'}
    target_grade = int(grade)
    next_grade = target_grade + 1
    assess_info = ASSESSMENT_TYPES[assess_type_key]

    prompt = f"""
    你是一位專業的台灣國小教師與測驗編製專家。請根據以下嚴格的教學設計規範，出 5 題單選題：

    1. **對象**：國小 {grade} 年級學生
    2. **科目**：{subject_map.get(subject, subject)}
    3. **單元/主題**：{unit}
    4. **語言**：繁體中文 (台灣用語)
    
    5. **嚴格的年級適用性檢核 (Grade-Level Appropriateness & ZPD)**：
       - **核心原則**：請遵循 Bruner 的螺旋式課程理論，同一主題在不同年級有嚴格的深度界線。
       - **界線設定**：你目前出的是「{grade}年級」的題目。
         - **絕對禁止**使用 {next_grade} 年級或更高年級才會教到的概念。
       - **數字與詞彙限制**：必須符合 {grade} 年級學生的認知負荷 (Cognitive Load)。
    
    6. **評量類型與難度設計**：
       - 類型：{assess_info['label']} (注意：這是盲測，題目中不要提及評量類型)
       - 策略：{assess_info['difficulty_strategy']}

    請嚴格遵守以下 JSON 格式回傳，不要有任何 Markdown 標記。
    **JSON 格式規範 (CRITICAL)**：
    1. 必須是合法的 JSON Array。
    2. 若內容包含數學符號或 LaTeX (例如 frac)，**必須使用雙反斜線** 轉義 (例如：\\\\frac{{1}}{{2}})。
    
    [
      {{
        "q": "題目內容",
        "options": ["選項A", "選項B", "選項C", "選項D"],
        "ans": 0, // 0-3
        "explanation": "詳細解析。",
        "bloomLevel": "該題的認知層次" 
      }}
    ]
    """

    try:
        model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")
        response = model.generate_content(prompt)
        
        # 修復之前截斷的部分：正確清理 Markdown 標記
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        return json.loads(text)
    except Exception as e:
        st.error(f"題目生成失敗: {e}")
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

    **輸出要求 (CRITICAL)**：
    請務必精簡，讓教師能在 **10秒內 (約30-50字)** 快速掌握重點。
    請直接使用以下格式列點：
    1. 核心迷思：(一句話點出最關鍵的錯誤觀念)
    2. 教學建議：(一句話提供具體解法)
    """
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-preview-09-2025")
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
        col1, col2 = st.columns(2)
        with col1:
            subject = st.selectbox("科目領域", ['chinese', 'math', 'science', 'social'], 
                                   format_func=lambda x: {'chinese':'國語', 'math':'數學', 'science':'自然科學', 'social':'社會'}[x])
        with col2:
            grade = st.selectbox("年級", [1, 2, 3, 4, 5, 6], format_func=lambda x: f"{x} 年級")
        
        unit = st.text_input("單元/主題關鍵字", placeholder="例如：分數的加減")
        
        assess_type = st.radio("評量類型", 
                               options=['placement', 'diagnostic', 'formative', 'summative'],
                               format_func=lambda x: f"{ASSESSMENT_TYPES[x]['label']} - {ASSESSMENT_TYPES[x]['desc']}")
        
        # [修正] 增加「應用程式網址」輸入欄位與除錯指引
        st.markdown("---")
        st.markdown("### 🔗 產生學生連結")
        
        with st.expander("❓ 學生點開連結顯示「Access Denied」或無法連線？"):
            st.markdown("""
            若學生無法開啟連結，請檢查以下兩點：
            1. **部署狀態**：您的程式必須部署到網路 (如 Streamlit Cloud)，若是 `localhost` 網址，學生無法從外部連線。
            2. **公開權限**：若已部署，請至 Streamlit Dashboard，點擊 App 右側選單的 **Settings -> Sharing**，確保設定為 **Public (公開)**。
            """)

        st.info("請將您目前瀏覽器上方的網址 (例如 `https://xxx.streamlit.app`) 複製貼入下方：")
        base_url_input = st.text_input("您的應用程式網址 (Base URL)", value="http://localhost:8501")
        
        # 檢查是否為 localhost 並發出警告
        if "localhost" in base_url_input or "127.0.0.1" in base_url_input:
            st.warning("⚠️ 注意：`localhost` 網址僅能由您的電腦開啟。若要傳給學生，請務必先將程式部署至 Streamlit Cloud 並使用該公開網址。")

        # 處理網址結尾斜線，避免雙重斜線
        base_url = base_url_input.rstrip("/")

        if st.button("產生連結", type="primary", use_container_width=True):
            if not unit:
                st.warning("請輸入單元名稱")
                return
            
            # 建立 Query Parameters
            params = {
                "role": "student",
                "subject": subject,
                "grade": grade,
                "unit": unit,
                "type": assess_type
            }
            query_string = urllib.parse.urlencode(params)
            
            # 組合完整網址
            full_url = f"{base_url}/?{query_string}"
            
            st.success("連結已產生！請複製下方連結給學生：")
            st.code(full_url, language="text")
            
            # 教師也可以自己試做
            if st.button("或者，教師自己先試做"):
                st.session_state.config = {'subject': subject, 'grade': grade, 'unit': unit, 'assess_type': assess_type}
                start_quiz_generation()

def render_student_welcome_screen():
    """學生透過連結進入時看到的畫面"""
    st.markdown("## 👋 歡迎來到線上評量")
    
    # 從 session_state.config 讀取 (由 URL params 解析而來)
    cfg = st.session_state.config
    subject_map = {'chinese': '國語', 'math': '數學', 'science': '自然科學', 'social': '社會'}
    
    st.info(f"📋 測驗資訊：{cfg['grade']} 年級 {subject_map.get(cfg['subject'], '')} - {cfg['unit']}")
    st.caption("本測驗將由 AI 老師為您即時生成題目，請放輕鬆作答。")
    
    if st.button("🚀 開始測驗", type="primary", use_container_width=True):
        start_quiz_generation()

def start_quiz_generation():
    cfg = st.session_state.config
    with st.spinner("正在準備試卷中..."):
        questions = generate_questions(cfg['subject'], cfg['grade'], cfg['unit'], cfg['assess_type'])
        if questions:
            st.session_state.questions = questions
            st.session_state.current_q_index = 0
            st.session_state.history = []
            st.session_state.generated_diagnosis = ""
            st.session_state.app_state = 'quiz'
            st.rerun()

def render_quiz_screen():
    q_index = st.session_state.current_q_index
    questions = st.session_state.questions
    
    if q_index >= len(questions):
        st.session_state.app_state = 'result'
        st.rerun()
        return

    current_q = questions[q_index]
    total_q = len(questions)

    st.progress((q_index + 1) / total_q)
    st.markdown(f"### Q{q_index + 1} / {total_q}")
    # 隱藏評量類型標籤，僅保留認知層次 (盲測)
    st.caption(f"🧠 認知層次：{current_q.get('bloomLevel', '綜合')}")
    st.markdown(f"#### {current_q['q']}")
    
    with st.form(key=f"q_form_{q_index}"):
        user_choice = st.radio("請選擇答案：", current_q['options'], index=None)
        submitted = st.form_submit_button("送出答案")
    
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

    st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
    if correct_count == total_q:
        st.title("🌟 太棒了！完全掌握！")
    elif correct_count >= total_q / 2:
        st.title("👍 做得不錯！繼續加油！")
    else:
        st.title("📖 很好的學習機會！")
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1: st.metric("答對題數", f"{correct_count}")
    with col2: st.metric("總題數", f"{total_q}")

    st.divider()

    # 教師專用診斷 (摺疊)
    incorrect_items = [h for h in history if not h['isCorrect']]
    if st.session_state.generated_diagnosis == "":
        if incorrect_items:
            with st.spinner("AI 正在分析學習斷層..."):
                diag = generate_diagnosis(incorrect_items, config['grade'], config['subject'], config['unit'])
                st.session_state.generated_diagnosis = diag
        else:
            st.session_state.generated_diagnosis = "表現優異，無顯著迷思概念。"

    with st.expander("👨‍🏫 教師專用：學習診斷分析"):
        st.markdown(st.session_state.generated_diagnosis)

    st.divider()
    
    # 錯題回顧
    if incorrect_items:
        st.subheader("📝 錯題回顧")
        for item in incorrect_items:
            q = item['question']
            with st.container(border=True):
                st.markdown(f"**Q: {q['q']}**")
                st.markdown(f"❌ 你的答案: {q['options'][item['user_answer']]}")
                st.markdown(f"✅ 正確答案: {q['options'][item['ans']]}")
                st.markdown(f"💡 **解析**: {q['explanation']}")

    # 判斷是否為學生連結模式，決定按鈕行為
    if st.query_params.get("role") == "student":
        if st.button("🔄 再練習一次 (相同單元)", type="primary", use_container_width=True):
            # 學生模式：保留 config，只重置題目狀態
            st.session_state.app_state = 'student_ready' # 跳回學生準備頁，或直接 'quiz' 重新生成
            # 這裡選擇直接重新生成，體驗較順暢
            start_quiz_generation()
    else:
        if st.button("🔄 回到首頁", type="primary", use_container_width=True):
            st.session_state.app_state = 'input'
            st.session_state.questions = []
            st.session_state.history = []
            st.session_state.current_q_index = 0
            st.session_state.generated_diagnosis = ""
            st.rerun()

# ==========================================
# 主程式進入點 (路由邏輯)
# ==========================================

def main():
    # 1. 檢查 URL 參數 (Deep Linking)
    # 注意：st.query_params 是 Streamlit 1.30+ 的新 API
    # 邏輯：如果 URL 有參數，且 app_state 還在初始 input 狀態，則切換到學生模式
    if "role" in st.query_params and st.query_params["role"] == "student":
        if st.session_state.app_state == 'input':
            # 解析參數並寫入 config
            try:
                st.session_state.config = {
                    "subject": st.query_params["subject"],
                    "grade": st.query_params["grade"],
                    "unit": st.query_params["unit"],
                    "assess_type": st.query_params["type"]
                }
                st.session_state.app_state = 'student_ready'
            except Exception:
                st.error("連結參數有誤，請聯繫教師。")
                return

    # 2. 狀態機路由
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