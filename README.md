# CS348_project
Stock Database Project for CS348


final submission is python file stage3_pretty.py 
- current paths are set to my device for the sp500 dataframe adn the db, initial call will be old data, need to update in app to get current correct information
- templates zip file included, contains the html files for front end, need templates folder in root path of python file

I built a Flask-based stock-portfolio web app to demonstrate end-to-end relational-database design in Python/SQL. The app lets users create, update, and delete portfolios, then add stocks with share counts; behind the scenes, SQLAlchemy models (users, portfolios, entries, S&P-500 metadata) sit on an indexed SQLite schema that pushes common joins and filters below 200 ms. A nightly yfinance pipeline refreshes prices and caches them in both CSV and a dedicated table, so the UI—including dynamic dropdowns—rebuilds instantly at startup. For analysis, the app renders an interactive report per ticker: 20-day moving-average charts (Matplotlib), real-time portfolio valuation, composition breakdowns, and per-stock KPIs. All writes run inside ACID-compliant transactions, and parameterized SQL keeps the code injection-safe while remaining portable to Postgres/MySQL.
