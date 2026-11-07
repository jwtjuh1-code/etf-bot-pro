import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf

TICKER = "VWCE.DE"
START_CASH = 1000.0
FEE = 0.001
STATE = Path("data/state.json")

def blank_account():
    return {"cash": START_CASH, "units": 0.0, "trades": [], "history": []}

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"version":"2.0","ticker":TICKER,"processed_days":0,
            "last_processed_date":None,
            "accounts":{n:blank_account() for n in ("SMA200","RSI","COMBI")},
            "daily":[],"started_at":datetime.now(timezone.utc).isoformat()}

def execute(account, side, price, date, reason):
    if side == "BUY" and account["cash"] > 1:
        spend = account["cash"] / (1 + FEE)
        units = spend / price
        fee = spend * FEE
        account["cash"] = 0.0
    elif side == "SELL" and account["units"] > 0:
        units = account["units"]
        gross = units * price
        fee = gross * FEE
        account["cash"] += gross - fee
        account["units"] = 0.0
    else:
        return
    if side == "BUY":
        account["units"] += units
    account["trades"].append({
        "date":date,"side":"KOOP" if side=="BUY" else "VERKOOP",
        "price":round(price,4),"units":round(units,6),
        "fee":round(fee,2),"reason":reason
    })

def main():
    state = load_state()
    df = yf.download(TICKER, period="2y", interval="1d",
                     auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError("Geen koersdata ontvangen van Yahoo Finance.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df["Close"].dropna().astype(float)
    sma = close.rolling(200).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))

    date = close.index[-1].date().isoformat()
    price = float(close.iloc[-1])
    sma_v = float(sma.iloc[-1]) if pd.notna(sma.iloc[-1]) else None
    rsi_v = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None

    # Verwerk elke koersdatum maximaal eenmaal.
    if state.get("last_processed_date") != date:
        for name, a in state["accounts"].items():
            invested = a["units"] > 0
            side, reason = None, ""
            if sma_v is not None and rsi_v is not None:
                if name == "SMA200":
                    if not invested and price > sma_v: side, reason = "BUY", "Koers boven SMA200"
                    elif invested and price < sma_v: side, reason = "SELL", "Koers onder SMA200"
                elif name == "RSI":
                    if not invested and rsi_v < 30: side, reason = "BUY", "RSI onder 30"
                    elif invested and rsi_v > 70: side, reason = "SELL", "RSI boven 70"
                else:
                    if not invested and price > sma_v and rsi_v < 40: side, reason = "BUY", "Boven SMA200 en RSI onder 40"
                    elif invested and (price < sma_v or rsi_v > 70): side, reason = "SELL", "Onder SMA200 of RSI boven 70"
            if side:
                execute(a, side, price, date, reason)
            a["history"].append({"date":date,"equity":round(a["cash"]+a["units"]*price,2)})
        state["last_processed_date"] = date
        state["processed_days"] = int(state.get("processed_days",0)) + 1
        state.setdefault("daily",[]).append({
            "date":date,"price":round(price,4),
            "sma200":round(sma_v,4) if sma_v is not None else None,
            "rsi14":round(rsi_v,2) if rsi_v is not None else None
        })

    state.update({
        "latest_date":date,"latest_price":round(price,4),
        "latest_sma200":round(sma_v,4) if sma_v is not None else None,
        "latest_rsi14":round(rsi_v,2) if rsi_v is not None else None,
        "progress_percent":min(100,round(state["processed_days"]/30*100,1)),
        "status":"30-daagse test afgerond" if state["processed_days"]>=30 else "Paper trading actief",
        "strategy_descriptions":{
            "SMA200":"Koop boven SMA200; verkoop eronder",
            "RSI":"Koop bij RSI < 30; verkoop bij RSI > 70",
            "COMBI":"Koop boven SMA200 met RSI < 40; verkoop onder SMA200 of RSI > 70"
        },
        "warnings":[
            "Alle transacties zijn virtueel; er worden geen echte orders geplaatst.",
            "Yahoo Finance/yfinance is een onofficiële koersbron en kan vertraagd of onbeschikbaar zijn.",
            "Dertig beursdagen is een korte test en bewijst geen toekomstige winstgevendheid."
        ]
    })
    for a in state["accounts"].values():
        a["equity"] = round(a["cash"]+a["units"]*price,2)
        a["return_eur"] = round(a["equity"]-START_CASH,2)
        a["return_percent"] = round((a["equity"]/START_CASH-1)*100,2)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"{date} | VWCE {price:.2f} | testdag {state['processed_days']}")

if __name__ == "__main__":
    main()
