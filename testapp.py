import streamlit as st
import google.generativeai as genai
import json
import time
import urllib.parse
import random

# ==========================================
# 系統設定與學術常數定義
# ==========================================

st.set_page_config(page_title="教育適性化評量系統", page_icon="🎓", layout="centered")

# [重要] API Key 設定 (資安修正版)
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

# ==========================================
# 核心邏輯函式
# ==========================================

def get_growth_mindset_feedback(correct_count, total_q):
    """
    根據成長型思維 (Growth Mindset) 生成豐富且隨機的正向回饋
    學術依據: Hattie & Timperley (2007) - Effective Feedback
    """
    ratio = correct_count / total_q
    
    if ratio == 1.0: # 100%
        messages = [
            {"title": "🌟 完美的表現！你是這個單元的小小專家！", "msg": "你展現了非常扎實的理解能力，這代表你之前的努力都得到了回報。試著挑戰更難的題目，繼續擴展你的知識邊界吧！"},
            {"title": "🏆 太棒了！完全制霸！", "msg": "你的細心與專注讓你獲得了滿分。請保持這份學習的熱情，你是其他同學的好榜樣！"},
            {"title": "🚀 實力超群！無懈可擊！", "msg": "你不僅掌握了概念，還能精準地應用。這個單元對你來說已經是輕而易舉，準備好迎接下一個挑戰了嗎？"}
        ]
    elif ratio >= 0.8: # 80-99%
        messages = [
            {"title": "👍 表現優異！只差一點點就全對囉！", "msg": "你已經掌握了絕大部分的關鍵概念。只要再多一點點細心，下次一定能拿滿分。回頭看看那道錯題，那是你變更強的關鍵！"},
            {"title": "✨ 很棒的成果！", "msg": "你的觀念非常清晰，大部分的問題都難不倒你。把那一點點小錯誤修正過來，你的知識網就完整了！"},
            {"title": "👏 令人印象深刻的表現！", "msg": "你做得很好！錯誤只是學習過程中的一個小插曲，它提醒我們還有哪些地方可以更精進。"}
        ]
    elif ratio >= 0.6: # 60-79%
        messages = [
            {"title": "🙂 做得不錯！基礎已經建立起來了！", "msg": "你已經懂了一半以上的內容，這是一個很好的開始。複習一下錯的題目，釐清那些模糊的觀念，你會進步神速喔！"},
            {"title": "🌱 持續進步中！", "msg": "學習就像馬拉松，你已經跑了一半了。現在是停下來檢查裝備（觀念）的好時機，把不清楚的地方弄懂，下半場會跑得更順！"},
            {"title": "💪 很好的嘗試！", "msg": "你已經掌握了核心概念。試著分析一下錯誤的原因，是看錯題目還是觀念混淆？只要修正這點，成績就會大幅提升。"}
        ]
    else: # < 60%
        messages = [
            {"title": "📖 很好的學習機會！我們一起從基礎加油！", "msg": "別氣餒，每一個錯誤都是變聰明的機會。現在我們發現了哪些觀念還不熟，這比全部答對更有價值，因為我們知道該往哪裡努力了！"},
            {"title": "💡 發現問題是解決問題的開始！", "msg": "這次測驗幫我們照亮了盲點。先別急著做新題目，花點時間把詳解看懂，把基礎打穩，下一次你一定會不一樣！"},
            {"title": "🧗 學習是一步一腳印的過程！", "msg": "現在覺得難是正常的，這代表你的大腦正在成長。多花一點時間在那些讓你困惑的題目上，堅持下去，你一定學得會！"}
        ]
    
    return random.choice(messages)

def generate_questions(subject, grade, unit, assess_type_key):
    """呼叫 Gemini API 生成題目"""
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
        
        if st.button("產生連結", type="primary", use_container_width=True):
            if not unit:
                st.warning("請輸入單元名稱")
                return
            
            if not base_url_input:
                st.error("⚠️ 請先填寫應用程式網址。如果您正在本機測試，可填入 http://localhost:8501")
                return

            base_url = base_url_input.rstrip("/")
            
            params = {
                "role": "student",
                "subject": subject,
                "grade": grade,
                "unit": unit,
                "type": assess_type
            }
            query_string = urllib.parse.urlencode(params)
            full_url = f"{base_url}/?{query_string}"
            
            st.success("連結已產生！請複製下方連結給學生：")
            st.code(full_url, language="text")
            st.caption("請複製上方連結傳送給學生。")
            
        st.markdown("---")
        st.markdown("### 🧪 教師試用")
        if st.button("教師自己先試做 (不需產生連結)", use_container_width=True):
            if not unit:
                st.warning("請輸入單元名稱")
            else:
                st.session_state.config = {'subject': subject, 'grade': grade, 'unit': unit, 'assess_type': assess_type}
                start_quiz_generation()

def render_student_welcome_screen():
    st.markdown("## 👋 歡迎來到線上評量")
    
    cfg = st.session_state.config
    subject_map = {'chinese': '國語', 'math': '數學', 'science': '自然科學', 'social': '社會'}
    
    st.info(f"📋 測驗資訊：{cfg['grade']} 年級 {subject_map.get(cfg['subject'], '')} - {cfg['unit']}")
    st.caption("本測驗將由 AI 老師為您即時生成題目，請放輕鬆作答。")
    
    if st.button("🚀 開始測驗", type="primary", use_container_width=True):
        start_quiz_generation()

def start_quiz_generation():
    """開始生成題目並重置相關狀態"""
    cfg = st.session_state.config
    with st.spinner("正在準備試卷中..."):
        questions = generate_questions(cfg['subject'], cfg['grade'], cfg['unit'], cfg['assess_type'])
        if questions:
            # 重置所有與題目相關的狀態
            st.session_state.questions = questions
            st.session_state.current_q_index = 0
            st.session_state.history = []
            st.session_state.generated_diagnosis = ""
            
            # [關鍵修正]：強制重置解析顯示狀態與使用者答案
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

    # [關鍵修正]：狀態防護，確保如果還沒作答，絕不顯示解析
    if st.session_state.user_answer is None:
        st.session_state.show_explanation = False

    current_q = questions[q_index]
    total_q = len(questions)

    st.progress((q_index + 1) / total_q)
    st.markdown(f"### Q{q_index + 1} / {total_q}")
    st.caption(f"🧠 認知層次：{current_q.get('bloomLevel', '綜合')}")
    st.markdown(f"#### {current_q['q']}")
    
    # [關鍵修正]：根據是否已顯示解析，來決定是否鎖定表單
    disable_interaction = st.session_state.show_explanation

    with st.form(key=f"q_form_{q_index}"):
        # [關鍵修正]：
        # 1. 綁定 index=st.session_state.user_answer 讓選過的答案在鎖定後依然顯示
        # 2. 設定 disabled=disable_interaction 防止重複提交
        # 3. 移除 timestamp key，確保提交後 Key 不變，能正確讀取狀態
        user_choice = st.radio(
            "請選擇答案：", 
            current_q['options'], 
            index=st.session_state.user_answer,
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

    # 取得豐富的回饋訊息
    feedback = get_growth_mindset_feedback(correct_count, total_q)

    st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
    st.title(feedback['title'])
    st.info(feedback['msg'])
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1: st.metric("答對題數", f"{correct_count}")
    with col2: st.metric("總題數", f"{total_q}")

    st.divider()

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
                    "assess_type": st.query_params["type"]
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