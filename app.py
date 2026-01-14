import streamlit as st
import datetime
from openai import OpenAI
from ics import Calendar, Event
import json
import re

# ===========================
# 1. 第一步：必须最先配置页面 (这是解决闪烁的关键！)
# ===========================
st.set_page_config(page_title="SmartCal 📅", page_icon="📅")

# ===========================
# 2. 第二步：读取 Secrets 中的 Key
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
) 

# 你的推理接入点 ID
MODEL_ID = "ep-20260114192542-x5zx6"

# ===========================
# 4. 页面布局设计
# ===========================
st.title("📅 SmartCal: 智能日程提取")
st.caption(f"当前使用的模型接入点: {MODEL_ID}")

text_input = st.text_area("在此粘贴通知文本...", height=150, 
                          placeholder="例如：本周五下午3点在主楼203开年级大会，记得带笔。")

# ===========================
# 5. 核心逻辑：AI 提取信息
# ===========================
def extract_event_info(text):
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
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]
        )
        
        content = response.choices[0].message.content
        print("AI 原始回复:", content)

        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            clean_json = match.group()
            return json.loads(clean_json)
        else:
            return json.loads(content)

    except Exception as e:
        st.error(f"AI 调用失败: {e}")
        return None

# ===========================
# 6. 按钮点击逻辑 (时区终极修正版)
# ===========================
if st.button("✨ 生成日历文件"):
    if not text_input:
        st.warning("请先粘贴点东西进去！")
    else:
        with st.spinner("AI 正在分析时间地点..."):
            event_data = extract_event_info(text_input)
            
            if event_data:
                st.success("提取成功！")
                
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
                    
                    # === ⏰ 时区处理核心逻辑 ===
                    # 目标：把 "2026-01-15 10:00:00" (北京) -> 转换成 -> "2026-01-15 02:00:00" (UTC)
                    
                    # 定义时区
                    tz_beijing = datetime.timezone(datetime.timedelta(hours=8)) # 北京是 UTC+8
                    tz_utc = datetime.timezone.utc # 世界标准时间

                    start_str = event_data.get('start_time')
                    end_str = event_data.get('end_time')

                    # 处理开始时间
                    if start_str:
                        try:
                            # 1. 把字符串变成时间对象 (默认为“无时区身份”)
                            dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                            # 2. 给它发身份证：你是“北京时间”
                            dt = dt.replace(tzinfo=tz_beijing)
                            # 3. 换算成“世界时间” (关键一步！这里会自动减8小时)
                            dt_utc = dt.astimezone(tz_utc)
                            e.begin = dt_utc
                        except ValueError:
                            # 兜底：如果格式不对，直接存字符串，交给手机自己猜
                            e.begin = start_str

                    # 处理结束时间
                    if end_str:
                        try:
                            dt = datetime.datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                            dt = dt.replace(tzinfo=tz_beijing)
                            dt_utc = dt.astimezone(tz_utc)
                            e.end = dt_utc
                        except:
                            pass 

                    e.location = event_data.get('location', '')
                    e.description = event_data.get('description', '') + "\n(Generated by SmartCal)"
                    
                    c.events.add(e)

                    st.download_button(
                        label="📥 点击下载 .ics 文件",
                        data=c.serialize(),
                        file_name="smartcal_event.ics",
                        mime="text/calendar"
                    )
                except Exception as e:
                    st.error(f"生成日历文件时出错: {e}")