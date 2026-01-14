import streamlit as st
import datetime
from openai import OpenAI
from ics import Calendar, Event
import json
import re

# ===========================
# 1. 配置区域
st.set_page_config(page_title="SmartCal 📅", page_icon="📅")
# ===========================
# 你的 API Key
try:
    # 优先读取 Secrets，如果读不到（比如本地运行），可以给个空值或者抛错
    # 注意：Secrets 的 Key 是区分大小写的，确保网页填的和这里写的一模一样
    if "VOLC_KEY" in st.secrets:
        API_KEY = st.secrets["VOLC_KEY"]
    else:
        st.error("未找到密钥，请在 Streamlit Secrets 中配置 VOLC_KEY")
        st.stop()
except FileNotFoundError:
    st.error("未找到 secrets.toml 文件")
    st.stop()

client = OpenAI(
    api_key=API_KEY,
    MODEL_ID = "ep-20260114192542-x5zx6"
    base_url="https://ark.cn-beijing.volces.com/api/v3"
)

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
# 4. 按钮点击逻辑
# ===========================
if st.button("✨ 生成日历文件"):
    if not text_input:
        st.warning("请先粘贴点东西进去！")
    else:
        with st.spinner("AI 正在分析时间地点..."):
            event_data = extract_event_info(text_input)
            
            if event_data:
                st.success("提取成功！")
                
                # 展示关键信息
                col1, col2 = st.columns(2)
                col1.metric("标题", event_data.get('title', '无标题'))
                col1.metric("时间", event_data.get('start_time', '未知'))
                
                # 调试折叠面板
                with st.expander("查看原始 JSON 数据"):
                    st.json(event_data)

                # 生成 .ics 文件
                try:
                    c = Calendar()
                    e = Event()
                    e.name = event_data.get('title', 'New Event')
                    
                    # 时间容错处理
                    if event_data.get('start_time'):
                        try:
                            e.begin = event_data.get('start_time')
                        except:
                            st.warning("时间格式解析有点小问题，尝试自动修正...")
                            e.begin = datetime.datetime.now() # 兜底

                    if event_data.get('end_time'):
                        try:
                            e.end = event_data.get('end_time')
                        except:
                            pass # 如果结束时间不对，就不填结束时间
                            
                    e.location = event_data.get('location', '')
                    e.description = event_data.get('description', '') + "\n(Generated by SmartCal)"
                    c.events.add(e)

                    st.download_button(
                        label="📥 点击下载 .ics 文件",
                        data=str(c),
                        file_name="smartcal_event.ics",
                        mime="text/calendar"
                    )
                except Exception as e:
                    st.error(f"生成日历文件时出错: {e}")