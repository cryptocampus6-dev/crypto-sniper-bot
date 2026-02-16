import streamlit as st
import ccxt
import pandas as pd
import mplfinance as mpf
import google.generativeai as genai
import asyncio
import os
import io
import json
import time
from datetime import datetime
import pytz
from telegram import Bot

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="GHOST VISION X",
    page_icon="👻",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SECRETS SETUP ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    CHANNEL_ID = st.secrets["TELEGRAM_CHAT_ID"]
except:
    st.warning("⚠️ Please set up your Secrets in Streamlit Cloud!")
    st.stop()

STICKER_ID = "CAACAgUAAxkBAAEQZgNpf0jTNnM9QwNCwqMbVuf-AAE0x5oAAvsKAAIWG_BWlMq--iOTVBE4BA"

# --- INIT SESSION STATE ---
if 'running' not in st.session_state:
    st.session_state['running'] = False
if 'coins' not in st.session_state:
    st.session_state['coins'] = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
if 'signal_count' not in st.session_state:
    st.session_state['signal_count'] = 0
if 'logs' not in st.session_state:
    st.session_state['logs'] = []

# --- SETUP API ---
genai.configure(api_key=GEMINI_API_KEY)

# CORRECT MODEL: 1.5 Flash (Library update එකෙන් පස්සේ මේක වැඩ කරනවා)
model = genai.GenerativeModel('gemini-1.5-flash') 
exchange = ccxt.binanceus()

# --- HELPER FUNCTIONS ---
def get_sri_lanka_time():
    tz = pytz.timezone('Asia/Colombo')
    return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

def get_market_data(symbol, timeframe, limit=100):
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def generate_chart_image(df, title):
    buf = io.BytesIO()
    s = mpf.make_mpf_style(base_mpf_style='charles', gridstyle='', y_on_right=False)
    mpf.plot(df, type='candle', volume=True, title=title, style=s, savefig=buf)
    buf.seek(0)
    return buf

async def send_telegram_msg(msg, sticker=False):
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        if sticker:
            await bot.send_sticker(chat_id=CHANNEL_ID, sticker=STICKER_ID)
            await asyncio.sleep(5)
        await bot.send_message(chat_id=CHANNEL_ID, text=msg)
    except Exception as e:
        st.error(f"Telegram Error: {e}")

async def analyze_coin(coin, log_placeholder, progress_bar):
    try:
        # 1. Data Collection
        df_4h = get_market_data(coin, '4h')
        df_1h = get_market_data(coin, '1h')
        df_15m = get_market_data(coin, '15m')
        df_5m = get_market_data(coin, '5m')
        
        current_price = df_5m.iloc[-1]['close']
        
        # 2. Image Generation
        img_4h = generate_chart_image(df_4h, f"{coin} 4H")
        img_1h = generate_chart_image(df_1h, f"{coin} 1H")
        img_15m = generate_chart_image(df_15m, f"{coin} 15m")
        img_5m = generate_chart_image(df_5m, f"{coin} 5m")

        # 3. Gemini Vision Analysis
        prompt = """
        Role: Expert Crypto Trader (SMC Strategy).
        Task: Analyze 4 charts for a SCALP entry.
        Output JSON ONLY:
        {
            "decision": "BUY" or "SELL" or "WAIT",
            "entry": price,
            "stop_loss": price,
            "tp1": price,
            "tp2": price,
            "tp3": price,
            "tp4": price
        }
        """
        from PIL import Image
        images = [Image.open(img_4h), Image.open(img_1h), Image.open(img_15m), Image.open(img_5m)]
        
        response = model.generate_content([prompt, *images])
        text = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        
        decision = data.get('decision', 'WAIT')
        
        # Log Result
        timestamp = get_sri_lanka_time()
        
        if decision == "WAIT":
             log_entry = f"🕒 {timestamp} | {coin} | WAIT | Price: {current_price}"
             st.session_state['logs'].insert(0, log_entry)
        else:
             st.session_state['signal_count'] += 1
             log_entry = f"🚀 {timestamp} | {coin} | **{decision}** | Entry: {data.get('entry')}"
             st.session_state['logs'].insert(0, log_entry)
             
             entry = float(data.get('entry', 0))
             sl = float(data.get('stop_loss', 0))
             tp1 = float(data.get('tp1', entry * 1.01))
             tp2 = float(data.get('tp2', entry * 1.02))
             tp3 = float(data.get('tp3', entry * 1.03))
             tp4 = float(data.get('tp4', entry * 1.04))

             def calc_profit(target):
                 return round(abs(target - entry) / entry * 100 * 50, 1) if entry > 0 else 0

             risk = abs(entry - sl)
             reward = abs(entry - tp4)
             rr = round(reward / risk, 1) if risk > 0 else 0.0
             emoji = "🔴Short" if decision == "SELL" else "🟢Long"
             
             msg = f"""💎CRYPTO CAMPUS VIP💎

🌑 {coin.replace('/USDT', ' USDT')}

{emoji}

🚀Isolated
📈Leverage 50X

💥Entry {entry}

✅Take Profit
1️⃣ {tp1} ({calc_profit(tp1)}%)
2️⃣ {tp2} ({calc_profit(tp2)}%)
3️⃣ {tp3} ({calc_profit(tp3)}%)
4️⃣ {tp4} ({calc_profit(tp4)}%)

⭕ Stop Loss {sl} ({calc_profit(sl)}%)

📝 RR 1:{rr}

⚠️ Margin Use 1%-5%(Trading Plan Use)"""
             
             await send_telegram_msg(msg, sticker=True)
             st.toast(f"Signal Sent for {coin}!", icon="🔥")

    except Exception as e:
        st.error(f"Error analyzing {coin}: {e}")

# --- SIDEBAR UI ---
with st.sidebar:
    st.header("🎲 Control Panel")
    
    status_color = "green" if st.session_state['running'] else "red"
    status_text = "RUNNING" if st.session_state['running'] else "STOPPED"
    st.markdown(f"Status: **:{status_color}[{status_text}]**")
    
    st.metric("Daily Signals", f"{st.session_state['signal_count']}/10")
    
    col_btn1, col_btn2 = st.columns(2)
    if col_btn1.button("▶ START", use_container_width=True):
        st.session_state['running'] = True
        st.rerun()
    if col_btn2.button("⏹ STOP", use_container_width=True):
        st.session_state['running'] = False
        st.rerun()
        
    st.markdown("---")
    
    st.subheader("Coin Manager")
    new_coin = st.text_input("Add Coin (e.g. DOGE/USDT)")
    if st.button("Add"):
        if new_coin and new_coin not in st.session_state['coins']:
            st.session_state['coins'].append(new_coin)
            st.success(f"Added {new_coin}")
    
    coin_to_remove = st.selectbox("Remove Coin", st.session_state['coins'])
    if st.button("Delete"):
        if coin_to_remove in st.session_state['coins']:
            st.session_state['coins'].remove(coin_to_remove)
            st.rerun()
            
    st.markdown("---")
    if st.button("🚀 Test Telegram"):
        asyncio.run(send_telegram_msg("🔔 Test Notification from GHOST VISION X", sticker=False))
        st.success("Test Sent!")

# --- MAIN DASHBOARD UI ---
st.title("👻 GHOST VISION X 🚀")
st.caption(f"🇱🇰 Sri Lanka Time: {get_sri_lanka_time()}")

tab1, tab2 = st.tabs(["📊 Vision Scanner", "📜 Signal History"])

with tab1:
    status_container = st.container()
    
    if st.session_state['running']:
        status_container.info("👁️ AI Scanning with Gemini 1.5 Flash (Fast & Free)...")
        my_bar = status_container.progress(0)
        log_placeholder = st.empty()
        
        scan_placeholder = st.empty()
        
        with scan_placeholder.container():
            coins = st.session_state['coins']
            total_coins = len(coins)
            
            for i, coin in enumerate(coins):
                log_placeholder.markdown(f"**👀 Checking:** `{coin}` ...")
                
                asyncio.run(analyze_coin(coin, log_placeholder, my_bar))
                
                my_bar.progress((i + 1) / total_coins)
                
                # SPEED BREAKER: API Limit නොවදින්න තත්පර 30ක් ඉන්නවා
                log_placeholder.caption(f"💤 Cooling down... (30s) to avoid API limit")
                time.sleep(30) 
            
            st.success("✅ Cycle Complete. Waiting for next scan...")
            time.sleep(60) 
            st.rerun()
            
    else:
        status_container.warning("⚠️ Bot is STOPPED. Click START in the sidebar.")

with tab2:
    st.subheader("Signal Logs")
    for log in st.session_state['logs']:
        st.markdown(log)
