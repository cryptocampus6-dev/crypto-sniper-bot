import ccxt
import pandas as pd
import mplfinance as mpf
import google.generativeai as genai
import asyncio
import os
import io
from telegram import Bot

# --- CONFIGURATION (Secrets වලින් දත්ත ගනී) ---
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHAT_ID"]

# Gemini Setup
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-exp') # හෝ gemini-1.5-flash

# Binance Setup (Public Data)
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
    # SMC පෙනුමට Chart එක (Grid ඉවත් කර, Colors වෙනස් කර)
    s = mpf.make_mpf_style(base_mpf_style='charles', gridstyle='', y_on_right=False)
    mpf.plot(df, type='candle', volume=True, title=title, style=s, savefig=buf)
    buf.seek(0)
    return buf

# --- 2. THE PYTHON FILTER (Candidates තෝරාගැනීම) ---
def get_top_candidates():
    # වෙලාව ඉතිරි කරගන්න අපි Top 20 Coins විතරක් බලමු දැනට
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 
               'ADA/USDT', 'AVAX/USDT', 'DOGE/USDT', 'TRX/USDT', 'LINK/USDT',
               'DOT/USDT', 'MATIC/USDT', 'LTC/USDT', 'BCH/USDT', 'UNI/USDT']
    
    candidates = []
    print("🔍 Scanning Market for Sweeps...")
    
    for sym in symbols:
        try:
            # 1H Chart එකේ විතරක් ඉක්මන් check එකක් දානවා
            df = get_market_data(sym, '1h', limit=50)
            
            # Logic: අන්තිම Candle එකේ ලොකු Wick එකක් තියෙනවද? (Potential Sweep)
            last_candle = df.iloc[-1]
            body_size = abs(last_candle['close'] - last_candle['open'])
            wick_size = (last_candle['high'] - last_candle['low']) - body_size
            
            # Wick එක Body එක වගේ දෙගුණයක් නම්, ඒක Sweep එකක් වෙන්න පුළුවන්
            if wick_size > (body_size * 2):
                candidates.append(sym)
                print(f"Found Candidate: {sym}")
                
        except Exception as e:
            continue
            
    return candidates[:5] # උපරිම 5යි ගන්නේ (Rate Limit හින්දා)

# --- 3. THE GEMINI "EYE" ---
async def analyze_with_gemini(symbol):
    print(f"🤖 Analyzing {symbol} with Gemini...")
    
    # Timeframes 4ටම Data ගන්නවා
    df_4h = get_market_data(symbol, '4h')
    df_1h = get_market_data(symbol, '1h')
    df_15m = get_market_data(symbol, '15m')
    df_5m = get_market_data(symbol, '5m')
    
    # Images හදනවා
    img_4h = generate_chart_image(df_4h, f"{symbol} 4H")
    img_1h = generate_chart_image(df_1h, f"{symbol} 1H")
    img_15m = generate_chart_image(df_15m, f"{symbol} 15m")
    img_5m = generate_chart_image(df_5m, f"{symbol} 5m")
    
    # Prompt එක (SMC Strategy)
    prompt = """
    Role: Expert Crypto Trader using "5-D Fusion Strategy" (ICT + Malaysian SnR).
    Task: Analyze these 4 charts (4H, 1H, 15m, 5m) for a perfect sniper entry.
    
    Strategy Rules:
    1. Trend: Identify 4H direction.
    2. The Raid: Look for Liquidity Sweep (SSL/BSL) on 1H/15m.
    3. Confirmation: Look for QML Pattern + MSS on 5m.
    4. Entry: Overlap of ICT FVG + Malaysian MPL.
    
    Output JSON ONLY:
    {
        "decision": "BUY_LIMIT" or "SELL_LIMIT" or "WAIT",
        "entry": price,
        "stop_loss": price,
        "tp1": price,
        "reason": "Short summary of the setup"
    }
    """
    
    # පින්තූර 4ම යවනවා (Pillow හරහා load කරලා)
    from PIL import Image
    images = [Image.open(img_4h), Image.open(img_1h), Image.open(img_15m), Image.open(img_5m)]
    
    response = model.generate_content([prompt, *images])
    return response.text

# --- 4. TELEGRAM SENDER ---
async def send_signal(message):
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=CHANNEL_ID, text=message)

# --- MAIN LOOP ---
async def main():
    candidates = get_top_candidates()
    
    if not candidates:
        print("No interesting setups found via Filter.")
        return

    for coin in candidates:
        try:
            analysis_text = await analyze_with_gemini(coin)
            
            # JSON clean කරනවා
            cleaned_text = analysis_text.replace("```json", "").replace("```", "").strip()
            import json
            data = json.loads(cleaned_text)
            
            if data['decision'] != "WAIT":
                # Signal එකක් හම්බුණා!
                msg = f"🚀 **5-D FUSION SIGNAL** 🚀\n\n" \
                      f"💎 **{coin}**\n" \
                      f"Action: {data['decision']}\n" \
                      f"Entry: {data['entry']}\n" \
                      f"⛔ SL: {data['stop_loss']}\n" \
                      f"🎯 TP1: {data['tp1']}\n\n" \
                      f"Reason: {data['reason']}\n\n" \
                      f"⚠️ *AI Analysis - DYOR*"
                
                await send_signal(msg)
                print(f"✅ Signal Sent for {coin}")
            else:
                print(f"Analysis for {coin}: WAIT")
                
        except Exception as e:
            print(f"Error analyzing {coin}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
