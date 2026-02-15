import ccxt
import pandas as pd
import mplfinance as mpf
import google.generativeai as genai
import asyncio
import os
import io
import json
from telegram import Bot

# --- CONFIGURATION (Secrets වලින් දත්ත ගනී) ---
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHAT_ID"]

# Sticker ID
STICKER_ID = "CAACAgUAAxkBAAEQZgNpf0jTNnM9QwNCwqMbVuf-AAE0x5oAAvsKAAIWG_BWlMq--iOTVBE4BA"

# Gemini Setup
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-exp') 

# Binance Setup
exchange = ccxt.binance()

# --- 1. DATA COLLECTION & CHARTING ---
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

# --- 2. TARGET LIST (Top 5 Coins) ---
def get_top_candidates():
    targets = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
    print(f"🎯 Targeting: {targets}")
    return targets

# --- 3. GEMINI ANALYSIS ---
async def analyze_with_gemini(symbol):
    print(f"🤖 Analyzing {symbol}...")
    try:
        df_4h = get_market_data(symbol, '4h')
        df_1h = get_market_data(symbol, '1h')
        df_15m = get_market_data(symbol, '15m')
        df_5m = get_market_data(symbol, '5m')
        
        img_4h = generate_chart_image(df_4h, f"{symbol} 4H")
        img_1h = generate_chart_image(df_1h, f"{symbol} 1H")
        img_15m = generate_chart_image(df_15m, f"{symbol} 15m")
        img_5m = generate_chart_image(df_5m, f"{symbol} 5m")
        
        prompt = """
        Role: Expert Crypto Trader.
        Task: Analyze charts for a HIGH PROBABILITY entry (Scalp/Day Trade).
        
        Output JSON ONLY with these exact keys:
        {
            "decision": "BUY" or "SELL" or "WAIT",
            "entry": numeric_price,
            "stop_loss": numeric_price,
            "tp1": numeric_price,
            "tp2": numeric_price,
            "tp3": numeric_price,
            "tp4": numeric_price,
            "reason": "Short reason"
        }
        """
        
        from PIL import Image
        images = [Image.open(img_4h), Image.open(img_1h), Image.open(img_15m), Image.open(img_5m)]
        
        response = model.generate_content([prompt, *images])
        return response.text
    except Exception as e:
        print(f"Analysis Error: {e}")
        return None

# --- 4. TELEGRAM SENDER ---
async def send_formatted_signal(coin, data):
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        # Sticker
        await bot.send_sticker(chat_id=CHANNEL_ID, sticker=STICKER_ID)
        await asyncio.sleep(5)
        
        # Data Prep
        decision = data.get('decision', 'WAIT').upper()
        entry = float(data.get('entry', 0))
        sl = float(data.get('stop_loss', 0))
        
        if entry == 0: return

        tp1 = float(data.get('tp1', entry * (1.01 if decision == "BUY" else 0.99)))
        tp2 = float(data.get('tp2', entry * (1.02 if decision == "BUY" else 0.98)))
        tp3 = float(data.get('tp3', entry * (1.03 if decision == "BUY" else 0.97)))
        tp4 = float(data.get('tp4', entry * (1.04 if decision == "BUY" else 0.96)))

        if decision == "SELL":
            direction_txt = "🔴Short"
        else:
            direction_txt = "🟢Long"
            
        def get_perc(price):
            if entry == 0: return 0.0
            val = abs(price - entry) / entry * 100 * 50
            return round(val, 1)

        risk = abs(entry - sl)
        reward = abs(entry - tp4)
        rr = round(reward / risk, 1) if risk > 0 else 0
        coin_display = coin.replace('/USDT', ' USDT')

        msg = f"""💎CRYPTO CAMPUS VIP💎

🌑 {coin_display}

{direction_txt}

🚀Isolated
📈Leverage 50X

💥Entry {entry}

✅Take Profit

1️⃣ {tp1} ({get_perc(tp1)}%)
2️⃣ {tp2} ({get_perc(tp2)}%)
3️⃣ {tp3} ({get_perc(tp3)}%)
4️⃣ {tp4} ({get_perc(tp4)}%)

⭕ Stop Loss {sl} ({get_perc(sl)}%)

📝 RR 1:{rr}

⚠️ Margin Use 1%-5%(Trading Plan Use)"""

        await bot.send_message(chat_id=CHANNEL_ID, text=msg)
        print(f"✅ Signal sent for {coin}")
        
    except Exception as e:
        print(f"Telegram Error: {e}")

# --- MAIN LOOP ---
async def main():
    candidates = get_top_candidates()
    
    # 1. මාකට් එක Analyze කරනවා
    for coin in candidates:
        try:
            analysis_text = await analyze_with_gemini(coin)
            if not analysis_text: continue

            cleaned_text = analysis_text.replace("```json", "").replace("```", "").strip()
            
            try:
                data = json.loads(cleaned_text)
            except:
                continue
            
            decision = data.get('decision', 'WAIT')
            print(f"{coin}: {decision}")
            
            if decision != "WAIT":
                await send_formatted_signal(coin, data)
                
        except Exception as e:
            print(f"Loop Error {coin}: {e}")

    # 2. වැඩේ ඉවර වුණාම Status Update එක යවනවා
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=CHANNEL_ID, text="මම ඉන්නවා තුමනි 🫡")
        print("✅ Status Update Sent!")
    except Exception as e:
        print(f"Status Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
