#!/usr/bin/env python3
"""
Generate daily trading performance report
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from trade_analyzer import get_performance_summary

def generate_report():
    summary = get_performance_summary()
    
    report = f"""
╔════════════════════════════════════════╗
║   TRADER CURTIS PERFORMANCE REPORT    ║
╚════════════════════════════════════════╝

Trades:      {summary['total_trades']}
Win Rate:    {summary['win_rate']:.1f}%
Total P&L:   ${summary['total_pnl']:,.2f}
Avg Return:  {summary['avg_return']:.2f}%

Wins:   {summary['wins']} | Avg Win:  {summary['avg_win'] or 0:.2f}%
Losses: {summary['losses']} | Avg Loss: {summary['avg_loss'] or 0:.2f}%

Sentiment Accuracy: [Run sentiment_analysis.py]

════════════════════════════════════════
Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    
    print(report)
    
    # Save to file
    report_path = Path(__file__).parent.parent / "reports" / "daily_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)

if __name__ == '__main__':
    generate_report()
