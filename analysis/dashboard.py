#!/usr/bin/env python3
"""
Performance Dashboard Generator
Creates daily trading performance reports
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent / "data" / "trades.db"

def generate_dashboard():
    """Generate comprehensive performance dashboard"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Overall stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
            SUM(pnl) as total_pnl,
            AVG(pnl_percent) as avg_return,
            MAX(pnl_percent) as best_trade,
            MIN(pnl_percent) as worst_trade
        FROM trades WHERE status = 'closed'
    ''')
    
    overall = cursor.fetchone()
    
    # Source accuracy
    cursor.execute('''
        SELECT source, 
               AVG(CASE WHEN (predicted_direction = 'up' AND actual_direction = 'up') 
                         OR (predicted_direction = 'down' AND actual_direction = 'down') 
                    THEN 1.0 ELSE 0.0 END) as accuracy
        FROM sentiment_accuracy 
        GROUP BY source
    ''')
    
    source_accuracy = {row[0]: f"{row[1]*100:.1f}%" for row in cursor.fetchall()}
    
    # Recent trades (last 7 days)
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute('''
        SELECT ticker, entry_date, pnl, pnl_percent
        FROM trades 
        WHERE entry_date > ?
        ORDER BY entry_date DESC
    ''', (week_ago,))
    
    recent = cursor.fetchall()
    
    conn.close()
    
    dashboard = f"""
╔════════════════════════════════════════════════╗
║     TRADER CURTIS PERFORMANCE DASHBOARD       ║
╚════════════════════════════════════════════════╝

📊 OVERALL PERFORMANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Trades:    {overall[0] or 0}
Win Rate:        {(overall[1] / overall[0] * 100) if overall[0] else 0:.1f}%
Total P&L:       ${overall[3] or 0:,.2f}
Avg Return:      {overall[4] or 0:.2f}%
Best Trade:      +{overall[5] or 0:.1f}%
Worst Trade:     {overall[6] or 0:.1f}%

📈 SOURCE ACCURACY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{chr(10).join(f"  {k}: {v}" for k, v in source_accuracy.items()) if source_accuracy else "  No data yet"}

📋 RECENT TRADES (Last 7 Days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    for trade in recent[:10]:
        emoji = "🟢" if trade[2] > 0 else "🔴"
        dashboard += f"{emoji} {trade[0]} ({trade[1]}): ${trade[2]:,.2f} ({trade[3]:.1f}%)\n"
    
    dashboard += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}
"""
    
    # Save to file
    dashboard_path = Path(__file__).parent.parent / "reports" / f"dashboard_{datetime.now().strftime('%Y%m%d')}.txt"
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_path.write_text(dashboard)
    
    print(dashboard)
    return dashboard

if __name__ == '__main__':
    generate_dashboard()
