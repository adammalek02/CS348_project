from flask import Flask, request, redirect, url_for
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
def fetch_sp500_data():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    response = requests.get(url)
    dfs = pd.read_html(response.text)
    sp500_df = dfs[0]  # Typically, the first table
    tickers = sp500_df['Symbol'].tolist()
    stock_info_list = []
    i = 1
    for ticker in tickers:
        ticker = ticker.strip()  # Remove any extra whitespace
        ticker = ticker.replace('.', '-')
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            stock_info_list.append({
                "Ticker": ticker,
                "ShortName": info.get("shortName", "N/A"),
                "Sector": info.get("sector", "N/A"),
                "Industry": info.get("industry", "N/A"),
                "Price": info.get("regularMarketPrice", "N/A")
            })
            print(f"Retrieved info for {ticker} stock #{i}/503")
            i += 1
        except Exception as e:
            print(f"Error retrieving info for {ticker}: {e}")
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
        return f"<p>Error: No historical data found for {ticker}.</p>"
    df['MA20'] = df['Close'].rolling(window=20).mean()
    plt.figure(figsize=(10,5))
    plt.plot(df.index, df['Close'], label='Close Price')
    plt.plot(df.index, df['MA20'], label='20-Day MA', linestyle='--')
    plt.title(f"{ticker.upper()} Price & 20-Day Moving Average")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.legend()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf8')
    plt.close()
    return f"""
    <html>
    <head><title>{ticker.upper()} Chart</title></head>
    <body>
      <h1>{ticker.upper()} Chart with 20-Day Moving Average</h1>
      <img src="data:image/png;base64,{image_base64}" alt="Chart for {ticker.upper()}" />
      <p><a href="/portfolios">Back to Portfolios</a></p>
    </body>
    </html>
    """

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
    return """
    <html>
    <head><title>Home</title></head>
    <body>
      <h1>Welcome to the Stock Manager/Tracker App!</h1>
      <p><a href="/portfolios">List Portfolios</a></p>
      <p><a href="/index_report">View Stocks by Index</a></p>
    </body>
    </html>
    """

@app.route('/portfolios')
def list_portfolios():
    portfolios = UserPortfolio.query.all()
    portfolios_html = ""
    for p in portfolios:
        portfolios_html += f"""
        <li>
            <strong>{p.portfolio_name}</strong> 
            (ID: {p.portfolio_id})<br>
            Description: {p.description or 'N/A'}<br>
            <a href="/portfolios/{p.portfolio_id}/detail">View Details</a> | 
            <a href="/portfolios/edit/{p.portfolio_id}">Edit</a>
            <form action="/portfolios/delete/{p.portfolio_id}" method="POST" style="display:inline;">
                <button type="submit">Delete</button>
            </form>
        </li>
        <hr>
        """
    page = f"""
    <html>
    <head><title>Portfolios</title></head>
    <body>
      <h1>All Portfolios</h1>
      <p><a href="/portfolios/create">Create a New Portfolio</a></p>
      <ul>{portfolios_html}</ul>
      <p><a href="/">Back to Home</a></p>
    </body>
    </html>
    """
    return page

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
        return """
        <html>
        <head><title>Create Portfolio</title></head>
        <body>
            <h1>Create a New Portfolio</h1>
            <form method="POST">
                <label>Portfolio Name:</label><br>
                <input type="text" name="portfolio_name" /><br><br>
                <label>Description:</label><br>
                <input type="text" name="description" /><br><br>
                <button type="submit">Save</button>
            </form>
            <p><a href="/portfolios">Cancel</a></p>
        </body>
        </html>
        """

@app.route('/portfolios/edit/<int:portfolio_id>', methods=['GET', 'POST'])
def edit_portfolio(portfolio_id):
    portfolio = UserPortfolio.query.get_or_404(portfolio_id)
    if request.method == 'POST':
        portfolio.portfolio_name = request.form.get('portfolio_name')
        portfolio.description = request.form.get('description')
        db.session.commit()
        return redirect(url_for('list_portfolios'))
    else:
        return f"""
        <html>
        <head><title>Edit Portfolio</title></head>
        <body>
            <h1>Edit Portfolio (ID: {portfolio_id})</h1>
            <form method="POST">
                <label>Portfolio Name:</label><br>
                <input type="text" name="portfolio_name" value="{portfolio.portfolio_name}" /><br><br>
                <label>Description:</label><br>
                <input type="text" name="description" value="{portfolio.description or ''}" /><br><br>
                <button type="submit">Save Changes</button>
            </form>
            <p><a href="/portfolios">Cancel</a></p>
        </body>
        </html>
        """

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
    
    # Build a bullet list showing ticker, company, and shares.
    entries_list_html = ""
    for entry, stock in entries:
        chart_link = f"<a href='/stock_chart/{stock.ticker_symbol}'>View Chart</a>"
        entries_list_html += f"""
        <li>
            {stock.ticker_symbol} - {stock.company_name} (Shares: {entry.shares}) {chart_link}
            <form action="/portfolios/{portfolio_id}/remove_stock/{entry.entry_id}" method="POST" style="display:inline;">
                <button type="submit">Remove</button>
            </form>
        </li>
        <hr>
        """
    
    # Build a detailed report table with up-to-date info and share count.
    report_table_html = "<h3>Detailed Stock Report</h3>"
    report_table_html += "<table border='1' cellspacing='0' cellpadding='5'>"
    report_table_html += ("<tr>"
                          "<th>Ticker</th>"
                          "<th>Short Name</th>"
                          "<th>Sector</th>"
                          "<th>Industry</th>"
                          "<th>Price</th>"
                          "<th>Shares</th>"
                          "<th>Chart</th>"
                          "</tr>")
    for entry, stock in entries:
        info = get_stock_info(stock.ticker_symbol)
        chart_link = f"<a href='/stock_chart/{stock.ticker_symbol}'>View Chart</a>"
        shares = entry.shares
        if info:
            report_table_html += (f"<tr>"
                                  f"<td>{info['Ticker']}</td>"
                                  f"<td>{info['ShortName']}</td>"
                                  f"<td>{info['Sector']}</td>"
                                  f"<td>{info['Industry']}</td>"
                                  f"<td>{info['Price']}</td>"
                                  f"<td>{shares}</td>"
                                  f"<td>{chart_link}</td>"
                                  f"</tr>")
        else:
            report_table_html += (f"<tr>"
                                  f"<td>{stock.ticker_symbol}</td>"
                                  f"<td>{stock.company_name}</td>"
                                  f"<td>N/A</td>"
                                  f"<td>N/A</td>"
                                  f"<td>N/A</td>"
                                  f"<td>{shares}</td>"
                                  f"<td>{chart_link}</td>"
                                  f"</tr>")
    report_table_html += "</table>"
    
    portfolio_value_link = f"<a href='/portfolio_value/{portfolio.portfolio_id}'>View Portfolio Value</a>"
    
    page = f"""
    <html>
    <head><title>Portfolio Detail</title></head>
    <body>
      <h1>Portfolio: {portfolio.portfolio_name} (ID: {portfolio.portfolio_id})</h1>
      <p>{portfolio.description or 'No description provided.'}</p>
      
      <h2>Stocks in this Portfolio:</h2>
      <ul>{entries_list_html if entries_list_html else '<li>No stocks added yet.</li>'}</ul>
      
      {report_table_html}
      
      <p>{portfolio_value_link}</p>
      <p><a href="/portfolios/{portfolio.portfolio_id}/add_stock">Add a Stock</a></p>
      <p><a href="/portfolios">Back to Portfolios</a></p>
    </body>
    </html>
    """
    return page


@app.route('/portfolios/<int:portfolio_id>/add_stock', methods=['GET', 'POST'])
def add_stock_route(portfolio_id):
    portfolio = UserPortfolio.query.get_or_404(portfolio_id)
    # this will commit the empty transaction so `begin()` can work
    db.session.commit()

    if request.method == 'POST':
        ticker_input = request.form.get('ticker_symbol', '').strip().upper()
        shares_input = request.form.get('shares', '').strip()

        if not ticker_input:
            return f"<p>Error: Please provide a ticker symbol. <a href='{url_for('add_stock_route', portfolio_id=portfolio_id)}'>Try again</a></p>"

        # fetch price & name from yfinance
        try:
            ticker_input = ticker_input.replace('.', '-')
            info = yf.Ticker(ticker_input).info
            company = info.get('shortName')
            price   = info.get('regularMarketPrice', None)
            if not company or price is None:
                raise ValueError("ticker not found or price missing")
        except Exception as e:
            return f"<p>Error fetching {ticker_input}: {e}. <a href='{url_for('add_stock_route', portfolio_id=portfolio_id)}'>Try again</a></p>"

        # parse shares
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
                         .with_for_update()  # lock the row so concurrent txs can’t race
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
            return f"<p>Could not add stock due to database error: {e}</p>"

    # GET: render the same HTML form as before
    return f"""
    <html>
      <head><title>Add Stock</title></head>
      <body>
        <h1>Add a Stock to Portfolio: {portfolio.portfolio_name}</h1>
        <form method="POST">
          <label>Ticker Symbol:</label><br>
          <input type="text" name="ticker_symbol" placeholder="e.g., AAPL" /><br><br>
          <label>Number of Shares:</label><br>
          <input type="number" name="shares" value="1" min="1" /><br><br>
          <button type="submit">Add Stock</button>
        </form>
        <p><a href="{url_for('portfolio_detail', portfolio_id=portfolio_id)}">Cancel</a></p>
      </body>
    </html>
    """


@app.route('/portfolios/<int:portfolio_id>/remove_stock/<int:entry_id>', methods=['POST'])
def remove_stock(portfolio_id, entry_id):
    entry = PortfolioEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('portfolio_detail', portfolio_id=portfolio_id))

# ---------------------------
# New Route: Calculate Portfolio Value (using a prepared statement)
# ---------------------------
@app.route('/portfolio_value/<int:portfolio_id>')
def portfolio_value(portfolio_id):
    sql = text("""
        SELECT SUM(pe.shares * s.price) AS total_value
        FROM portfolio_entries pe
        JOIN stocks s ON pe.stock_id = s.stock_id
        WHERE pe.portfolio_id = :pid
    """)
    result = db.session.execute(sql, {"pid": portfolio_id}).fetchone()
    total_value = result.total_value if result and result.total_value is not None else 0
    return f"""
    <html>
    <head><title>Portfolio Value</title></head>
    <body>
      <h1>Portfolio {portfolio_id} Value: ${total_value:.2f}</h1>
      <p><a href="/portfolios/{portfolio_id}/detail">Back to Portfolio</a></p>
    </body>
    </html>
    """

# ---------------------------
# Report: View Stocks by Index (S&P 500 only for now)
# ---------------------------
@app.route('/index_report', methods=['GET', 'POST'])
def index_report():
    result_html = ""
    # Build the drop-down options for sectors and industries from your table.
    # Here we load them from the global sp500_data; alternatively, you could query the table.
    if sp500_data:
        sectors = sorted({str(stock["Sector"]) for stock in sp500_data if isinstance(stock["Sector"], str) and stock["Sector"] != "N/A"})
        industries = sorted({str(stock["Industry"]) for stock in sp500_data if isinstance(stock["Industry"], str) and stock["Industry"] != "N/A"})
    else:
        sectors, industries = [], []
    sector_options = ["All"] + sectors
    industry_options = ["All"] + industries

    if request.method == 'POST':
        chosen_index = request.form.get('chosen_index')
        chosen_sector = request.form.get('sector_filter')
        chosen_industry = request.form.get('industry_filter')
        if chosen_index == 'SNP':
            # Build the prepared statement
            sql = "SELECT * FROM sp500_data WHERE 1=1"
            params = {}
            if chosen_sector and chosen_sector != "All":
                sql += " AND Sector = :sector"
                params["sector"] = chosen_sector
            if chosen_industry and chosen_industry != "All":
                sql += " AND Industry = :industry"
                params["industry"] = chosen_industry

            rows = db.session.execute(text(sql), params).mappings().all()

            result_html = "<h3>S&P 500 Stocks"
            if chosen_sector and chosen_sector != "All":
                result_html += f" in {chosen_sector} Sector"
            if chosen_industry and chosen_industry != "All":
                result_html += f", {chosen_industry} Industry"
            result_html += "</h3>"
            result_html += "<table border='1' cellspacing='0' cellpadding='5'>"
            result_html += (
                "<tr>"
                "<th>Ticker</th>"
                "<th>Short Name</th>"
                "<th>Sector</th>"
                "<th>Industry</th>"
                "<th>Price</th>"
                "<th>20DayMA</th>"
                "</tr>"
            )
            for row in rows:
                # row is already a mapping because we used .mappings().all()
                chart_link = f"<a href='/stock_chart/{row['Ticker']}'>View Chart</a>"
                result_html += (
                    f"<tr>"
                    f"<td>{row['Ticker']}</td>"
                    f"<td>{row['ShortName']}</td>"
                    f"<td>{row['Sector']}</td>"
                    f"<td>{row['Industry']}</td>"
                    f"<td>{row['Price']}</td>"
                    f"<td>{chart_link}</td>"
                    f"</tr>"
                )
            result_html += "</table>"
        else:
            result_html = "<p>Only S&P 500 data is available for now.</p>"

    # Build drop-down HTML for sectors and industries
    sector_dropdown_html = "".join(f'<option value="{s}">{s}</option>' for s in sector_options)
    industry_dropdown_html = "".join(f'<option value="{i}">{i}</option>' for i in industry_options)

    page = f"""
    <html>
    <head><title>Stocks by Index</title></head>
    <body>
      <h1>View Stocks by Index</h1>
      <form method="POST" action="/index_report">
        <label>Select an Index:</label>
        <select name="chosen_index">
          <option value="SNP">S&P 500</option>
          <option value="DOW">Dow Jones</option>
          <option value="NASDAQ">Nasdaq</option>
        </select>
        <br><br>
        <label>Filter by Sector:</label>
        <select name="sector_filter">
          {sector_dropdown_html}
        </select>
        <br><br>
        <label>Filter by Industry:</label>
        <select name="industry_filter">
          {industry_dropdown_html}
        </select>
        <br><br>
        <button type="submit">Show Stocks</button>
      </form>
      <p><a href="/update_sp500">Update S&P 500 Data</a></p>
      <hr>
      {result_html}
      <p><a href="/">Back to Home</a></p>
    </body>
    </html>
    """
    return page
# ---------------------------
# Update Route for S&P 500 Data
# ---------------------------
@app.route('/update_sp500')
def update_sp500():
    global sp500_data
    sp500_data = fetch_sp500_data()
    csv_path = "C:/Users/19257/CS348p2/Project/sp500_info_df.csv"
    sp500_df = pd.DataFrame(sp500_data)
    sp500_df.to_csv(csv_path, index=False)
    # Load the updated data into the database table.
    load_sp500_table(sp500_data)
    return redirect(url_for('index_report'))

# ---------------------------
# Run the App
# ---------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # run your CREATE INDEX DDL via the session
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
            sp500_data = fetch_sp500_data()
            sp500_df = pd.DataFrame(sp500_data)
            sp500_df.to_csv(csv_path, index=False)
            print("Fetched S&P 500 data from API and saved to CSV.")
        # Load the data into the sp500_data table
        load_sp500_table(sp500_data)
    app.run(debug=False)

