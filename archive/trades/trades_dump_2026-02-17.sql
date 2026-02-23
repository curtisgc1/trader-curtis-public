PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE simple_source_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            entry_price REAL,
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            trade_grade TEXT,
            outcome TEXT,
            sources TEXT,  -- JSON of all source scores
            bullish_count INTEGER,
            bearish_count INTEGER,
            neutral_count INTEGER,
            combo_used TEXT,
            created_at TEXT
        );
INSERT INTO simple_source_outcomes VALUES(1,'MARA',9.199999999999999289,7.5,-91.79999999999995453,-18.47826086956521153,'D','loss','{"reddit_wsb": {"score": 55, "prediction": "neutral"}, "reddit_stocks": {"score": 55, "prediction": "neutral"}, "twitter": {"score": 55, "prediction": "neutral"}, "grok_ai": {"score": 55, "prediction": "neutral"}, "trump": {"score": 55, "prediction": "neutral"}, "analyst": {"score": 55, "prediction": "neutral"}}',0,0,6,'no_consensus','2026-02-15T23:22:06.200982');
INSERT INTO simple_source_outcomes VALUES(2,'ASTS',109.3599999999999995,86.81999999999999317,-788.900000000000091,-20.61082662765180018,'D','loss','{"reddit_wsb": {"score": 50, "prediction": "neutral"}, "reddit_stocks": {"score": 50, "prediction": "neutral"}, "twitter": {"score": 50, "prediction": "neutral"}, "grok_ai": {"score": 50, "prediction": "neutral"}, "trump": {"score": 50, "prediction": "neutral"}, "analyst": {"score": 50, "prediction": "neutral"}}',0,0,6,'no_consensus','2026-02-15T23:22:06.201591');
INSERT INTO simple_source_outcomes VALUES(3,'PLTR',162.5900000000000034,129.9966670000000021,-97.7799989999999752,-20.04633310781721178,'D','loss','{"reddit_wsb": {"score": 50, "prediction": "neutral"}, "reddit_stocks": {"score": 50, "prediction": "neutral"}, "twitter": {"score": 50, "prediction": "neutral"}, "grok_ai": {"score": 50, "prediction": "neutral"}, "trump": {"score": 50, "prediction": "neutral"}, "analyst": {"score": 50, "prediction": "neutral"}}',0,0,6,'no_consensus','2026-02-15T23:22:06.202282');
COMMIT;
