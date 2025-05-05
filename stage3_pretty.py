from flask import Flask, request, redirect, url_for, render_template_string
from flask import render_template

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
import yfinance as yf
from sqlalchemy import text
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import io, base64
import os



app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///C:/Users/19257/CS348p2/Project/mydatabase.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "isolation_level": "SERIALIZABLE"
}

db = SQLAlchemy(app)


# ---------------------------
# Load sp500 CSV
# ---------------------------
def load_sp500_table(data):
    # Clear existing data in the table
    db.session.query(SP500Stock).delete()
    for stock in data:
        # Convert price to float if possible
        try:
            price = float(stock['Price'])
        except (TypeError, ValueError):
            price = None
        new_stock = SP500Stock(
            Ticker = stock['Ticker'],
            ShortName = stock['ShortName'],
            Sector = stock['Sector'],
            Industry = stock['Industry'],
            Price = price
        )
        db.session.add(new_stock)
    db.session.commit()

# ---------------------------
# Helper Function: Fetch S&P 500 Data from Wikipedia and yfinance
# ---------------------------
def fast_fetch_sp500_data():
    # 1) pull the wiki table
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    sp500_df = pd.read_html(requests.get(url).text)[0]
    tickers = [t.strip().replace('.', '-') for t in sp500_df['Symbol']]

    # 2) batch‐download just the Close prices
    price_df = yf.download(tickers, period="1d")  # or period="5d" if you need more history
    # extract the 'Close' sub‐frame:
    close_df = price_df.xs('Close', axis=1, level=0)
    last_closes = close_df.iloc[-1].to_dict()

    # 3) build your list, using the wiki columns for names/sector/industry
    stock_info_list = []
    for _, row in sp500_df.iterrows():
        t = row['Symbol'].strip().replace('.', '-')
        stock_info_list.append({
            "Ticker":    t,
            "ShortName": row['Security'],
            "Sector":    row['GICS Sector'],
            "Industry":  row['GICS Sub-Industry'],
            "Price":     last_closes.get(t)     # may be None if missing
        })

    return stock_info_list

# ---------------------------
# Helper Function: Get Stock Info (Cache then Fallback to yfinance)
# ---------------------------
def get_stock_info(ticker):
    """Return stock info dict for the given ticker.
       First, check the global sp500_data (case-insensitive match);
       if not found, call yfinance directly."""
    if sp500_data:
        for stock in sp500_data:
            if stock['Ticker'].upper() == ticker.upper():
                return stock
    try:
        info = yf.Ticker(ticker).info
        return {
            "Ticker": ticker.upper(),
            "ShortName": info.get("shortName", "N/A"),
            "Sector": info.get("sector", "N/A"),
            "Industry": info.get("industry", "N/A"),
            "Price": info.get("regularMarketPrice", "N/A")
        }
    except Exception as e:
        print(f"Error fetching info for {ticker}: {e}")
        return None

# ---------------------------
# New Route: Stock Chart with 20-Day Moving Average
# ---------------------------
@app.route('/stock_chart/<ticker>')
def stock_chart(ticker):
    df = yf.download(ticker, period="6mo")
    if df.empty:
        # no data
        return render_template('stock_chart_error.html', ticker=ticker.upper())
    
    df['MA20'] = df['Close'].rolling(window=20).mean()
    plt.figure(figsize=(10,5))
    plt.plot(df.index, df['Close'], label='Close Price', color='#0d6efd')
    plt.plot(df.index, df['MA20'], label='20-Day MA', linestyle='--', color='#dc3545')
    plt.title(f"{ticker.upper()} Price & 20-Day Moving Average", fontsize=14, fontweight='bold')
    plt.xlabel("Date")
    plt.ylabel("Price ($)")
    plt.grid(True, alpha=0.3)
    plt.legend(frameon=True)
    plt.tight_layout()
    
    # Calculate some statistics for the stock
    current_price = float(df['Close'].iloc[-1])  # Convert to float
    prev_price = float(df['Close'].iloc[-2])     # Convert to float
    price_change = current_price - prev_price
    price_change_pct = (price_change / prev_price) * 100
    avg_volume = float(df['Volume'].mean())
    high_52wk = float(df['High'].max())
    low_52wk = float(df['Low'].min())
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf8')
    plt.close()
    
    # after saving to buf & encoding
    return render_template(
      'stock_chart.html',
      ticker=ticker.upper(),
      image_base64=image_base64,
      stock_info=get_stock_info(ticker),
      current_price=current_price,
      price_change=price_change,
      price_change_pct=price_change_pct,
      avg_volume=avg_volume,
      high_52wk=high_52wk,
      low_52wk=low_52wk
    )

# ---------------------------
# Models
# ---------------------------
class UserPortfolio(db.Model):
    __tablename__ = 'user_portfolios'
    portfolio_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    portfolio_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))

class Stock(db.Model):
    __tablename__ = 'stocks'
    stock_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ticker_symbol = db.Column(db.String(10), unique=True, nullable=False)
    company_name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float)  # Store current price

class PortfolioEntry(db.Model):
    __tablename__ = 'portfolio_entries'
    entry_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('user_portfolios.portfolio_id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stocks.stock_id'), nullable=False)
    shares = db.Column(db.Integer, nullable=False, default=1)  # Number of shares held
    
class SP500Stock(db.Model):
    __tablename__ = 'sp500_data'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Ticker = db.Column(db.String(10), unique=True, nullable=False)
    ShortName = db.Column(db.String(200))
    Sector = db.Column(db.String(200))
    Industry = db.Column(db.String(200))
    Price = db.Column(db.Float)

# ---------------------------
# Main Routes & Portfolio CRUD
# ---------------------------
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/portfolios')
def list_portfolios():
    portfolios = UserPortfolio.query.all()
    return render_template('list_portfolios.html', portfolios=portfolios)
    

@app.route('/portfolios/create', methods=['GET', 'POST'])
def create_portfolio():
    if request.method == 'POST':
        portfolio_name = request.form.get('portfolio_name')
        description = request.form.get('description')
        new_portfolio = UserPortfolio(
            portfolio_name=portfolio_name,
            description=description
        )
        db.session.add(new_portfolio)
        db.session.commit()
        return redirect(url_for('list_portfolios'))
    else:
        return render_template('create_portfolio.html')

@app.route('/portfolios/edit/<int:portfolio_id>', methods=['GET', 'POST'])
def edit_portfolio(portfolio_id):
    portfolio = UserPortfolio.query.get_or_404(portfolio_id)
    if request.method == 'POST':
        portfolio.portfolio_name = request.form.get('portfolio_name')
        portfolio.description = request.form.get('description')
        db.session.commit()
        return redirect(url_for('list_portfolios'))
    else:
        return render_template('edit_portfolio.html', portfolio = portfolio)

@app.route('/portfolios/delete/<int:portfolio_id>', methods=['POST'])
def delete_portfolio(portfolio_id):
    PortfolioEntry.query.filter_by(portfolio_id=portfolio_id).delete()
    portfolio = UserPortfolio.query.get_or_404(portfolio_id)
    db.session.delete(portfolio)
    db.session.commit()
    return redirect(url_for('list_portfolios'))

@app.route('/portfolios/<int:portfolio_id>/detail')
def portfolio_detail(portfolio_id):
    portfolio = UserPortfolio.query.get_or_404(portfolio_id)
    entries = db.session.query(PortfolioEntry, Stock).join(
        Stock, PortfolioEntry.stock_id == Stock.stock_id
    ).filter(PortfolioEntry.portfolio_id == portfolio_id).all()


    return render_template(
        'portfolio_detail.html',
        portfolio=portfolio,
        entries=entries,
        get_stock_info=get_stock_info
    )

@app.route('/portfolios/<int:portfolio_id>/add_stock', methods=['GET', 'POST'])
def add_stock_route(portfolio_id):
    portfolio = UserPortfolio.query.get_or_404(portfolio_id)
    error = None
    # this will commit the empty transaction so `begin()` can work
    db.session.commit()

    if request.method == 'POST':
        ticker_input = request.form.get('ticker_symbol', '').strip().upper()
        shares_input = request.form.get('shares', '').strip()

        # 1) validate ticker
        if not ticker_input:
            error = "Please provide a valid ticker symbol."
        else:
            # 2) fetch via yfinance
            try:
                info = yf.Ticker(ticker_input.replace('.', '-')).info
                company = info.get('shortName')
                price   = info.get('regularMarketPrice')
                if not company or price is None:
                    raise ValueError("Ticker not found or price missing")
            except Exception as e:
                error = f"Error fetching {ticker_input}: {e}"

        # 3) parse shares
        if error is None:
            try:
                shares = max(1, int(shares_input or 1))
            except ValueError:
                shares = 1

        # ---- begin ONE transaction block ----
        try:
            with db.session.begin():  # everything inside here is atomic
                # 1) upsert Stock row
                stock = Stock.query.filter_by(ticker_symbol=ticker_input).first()
                if not stock:
                    stock = Stock(
                        ticker_symbol=ticker_input,
                        company_name=company,
                        price=price
                    )
                    db.session.add(stock)
                else:
                    stock.price = price

                # 2) insert or update PortfolioEntry
                entry = (PortfolioEntry
                         .query
                         .filter_by(portfolio_id=portfolio_id, stock_id=stock.stock_id)
                         .with_for_update()  # lock the row so concurrent txs can't race
                         .first())

                if entry:
                    entry.shares += shares
                else:
                    entry = PortfolioEntry(
                        portfolio_id=portfolio_id,
                        stock_id=stock.stock_id,
                        shares=shares
                    )
                    db.session.add(entry)

            # if we get here, the transaction committed
            return redirect(url_for('portfolio_detail', portfolio_id=portfolio_id))

        except SQLAlchemyError as e:
            # on error, session is rolled back automatically by contextmanager
            error = f"Database error: {e}"

    # either GET, or POST with error
    return render_template('add_stock.html',
                           portfolio=portfolio,
                           error=error)

@app.route('/portfolios/<int:portfolio_id>/remove_stock/<int:entry_id>', methods=['POST'])
def remove_stock(portfolio_id, entry_id):
    entry = PortfolioEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('portfolio_detail', portfolio_id=portfolio_id))

# ---------------------------
# Portfolio Value Route with Bootstrap Styling
# ---------------------------
@app.route('/portfolio_value/<int:portfolio_id>')
def portfolio_value(portfolio_id):
    portfolio = UserPortfolio.query.get_or_404(portfolio_id)

    # prepared stmt for total value
    total_sql = text("""
        SELECT SUM(pe.shares * s.price) AS total_value
        FROM portfolio_entries pe
        JOIN stocks s ON pe.stock_id = s.stock_id
        WHERE pe.portfolio_id = :pid
    """)
    total_value = db.session.execute(total_sql, {"pid": portfolio_id}).scalar() or 0

    # prepared stmt for composition
    comp_sql = text("""
        SELECT s.ticker_symbol,
               s.company_name,
               pe.shares,
               s.price,
               (pe.shares * s.price) AS value
        FROM portfolio_entries pe
        JOIN stocks s ON pe.stock_id = s.stock_id
        WHERE pe.portfolio_id = :pid
    """)
    stocks = db.session.execute(comp_sql, {"pid": portfolio_id}).mappings().all()

    return render_template(
        'portfolio_value.html',
        portfolio=portfolio,
        total_value=total_value,
        stocks=stocks
    )

# ---------------------------
# S&P 500 Index Report with Bootstrap Styling
# ---------------------------
@app.route('/index_report', methods=['GET', 'POST'])
def index_report():
    # Build the drop-down options for sectors and industries from your table.
    if sp500_data:
        sectors = sorted({str(stock["Sector"]) for stock in sp500_data if isinstance(stock["Sector"], str) and stock["Sector"] != "N/A"})
        industries = sorted({str(stock["Industry"]) for stock in sp500_data if isinstance(stock["Industry"], str) and stock["Industry"] != "N/A"})
    else:
        sectors, industries = [], []
    sector_options = ["All"] + sectors
    industry_options = ["All"] + industries
    
    chosen_index = None
    chosen_sector = None
    chosen_industry = None
    rows = []
    
    if request.method == 'POST':
        chosen_index = request.form.get('chosen_index')
        chosen_sector = request.form.get('sector_filter')
        chosen_industry = request.form.get('industry_filter')
        
        if chosen_index == 'SNP':
            # Build the prepared statement - keeping the same SQL logic
            sql = "SELECT * FROM sp500_data WHERE 1=1"
            params = {}
            if chosen_sector and chosen_sector != "All":
                sql += " AND Sector = :sector"
                params["sector"] = chosen_sector
            if chosen_industry and chosen_industry != "All":
                sql += " AND Industry = :industry"
                params["industry"] = chosen_industry

            rows = db.session.execute(text(sql), params).mappings().all()
    

    return render_template(
        'index_report.html',
        sector_options=sector_options,
        industry_options=industry_options,
        chosen_index=chosen_index,
        chosen_sector=chosen_sector,
        chosen_industry=chosen_industry,
        rows=rows
    )

# ---------------------------
# Update S&P 500 Data Route with Bootstrap Styling
# ---------------------------
@app.route('/update_sp500')
def update_sp500():
    global sp500_data
    sp500_data = fast_fetch_sp500_data()
    csv_path = "C:/Users/19257/CS348p2/Project/sp500_info_df.csv"
    sp500_df = pd.DataFrame(sp500_data)
    sp500_df.to_csv(csv_path, index=False)
    # Load the updated data into the database table.
    load_sp500_table(sp500_data)
    return render_template('update_sp500.html')

# ---------------------------
# Run the App
# ---------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # run your CREATE INDEX DDL via the session - keeping existing logic
        for ddl in (
            "CREATE INDEX IF NOT EXISTS idx_pe_portfolio   ON portfolio_entries(portfolio_id)",
            "CREATE INDEX IF NOT EXISTS idx_pe_stock       ON portfolio_entries(stock_id)",
            "CREATE INDEX IF NOT EXISTS idx_pe_port_stock  ON portfolio_entries(portfolio_id, stock_id)",
            "CREATE INDEX IF NOT EXISTS idx_sp500_sector   ON sp500_data(Sector)",
            "CREATE INDEX IF NOT EXISTS idx_sp500_ind      ON sp500_data(Industry)",
        ):
            db.session.execute(text(ddl))
        db.session.commit()
        csv_path = "C:/Users/19257/CS348p2/Project/sp500_info_df.csv"
        if os.path.exists(csv_path):
            sp500_df = pd.read_csv(csv_path)
            sp500_data = sp500_df.to_dict(orient='records')
            print("Loaded S&P 500 data from CSV.")
        else:
            sp500_data = fast_fetch_sp500_data()
            sp500_df = pd.DataFrame(sp500_data)
            sp500_df.to_csv(csv_path, index=False)
            print("Fetched S&P 500 data from API and saved to CSV.")
        # Load the data into the sp500_data table
        load_sp500_table(sp500_data)
    app.run(debug=False)