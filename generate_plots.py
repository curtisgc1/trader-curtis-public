#!/usr/bin/env python3
"""
Trading Dashboard Plots
Generate visualizations for the trading system
"""

import sqlite3
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path('/Users/Shared/curtis/trader-curtis/data/trades.db')
OUTPUT_DIR = Path('/Users/Shared/curtis/trader-curtis/plots')
OUTPUT_DIR.mkdir(exist_ok=True)

def plot_portfolio_performance():
    """Plot portfolio value over time"""
    conn = sqlite3.connect(DB_PATH)
    
    # Get trade data
    df = pd.read_sql_query('''
        SELECT timestamp, ticker, pnl, pnl_pct 
        FROM simple_source_outcomes 
        ORDER BY timestamp
    ''', conn)
    
    conn.close()
    
    if df.empty:
        print("No trade data to plot")
        return None
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # P&L Chart
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['cumulative_pnl'] = df['pnl'].cumsum()
    
    ax1.plot(df['timestamp'], df['cumulative_pnl'], marker='o', linewidth=2)
    ax1.axhline(y=0, color='r', linestyle='--', alpha=0.5)
    ax1.set_title('Cumulative P&L', fontsize=14, fontweight='bold')
    ax1.set_ylabel('P&L ($)')
    ax1.grid(True, alpha=0.3)
    
    # Win Rate Chart
    df['win'] = df['pnl'] > 0
    win_rate = df['win'].rolling(window=5).mean() * 100
    
    ax2.plot(df['timestamp'], win_rate, color='green', marker='s')
    ax2.axhline(y=50, color='orange', linestyle='--', alpha=0.5, label='50% breakeven')
    ax2.set_title('Rolling 5-Trade Win Rate', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Win Rate (%)')
    ax2.set_xlabel('Date')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_file = OUTPUT_DIR / 'portfolio_performance.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✅ Saved: {output_file}")
    return output_file

def plot_sentiment_accuracy():
    """Plot source accuracy over time"""
    conn = sqlite3.connect(DB_PATH)
    
    df = pd.read_sql_query('''
        SELECT source, accuracy_rate, last_updated
        FROM source_leaderboard
        ORDER BY accuracy_rate DESC
    ''', conn)
    
    conn.close()
    
    if df.empty:
        print("No source accuracy data")
        return None
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    colors = ['green' if x >= 60 else 'orange' if x >= 40 else 'red' for x in df['accuracy_rate']]
    ax.barh(df['source'], df['accuracy_rate'], color=colors, alpha=0.7)
    
    ax.axvline(x=60, color='green', linestyle='--', alpha=0.5, label='Trust threshold (60%)')
    ax.axvline(x=40, color='red', linestyle='--', alpha=0.5, label='Avoid threshold (40%)')
    
    ax.set_xlabel('Accuracy Rate (%)')
    ax.set_title('Source Accuracy Grades', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    
    output_file = OUTPUT_DIR / 'source_accuracy.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✅ Saved: {output_file}")
    return output_file

def plot_pattern_performance():
    """Plot institutional pattern performance"""
    conn = sqlite3.connect(DB_PATH)
    
    df = pd.read_sql_query('''
        SELECT pattern_type, 
               COUNT(*) as count,
               SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins
        FROM institutional_patterns
        WHERE confirmed = 1
        GROUP BY pattern_type
    ''', conn)
    
    conn.close()
    
    if df.empty:
        print("No pattern data")
        return None
    
    df['win_rate'] = (df['wins'] / df['count'] * 100).fillna(0)
    df = df.sort_values('win_rate', ascending=True)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    colors = ['green' if x >= 70 else 'orange' if x >= 50 else 'red' for x in df['win_rate']]
    ax.barh(df['pattern_type'], df['win_rate'], color=colors, alpha=0.7)
    
    ax.axvline(x=70, color='green', linestyle='--', alpha=0.5, label='Grade A (70%)')
    ax.axvline(x=50, color='orange', linestyle='--', alpha=0.5, label='Grade C (50%)')
    
    ax.set_xlabel('Win Rate (%)')
    ax.set_title('Institutional Pattern Performance', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    
    output_file = OUTPUT_DIR / 'pattern_performance.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✅ Saved: {output_file}")
    return output_file

def plot_gamma_levels():
    """Plot dealer gamma over time"""
    conn = sqlite3.connect(DB_PATH)
    
    df = pd.read_sql_query('''
        SELECT timestamp, spx_gamma, gamma_level
        FROM dealer_gamma
        ORDER BY timestamp DESC
        LIMIT 50
    ''', conn)
    
    conn.close()
    
    if df.empty:
        print("No gamma data")
        return None
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Color by level
    colors = {'EXTREME_LOW': 'red', 'LOW': 'orange', 'NORMAL': 'green', 
              'HIGH': 'blue', 'EXTREME_HIGH': 'purple'}
    
    for level in df['gamma_level'].unique():
        mask = df['gamma_level'] == level
        ax.scatter(df[mask]['timestamp'], df[mask]['spx_gamma'], 
                  c=colors.get(level, 'gray'), label=level, alpha=0.7, s=50)
    
    ax.axhline(y=500, color='red', linestyle='--', alpha=0.5, label='Extreme Low')
    ax.axhline(y=5200, color='green', linestyle='--', alpha=0.5, label='Normal')
    ax.axhline(y=8000, color='blue', linestyle='--', alpha=0.5, label='High')
    
    ax.set_ylabel('Gamma ($M)')
    ax.set_title('S&P 500 Dealer Gamma Levels', fontsize=14, fontweight='bold')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_file = OUTPUT_DIR / 'gamma_levels.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✅ Saved: {output_file}")
    return output_file

def generate_all_plots():
    """Generate all dashboard plots"""
    print("=" * 60)
    print("📊 GENERATING DASHBOARD PLOTS")
    print("=" * 60)
    print()
    
    plots = []
    
    plots.append(("Portfolio Performance", plot_portfolio_performance()))
    plots.append(("Source Accuracy", plot_sentiment_accuracy()))
    plots.append(("Pattern Performance", plot_pattern_performance()))
    plots.append(("Gamma Levels", plot_gamma_levels()))
    
    print()
    print("=" * 60)
    print("PLOTS GENERATED:")
    for name, path in plots:
        if path:
            print(f"  ✅ {name}: {path}")
        else:
            print(f"  ⚪ {name}: No data yet")
    print("=" * 60)
    
    return plots

if __name__ == '__main__':
    generate_all_plots()
    print("\nAll plots saved to: /Users/Shared/curtis/trader-curtis/plots/")
