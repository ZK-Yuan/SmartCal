import streamlit as st
import datetime
from openai import OpenAI
from ics import Calendar, Event
import json
import re

# ===========================
# 1. 必须最先配置页面
# ===========================
st.set_page_config(page_title="SmartCal 📅", page_icon="📅")

# ===========================
# 2. 读取 Secrets 中的 Key
# ===========================
try:
    # 检查 secrets 是否存在 VOLC_KEY
    if "VOLC_KEY" in st.secrets:
        API_KEY = st.secrets["VOLC_KEY"]
    else:
        st.error("未找到密钥，请在 Streamlit Secrets 中配置 VOLC_KEY")
        st.stop()
except FileNotFoundError:
    st.error("未找到 secrets.toml 文件，请检查 Streamlit 部署设置")
    st.stop()

# ===========================
# 3. 初始化客户端
# ===========================
client = OpenAI(
    api_key=API_KEY,
    base_url="https://ark.cn-beijing.volces.com/api/v3"
)  # <--- 关键点：一定要有这个右括号！

# 你的推理接入点 ID
MODEL_ID = "ep-20260114192542-x5zx6"

# ===========================
# 2. 页面布局设计
# ===========================
st.set_page_config(page_title="SmartCal 📅", page_icon="📅")
st.title("📅 SmartCal: 智能日程提取")
st.caption(f"当前使用的模型接入点: {MODEL_ID}")

text_input = st.text_area("在此粘贴通知文本...", height=150, 
                          placeholder="例如：本周五下午3点在主楼203开年级大会，记得带笔。")

# ===========================
# 3. 核心逻辑：AI 提取信息
# ===========================
def extract_event_info(text):
    # 获取当前时间，告诉 AI "今天" 是几号
    current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %A %H:%M")
    
    system_prompt = f"""
    你是一个日程提取助手。当前时间是：{current_time_str}。
    请从用户输入的文本中提取日程信息，并输出为纯 JSON 字符串。
    
    【重要】不要输出 Markdown 标记（如 ```json ... ```），直接输出 {{ ... }}。
    
    JSON 字段要求：
    - title: 事件标题
    - start_time: 开始时间 (格式 YYYY-MM-DD HH:MM:SS)
    - end_time: 结束时间 (格式 YYYY-MM-DD HH:MM:SS)。如果未提及，默认开始后1小时。
    - location: 地点 (如果没有则为空字符串)
    - description: 备注/原文摘要
    """

    try:
        # 使用标准的 chat.completions 接口调用你的 Endpoint
        response = client.chat.completions.create(
            model=MODEL_ID,  # 填入你的 ep-xxxx ID
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]
        )
        
        content = response.choices[0].message.content
        print("AI 原始回复:", content) # 方便在终端调试

        # === 清洗数据的逻辑 (双重保险) ===
        # 有时候 AI 还是会忍不住加 Markdown，这里用正则提取纯 JSON
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            clean_json = match.group()
            return json.loads(clean_json)
        else:
            # 如果正则没匹配到，尝试直接解析
            return json.loads(content)

    except Exception as e:
        st.error(f"AI 调用失败: {e}")
        st.info("💡 提示：请检查 API Key 是否过期，或者 Endpoint ID 是否拼写正确。")
        return None

# ===========================
# 4. 按钮点击逻辑 (修改了时间处理部分)
# ===========================
if st.button("✨ 生成日历文件"):
    if not text_input:
        st.warning("请先粘贴点东西进去！")
    else:
        with st.spinner("AI 正在分析时间地点..."):
            event_data = extract_event_info(text_input)
            
            if event_data:
                st.success("提取成功！")
                
                # --- 新增：定义北京时区 ---
                beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
                
                # 展示信息
                col1, col2 = st.columns(2)
                col1.metric("标题", event_data.get('title', '无标题'))
                col1.metric("时间", event_data.get('start_time', '未知'))
                
                with st.expander("查看原始 JSON 数据"):
                    st.json(event_data)

                # 生成 .ics 文件
                try:
                    c = Calendar()
                    e = Event()
                    e.name = event_data.get('title', 'New Event')
                    
                    # --- 核心修改：强制加上北京时区 ---
                    # 1. 拿到时间字符串 (例如 "2026-01-15 14:00:00")
                    start_str = event_data.get('start_time')
                    end_str = event_data.get('end_time')

                    # 2. 解析成 Python 时间对象，并贴上北京时区标签
                    # 注意：这里假设 AI 听话地输出了 YYYY-MM-DD HH:MM:SS 格式
                    if start_str:
                        try:
                            # 尝试解析标准格式
                            dt_start = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                            # 替换为北京时区
                            dt_start = dt_start.replace(tzinfo=beijing_tz)
                            e.begin = dt_start
                        except ValueError:
                            # 如果 AI 格式乱了，尝试用 arrow 自动解析 (ics 库自带能力)，但手动加 +08:00
                            e.begin = start_str + "+08:00"

                    if end_str:
                        try:
                            dt_end = datetime.datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                            dt_end = dt_end.replace(tzinfo=beijing_tz)
                            e.end = dt_end
                        except:
                            pass # 结束时间容错

                    e.location = event_data.get('location', '')
                    e.description = event_data.get('description', '') + "\n(Generated by SmartCal)"
                    
                    c.events.add(e)

                    # ⬇️ 修改了这一行：用 c.serialize() 替代 str(c)
                    st.download_button(
                        label="📥 点击下载 .ics 文件",
                        data=c.serialize(), 
                        file_name="smartcal_event.ics",
                        mime="text/calendar"
                    )
                except Exception as e:
                    st.error(f"生成日历文件时出错: {e}")
